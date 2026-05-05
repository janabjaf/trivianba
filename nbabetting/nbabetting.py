"""nbabetting.py – Main NBABetting cog: commands, economy, auto-settlement, news feed."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Set

import discord
from discord import app_commands
from redbot.core import Config, commands
from redbot.core.bot import Red

from .data import BetsManager
from .economy import CURRENCY, DEFAULT_MAX_BET_PCT, DEFAULT_MAX_DAILY_BETS, STARTING_BALANCE, Economy
from .odds import OddsFetcher, calc_parlay_odds, calc_profit, evaluate_bet, fmt_odds, fmt_prop_selection
from .views import (
    BetFlowView,
    ConfirmView,
    GamesView,
    LeaderboardView,
    MyBetsView,
    OddsView,
    ParlayBuilderView,
)

log = logging.getLogger("red.jaffar-cogs.nbabetting")


# ── Admin check ───────────────────────────────────────────────────────────────

async def _is_admin(ctx: commands.Context) -> bool:
    """True if author has Administrator permission OR the configured admin role."""
    if ctx.guild is None:
        return False
    if ctx.author.guild_permissions.administrator:
        return True
    role_id: Optional[int] = await ctx.cog.config.guild(ctx.guild).admin_role()
    if role_id:
        return any(r.id == role_id for r in ctx.author.roles)
    return False


def admin_only():
    return commands.check(_is_admin)


# ══════════════════════════════════════════════════════════════════════════════
# Cog
# ══════════════════════════════════════════════════════════════════════════════

class NBABetting(commands.Cog):
    """NBA betting with live odds, injury-aware lines, player props, and auto-settlement."""

    def __init__(self, bot: Red) -> None:
        self.bot = bot

        # ── Config registration ───────────────────────────────────────────────
        self.config = Config.get_conf(self, identifier=8675309_555, force_registration=True)
        self.config.register_member(
            balance=STARTING_BALANCE,
            total_wagered=0.0,
            total_returned=0.0,
            bets_placed=0,
            bets_won=0,
            bets_lost=0,
            bets_push=0,
        )
        self.config.register_guild(
            admin_role=None,
            notify_channel=None,
            news_channel=None,
            max_bet_pct=DEFAULT_MAX_BET_PCT,
            max_daily_bets=DEFAULT_MAX_DAILY_BETS,
        )

        # ── Helpers ───────────────────────────────────────────────────────────
        self.economy = Economy(self.config, bot)
        self.fetcher = OddsFetcher()
        self.bets    = BetsManager(self)

        self._settlement_task: Optional[asyncio.Task] = None
        self._news_task:       Optional[asyncio.Task] = None

        # Track which news article IDs have already been posted per guild
        self._news_posted: Dict[int, Set[str]] = {}
        # Track last known injury statuses per guild for change detection
        self._injury_snapshot: Dict[int, Dict[str, str]] = {}

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def cog_load(self) -> None:
        self._settlement_task = asyncio.create_task(self._settlement_loop())
        self._news_task       = asyncio.create_task(self._news_loop())

    async def cog_unload(self) -> None:
        for task in (self._settlement_task, self._news_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        await self.fetcher.close()

    # ── Error handler ─────────────────────────────────────────────────────────

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.CheckFailure):
            await ctx.send("❌ You don't have permission to use this command.", ephemeral=True)
        elif isinstance(error, (commands.BadArgument, commands.MissingRequiredArgument)):
            await ctx.send_help(ctx.command)
        else:
            raise error

    # ══════════════════════════════════════════════════════════════════════════
    # Auto-settlement background task
    # ══════════════════════════════════════════════════════════════════════════

    async def _settlement_loop(self) -> None:
        await self.bot.wait_until_ready()
        while True:
            try:
                await self._run_settlement()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.exception("Settlement error: %s", exc)
            await asyncio.sleep(600)   # every 10 minutes

    async def _run_settlement(self) -> None:
        guild_ids = self.bets.get_all_guilds()
        if not guild_ids:
            return

        completed = await self.fetcher.get_completed_games(days_back=2)
        if not completed:
            return

        completed_by_id = {g["event_id"]: g for g in completed}

        for guild_id in guild_ids:
            pending = self.bets.get_all_pending(guild_id)
            if not pending:
                continue

            # Pre-fetch box scores for all events with player-prop or parlay bets
            prop_event_ids: set = set()
            for b in pending:
                if b["bet_type"] == "player_props":
                    prop_event_ids.add(b["event_id"])
                elif b["bet_type"] == "parlay":
                    for leg in b.get("legs", []):
                        if leg.get("leg_type") == "player_props":
                            prop_event_ids.add(leg["event_id"])
            box_scores: dict = {}
            for eid in prop_event_ids:
                if eid in completed_by_id:
                    bs = await self.fetcher.get_game_box_score(eid)
                    if bs:
                        box_scores[eid] = bs

            for bet in pending:
                user_id = int(bet["user_id"])
                stake   = bet["stake"]

                # ── Parlay settlement ──────────────────────────────────────────
                if bet["bet_type"] == "parlay":
                    legs = bet.get("legs", [])
                    if not legs:
                        continue

                    leg_results: List[str] = []
                    can_settle = True

                    for leg in legs:
                        leg_game = completed_by_id.get(leg["event_id"])
                        if not leg_game or leg_game.get("home_score") is None:
                            can_settle = False
                            break

                        if leg.get("leg_type") == "player_props":
                            ps = box_scores.get(leg["event_id"])
                            if ps is None:
                                can_settle = False
                                break
                            leg_result = evaluate_bet(
                                bet_type="player_props",
                                selection=leg["selection"],
                                point=leg.get("point"),
                                home_team=leg_game["home_team"],
                                away_team=leg_game["away_team"],
                                home_score=leg_game["home_score"],
                                away_score=leg_game["away_score"],
                                player_stats=ps,
                            )
                        else:
                            leg_result = evaluate_bet(
                                bet_type=leg["leg_type"],
                                selection=leg["selection"],
                                point=leg.get("point"),
                                home_team=leg_game["home_team"],
                                away_team=leg_game["away_team"],
                                home_score=leg_game["home_score"],
                                away_score=leg_game["away_score"],
                            )
                        leg_results.append(leg_result)

                    if not can_settle:
                        continue

                    if "lost" in leg_results:
                        result = "lost"
                        payout = 0.0
                    elif all(r == "won" for r in leg_results):
                        result = "won"
                        payout = stake + bet["potential_payout"]
                    else:
                        # Some legs pushed — reduce parlay to surviving legs
                        surviving = [
                            legs[i] for i, r in enumerate(leg_results) if r != "push"
                        ]
                        if len(surviving) < 2:
                            result = "push"
                            payout = stake
                        else:
                            new_odds   = calc_parlay_odds([lg["odds"] for lg in surviving])
                            new_profit = calc_profit(stake, new_odds)
                            result     = "won"
                            payout     = stake + new_profit

                    if result != "won" and result != "push":
                        payout = 0.0
                    # Settle first — moves bet out of active before crediting money.
                    settled = self.bets.settle_bet(guild_id, bet["id"], result, payout)
                    if not settled:
                        continue  # already settled (safety guard)
                    if result == "won":
                        await self.economy.add(guild_id, user_id, payout)
                        await self.economy.record_win(guild_id, user_id, payout)
                    elif result == "push":
                        await self.economy.add(guild_id, user_id, payout)
                        await self.economy.record_push(guild_id, user_id, stake)
                    else:
                        await self.economy.record_loss(guild_id, user_id)
                    await self._notify_result(guild_id, user_id, bet, result, payout)
                    continue

                # ── Single bet settlement ──────────────────────────────────────
                game = completed_by_id.get(bet["event_id"])
                if not game:
                    continue
                if game.get("home_score") is None or game.get("away_score") is None:
                    continue

                player_stats = None
                if bet["bet_type"] == "player_props":
                    player_stats = box_scores.get(bet["event_id"])
                    if player_stats is None:
                        continue

                result = evaluate_bet(
                    bet_type=bet["bet_type"],
                    selection=bet["selection"],
                    point=bet.get("point"),
                    home_team=bet["home_team"],
                    away_team=bet["away_team"],
                    home_score=game["home_score"],
                    away_score=game["away_score"],
                    player_stats=player_stats,
                )

                profit = bet["potential_payout"]

                if result == "won":
                    payout = stake + profit
                elif result == "push":
                    payout = stake
                else:
                    payout = 0.0
                # Settle first — prevents double payout if the bot restarts mid-loop.
                settled = self.bets.settle_bet(guild_id, bet["id"], result, payout)
                if not settled:
                    continue  # already settled (safety guard)
                if result == "won":
                    await self.economy.add(guild_id, user_id, payout)
                    await self.economy.record_win(guild_id, user_id, payout)
                elif result == "push":
                    await self.economy.add(guild_id, user_id, payout)
                    await self.economy.record_push(guild_id, user_id, stake)
                else:
                    await self.economy.record_loss(guild_id, user_id)
                await self._notify_result(guild_id, user_id, bet, result, payout)

    async def _notify_result(
        self,
        guild_id: int,
        user_id: int,
        bet: dict,
        result: str,
        payout: float,
    ) -> None:
        """DM the user their bet result AND post to the guild's notify_channel if set."""
        emoji = {"won": "✅", "lost": "❌", "push": "🔄"}.get(result, "❓")
        color = {
            "won":  discord.Color.green(),
            "lost": discord.Color.red(),
            "push": discord.Color.gold(),
        }.get(result, discord.Color.greyple())

        bet_type = bet.get("bet_type", "")

        # Build selection display and game string safely for all bet types
        if bet_type == "parlay":
            legs = bet.get("legs", [])
            sel_display = f"{len(legs)}-leg parlay"
            game_str = "  ·  ".join(
                f"{lg.get('away_team','')} @ {lg.get('home_team','')}" for lg in legs[:3]
            )
            if len(legs) > 3:
                game_str += f"  +{len(legs) - 3} more"
        elif bet_type == "player_props":
            sel_display = fmt_prop_selection(bet.get("selection", ""))
            game_str = f"{bet.get('away_team', '')} @ {bet.get('home_team', '')}"
        else:
            sel_display = bet.get("selection", "")
            game_str = f"{bet.get('away_team', '')} @ {bet.get('home_team', '')}"

        embed = discord.Embed(
            title=f"{emoji} Bet Settled — {result.upper()}",
            color=color,
        )
        embed.add_field(name="Bet ID",    value=f"`{bet['id']}`",        inline=True)
        embed.add_field(name="Game",      value=game_str,                 inline=False)
        embed.add_field(name="Your Pick", value=f"{sel_display}  ({fmt_odds(bet.get('odds', -110))})", inline=True)
        embed.add_field(name="Stake",     value=f"{CURRENCY}{bet['stake']:.0f}", inline=True)
        if result == "won":
            embed.add_field(name="You Won!", value=f"{CURRENCY}**{payout:.0f}**", inline=True)
        elif result == "push":
            embed.add_field(name="Push", value="Stake returned.", inline=True)

        # ── DM the user ───────────────────────────────────────────────────────
        user = self.bot.get_user(user_id)
        if user:
            try:
                await user.send(embed=embed)
            except (discord.Forbidden, discord.HTTPException):
                pass

        # ── Post to notify_channel if configured ──────────────────────────────
        channel_id: Optional[int] = await self.config.guild_from_id(guild_id).notify_channel()
        if channel_id:
            channel = self.bot.get_channel(channel_id)
            if channel:
                try:
                    member  = channel.guild.get_member(user_id)
                    mention = member.mention if member else f"<@{user_id}>"
                    await channel.send(content=mention, embed=embed)
                except (discord.Forbidden, discord.HTTPException):
                    pass

    # ══════════════════════════════════════════════════════════════════════════
    # ESPN news background task
    # ══════════════════════════════════════════════════════════════════════════

    async def _news_loop(self) -> None:
        """Background task: poll ESPN for NBA news and injury updates every 15 minutes."""
        await self.bot.wait_until_ready()
        await asyncio.sleep(90)  # Initial delay to let everything else stabilize
        while True:
            try:
                await self._run_news_check()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.exception("News check error: %s", exc)
            await asyncio.sleep(900)  # every 15 minutes

    async def _run_news_check(self) -> None:
        """Fetch ESPN NBA news and injury reports, post new items to configured channels."""
        news_articles = await self.fetcher.get_news(limit=8)
        injuries      = await self.fetcher.get_injuries()

        for guild in self.bot.guilds:
            guild_id   = guild.id
            channel_id: Optional[int] = await self.config.guild_from_id(guild_id).news_channel()
            if not channel_id:
                continue
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                continue

            posted_ids = self._news_posted.get(guild_id, set())
            old_inj    = self._injury_snapshot.get(guild_id, {})

            # ── Post new news articles ─────────────────────────────────────────
            new_articles = [
                a for a in news_articles
                if a.get("id") and a["id"] not in posted_ids
            ]
            for article in new_articles[:3]:
                try:
                    embed = discord.Embed(
                        title=(article.get("headline") or "NBA News")[:256],
                        description=(article.get("description") or "")[:500] or None,
                        color=discord.Color.orange(),
                        url=article.get("url") or None,
                    )
                    embed.set_author(name="📰 ESPN NBA News")
                    if article.get("image_url"):
                        embed.set_thumbnail(url=article["image_url"])
                    published = article.get("published")
                    if published:
                        try:
                            embed.timestamp = datetime.fromisoformat(
                                published.replace("Z", "+00:00")
                            )
                        except Exception:
                            pass
                    await channel.send(embed=embed)
                    posted_ids.add(article["id"])
                except (discord.Forbidden, discord.HTTPException):
                    pass
                except Exception as exc:
                    log.warning("Failed posting news article: %s", exc)

            # ── Post injury status CHANGES ─────────────────────────────────────
            # get_injuries() returns {team_abbr: [{"name", "status", "description"}]}
            # Flatten to {player_name: status} and keep a detail map for display.
            new_inj: Dict[str, str] = {}
            inj_detail: Dict[str, Dict] = {}
            for team_abbr_key, players in (injuries or {}).items():
                for player_info in players:
                    pname  = player_info.get("name", "")
                    status = player_info.get("status", "Active")
                    if not pname:
                        continue
                    new_inj[pname] = status
                    inj_detail[pname] = {
                        "team":    team_abbr_key,
                        "comment": player_info.get("description", ""),
                    }

            if old_inj:  # Only compare after we have a baseline snapshot
                changes: List[str] = []
                for pname, new_status in new_inj.items():
                    old_status = old_inj.get(pname)
                    if old_status and old_status != new_status:
                        # Status changed — worth flagging
                        inj_info = inj_detail.get(pname, {})
                        team     = inj_info.get("team", "")
                        comment  = inj_info.get("comment", "")
                        emoji    = "🔴" if new_status in ("Out", "Doubtful") else (
                                   "🟡" if new_status == "Questionable" else "🟢")
                        line = f"{emoji} **{pname}** ({team}): {old_status} → **{new_status}**"
                        if comment:
                            line += f"\n　_{comment[:120]}_"
                        changes.append(line)

                if changes:
                    try:
                        embed = discord.Embed(
                            title="🏥 NBA Injury Report Update",
                            description="\n".join(changes[:10]),
                            color=discord.Color.red(),
                        )
                        embed.set_footer(text="Source: ESPN  ·  Updates every 15 minutes")
                        await channel.send(embed=embed)
                    except (discord.Forbidden, discord.HTTPException):
                        pass
                    except Exception as exc:
                        log.warning("Failed posting injury update: %s", exc)

            self._news_posted[guild_id]       = posted_ids
            self._injury_snapshot[guild_id]   = new_inj

    # ══════════════════════════════════════════════════════════════════════════
    # /economy  commands
    # ══════════════════════════════════════════════════════════════════════════

    @commands.hybrid_group(name="economy", aliases=["eco"], fallback="balance")
    @commands.guild_only()
    async def economy_group(
        self, ctx: commands.Context, user: Optional[discord.Member] = None
    ) -> None:
        """Check your economy balance (or another user's)."""
        target = user or ctx.author
        data   = await self.economy.get_data(ctx.guild.id, target.id)
        bal    = data.get("balance", STARTING_BALANCE)
        w      = data.get("bets_won",  0)
        l      = data.get("bets_lost", 0)
        p      = data.get("bets_push", 0)
        placed = data.get("bets_placed", 0)
        wagered  = data.get("total_wagered",  0.0)
        returned = data.get("total_returned", 0.0)
        profit   = returned - wagered
        win_pct  = f"{w / (w + l) * 100:.1f}%" if (w + l) > 0 else "—"

        embed = discord.Embed(
            title=f"{CURRENCY} Economy — {target.display_name}",
            color=discord.Color.gold(),
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Balance",       value=f"{CURRENCY}**{bal:.0f}**", inline=True)
        embed.add_field(name="Bets Placed",   value=str(placed),                inline=True)
        embed.add_field(name="Record",        value=f"{w}W – {l}L – {p}P",     inline=True)
        embed.add_field(name="Win Rate",      value=win_pct,                    inline=True)
        embed.add_field(name="Total Wagered", value=f"{CURRENCY}{wagered:.0f}", inline=True)
        profit_str = f"+{profit:.0f}" if profit >= 0 else f"{profit:.0f}"
        embed.add_field(name="Profit / Loss", value=f"{CURRENCY}{profit_str}",  inline=True)
        await ctx.send(embed=embed)

    @economy_group.command(name="leaderboard", aliases=["lb"])
    @commands.guild_only()
    async def eco_leaderboard(self, ctx: commands.Context) -> None:
        """Top-100 players by balance with full stats."""
        async with ctx.typing():
            entries = await self.economy.get_leaderboard(ctx.guild)
        if not entries:
            return await ctx.send("No economy data yet. Use `/economy balance` to get started!")
        view = LeaderboardView(entries, ctx.guild, ctx.author.id)
        msg  = await ctx.send(embed=view.build_embed(), view=view)
        view.message = msg

    @economy_group.command(name="transfer")
    @commands.guild_only()
    @app_commands.describe(
        recipient="Who to send money to",
        amount="Amount to transfer (min 1)",
    )
    async def eco_transfer(
        self, ctx: commands.Context, recipient: discord.Member, amount: float
    ) -> None:
        """Transfer 💰 to another server member."""
        if recipient.bot:
            return await ctx.send("❌ You can't transfer to a bot.", ephemeral=True)
        if recipient.id == ctx.author.id:
            return await ctx.send("❌ You can't transfer to yourself.", ephemeral=True)
        if amount < 1:
            return await ctx.send("❌ Minimum transfer is 1.", ephemeral=True)

        view = ConfirmView(ctx.author.id, timeout=30)
        msg  = await ctx.send(
            f"Transfer {CURRENCY}**{amount:.0f}** to **{recipient.display_name}**?",
            view=view,
        )
        await view.wait()
        if not view.confirmed:
            return await msg.edit(content="Transfer cancelled.", view=None)

        ok = await self.economy.deduct(ctx.guild.id, ctx.author.id, amount)
        if not ok:
            return await msg.edit(content="❌ Insufficient balance.", view=None)
        await self.economy.add(ctx.guild.id, recipient.id, amount)

        embed = discord.Embed(title="💸 Transfer Complete", color=discord.Color.green())
        embed.add_field(name="From",   value=ctx.author.mention,            inline=True)
        embed.add_field(name="To",     value=recipient.mention,             inline=True)
        embed.add_field(name="Amount", value=f"{CURRENCY}**{amount:.0f}**", inline=True)
        await msg.edit(content=None, embed=embed, view=None)

    # ══════════════════════════════════════════════════════════════════════════
    # /bet  commands
    # ══════════════════════════════════════════════════════════════════════════

    @commands.hybrid_group(name="bet")
    @commands.guild_only()
    async def bet_group(self, ctx: commands.Context) -> None:
        """NBA betting commands."""
        await ctx.send_help(ctx.command)

    @bet_group.command(name="games")
    @app_commands.describe(date="Date in YYYYMMDD format (default: today)")
    async def bet_games(self, ctx: commands.Context, date: Optional[str] = None) -> None:
        """Browse today's NBA schedule with live scores."""
        async with ctx.typing():
            games = await self.fetcher.get_games(force=bool(date))

        if not games:
            return await ctx.send("No NBA games found for today. Check back later!")

        view = GamesView(games, ctx.author.id, cog=self)
        msg  = await ctx.send(embed=view.build_embed(), view=view)
        view.message = msg

    @bet_group.command(name="odds")
    @app_commands.describe(game="Game abbreviation or number from /bet games (default: first available)")
    async def bet_odds(self, ctx: commands.Context, game: Optional[str] = None) -> None:
        """Show the full odds board for a game — spreads, moneyline, totals, injuries, public action."""
        async with ctx.typing():
            games = await self.fetcher.get_games()

        _BETTABLE_STATES = {"STATUS_SCHEDULED", "STATUS_PREGAME"}
        upcoming = [
            g for g in games
            if not g.get("completed") and g.get("state", "") in _BETTABLE_STATES
        ]
        if not upcoming:
            return await ctx.send("No upcoming games available right now.")

        target_game = None
        if game:
            game_lower = game.lower()
            for g in upcoming:
                if (
                    game_lower in g.get("home_abbr", "").lower()
                    or game_lower in g.get("away_abbr", "").lower()
                    or game_lower in g.get("home_team", "").lower()
                    or game_lower in g.get("away_team", "").lower()
                ):
                    target_game = g
                    break
            if target_game is None and game.isdigit():
                idx = int(game) - 1
                if 0 <= idx < len(upcoming):
                    target_game = upcoming[idx]
        if target_game is None:
            target_game = upcoming[0]

        full = await self.fetcher.get_game_with_odds(
            target_game["event_id"],
            guild_id=ctx.guild.id,
            bets_manager=self.bets,
        )
        if not full:
            return await ctx.send("Could not fetch odds for that game.")

        view = OddsView(
            full, ctx.author.id,
            cog=self,
            guild_id=ctx.guild.id,
            event_id=target_game["event_id"],
        )
        msg  = await ctx.send(embed=view.build_embed(), view=view)
        view.message = msg

    @bet_group.command(name="place")
    async def bet_place(self, ctx: commands.Context) -> None:
        """Open the interactive bet placement menu."""
        async with ctx.typing():
            games   = await self.fetcher.get_games()
            balance = await self.economy.get_balance(ctx.guild.id, ctx.author.id)

        # ── Only show games that haven't started yet ───────────────────────────
        _BETTABLE_STATES = {"STATUS_SCHEDULED", "STATUS_PREGAME"}
        upcoming = [
            g for g in games
            if not g.get("completed") and g.get("state", "") in _BETTABLE_STATES
        ]
        if not upcoming:
            return await ctx.send(
                "🔒 No upcoming NBA games available for betting right now. "
                "All games today have either started or finished — try again when new games are scheduled!"
            )

        # ── Bet limit checks ──────────────────────────────────────────────────
        cfg        = await self.config.guild(ctx.guild).all()
        max_daily  = cfg.get("max_daily_bets", DEFAULT_MAX_DAILY_BETS)
        bets_today = self.bets.get_bets_placed_today(ctx.guild.id, ctx.author.id)
        if bets_today >= max_daily:
            return await ctx.send(
                f"🔒 You've reached the daily limit of **{max_daily}** bets. "
                f"Limits reset at midnight UTC."
            )

        max_pct = cfg.get("max_bet_pct", DEFAULT_MAX_BET_PCT)
        max_bet = round(balance * max_pct, 2) if max_pct > 0 else 0.0

        # ── Build per-game restriction maps — block only the specific type/player ──
        # h2h/spreads/totals block the whole bet-type for that game (can't bet both sides).
        # Player props block the specific player only (other players are still available).
        _OUTCOME_TYPES = {"h2h", "spreads", "totals"}
        pending_bets   = self.bets.get_user_bets(ctx.guild.id, ctx.author.id, status="pending")

        locked_types:   Dict[str, Set[str]] = {}
        locked_players: Dict[str, Set[str]] = {}

        for b in pending_bets:
            event_id = b.get("event_id")
            if not event_id:
                continue  # skip parlays (handled separately via legs)
            bet_type = b.get("bet_type", "")
            if bet_type in _OUTCOME_TYPES:
                locked_types.setdefault(event_id, set()).add(bet_type)
            elif bet_type == "player_props":
                sel   = b.get("selection", "")
                pname = sel.split("|")[0] if sel else ""
                if pname:
                    locked_players.setdefault(event_id, set()).add(pname)

        view = BetFlowView(
            self, ctx.author.id, ctx.guild.id, upcoming, balance,
            max_bet=max_bet,
            locked_types=locked_types,
            locked_players=locked_players,
        )
        msg  = await ctx.send(embed=view._build_embed(), view=view)
        view.message = msg

    @bet_group.command(name="parlay")
    async def bet_parlay(self, ctx: commands.Context) -> None:
        """Build a multi-leg parlay (2–5 legs). Combined odds multiply together."""
        async with ctx.typing():
            games   = await self.fetcher.get_games()
            balance = await self.economy.get_balance(ctx.guild.id, ctx.author.id)

        _BETTABLE_STATES = {"STATUS_SCHEDULED", "STATUS_PREGAME"}
        upcoming = [
            g for g in games
            if not g.get("completed") and g.get("state", "") in _BETTABLE_STATES
        ]
        if not upcoming:
            return await ctx.send(
                "🔒 No upcoming NBA games available for parlays right now."
            )

        # ── Daily limit check ─────────────────────────────────────────────────
        cfg        = await self.config.guild(ctx.guild).all()
        max_daily  = cfg.get("max_daily_bets", DEFAULT_MAX_DAILY_BETS)
        bets_today = self.bets.get_bets_placed_today(ctx.guild.id, ctx.author.id)
        if bets_today >= max_daily:
            return await ctx.send(
                f"🔒 You've reached the daily limit of **{max_daily}** bets. "
                f"Limits reset at midnight UTC."
            )

        max_pct = cfg.get("max_bet_pct", DEFAULT_MAX_BET_PCT)
        max_bet = round(balance * max_pct, 2) if max_pct > 0 else 0.0

        view = ParlayBuilderView(self, ctx.author.id, ctx.guild.id, upcoming, balance, max_bet=max_bet)
        msg  = await ctx.send(embed=view._build_embed(), view=view)
        view.message = msg

    @bet_group.command(name="mybets")
    async def bet_mybets(self, ctx: commands.Context) -> None:
        """View your active (pending) bets."""
        bets = self.bets.get_user_bets(ctx.guild.id, ctx.author.id, "pending")
        if not bets:
            return await ctx.send("You have no pending bets. Use `/bet place` to get started!")
        view = MyBetsView(bets, self, ctx.author.id, ctx.guild.id,
                          title="📋 My Active Bets")
        msg  = await ctx.send(embed=view.build_embed(), view=view)
        view.message = msg

    @bet_group.command(name="history")
    @app_commands.describe(user="User to view history for (default: yourself)")
    async def bet_history(
        self, ctx: commands.Context, user: Optional[discord.Member] = None
    ) -> None:
        """View your full bet history (last 50 bets)."""
        target = user or ctx.author
        bets   = self.bets.get_user_bets(ctx.guild.id, target.id, limit=50)
        if not bets:
            return await ctx.send(
                f"{'You have' if target == ctx.author else f'{target.display_name} has'} no bet history yet."
            )
        view = MyBetsView(bets, self, ctx.author.id, ctx.guild.id,
                          title=f"📜 Bet History — {target.display_name}")
        msg  = await ctx.send(embed=view.build_embed(), view=view)
        view.message = msg

    # ══════════════════════════════════════════════════════════════════════════
    # /admin  commands  (admin-only)
    # ══════════════════════════════════════════════════════════════════════════

    @commands.hybrid_group(name="admin")
    @commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @admin_only()
    async def admin_group(self, ctx: commands.Context) -> None:
        """Admin commands for NBABetting."""
        await ctx.send_help(ctx.command)

    # ── Economy management ────────────────────────────────────────────────────

    @admin_group.command(name="add")
    @app_commands.describe(user="Target user", amount="Amount to add")
    async def admin_add(
        self, ctx: commands.Context, user: discord.Member, amount: float
    ) -> None:
        """Add 💰 to a user's balance."""
        if amount <= 0:
            return await ctx.send("❌ Amount must be positive.", ephemeral=True)
        new_bal = await self.economy.add(ctx.guild.id, user.id, amount)
        await ctx.send(
            f"✅ Added {CURRENCY}**{amount:.0f}** to **{user.display_name}**. "
            f"New balance: {CURRENCY}**{new_bal:.0f}**"
        )

    @admin_group.command(name="remove")
    @app_commands.describe(user="Target user", amount="Amount to remove")
    async def admin_remove(
        self, ctx: commands.Context, user: discord.Member, amount: float
    ) -> None:
        """Remove 💰 from a user's balance (won't go below 0)."""
        if amount <= 0:
            return await ctx.send("❌ Amount must be positive.", ephemeral=True)
        cur_bal = await self.economy.get_balance(ctx.guild.id, user.id)
        deduct  = min(amount, cur_bal)
        new_bal = await self.economy.add(ctx.guild.id, user.id, -deduct)
        await ctx.send(
            f"✅ Removed {CURRENCY}**{deduct:.0f}** from **{user.display_name}**. "
            f"New balance: {CURRENCY}**{new_bal:.0f}**"
        )

    @admin_group.command(name="set")
    @app_commands.describe(user="Target user", amount="New balance")
    async def admin_set(
        self, ctx: commands.Context, user: discord.Member, amount: float
    ) -> None:
        """Set a user's balance to an exact value."""
        if amount < 0:
            return await ctx.send("❌ Balance cannot be negative.", ephemeral=True)
        await self.economy.set_balance(ctx.guild.id, user.id, amount)
        await ctx.send(
            f"✅ Set **{user.display_name}**'s balance to {CURRENCY}**{amount:.0f}**."
        )

    @admin_group.command(name="reseteco")
    async def admin_reseteco(self, ctx: commands.Context) -> None:
        """Reset ALL members' balances AND clear all bet history."""
        view = ConfirmView(ctx.author.id, timeout=30)
        msg  = await ctx.send(
            f"⚠️ **Full economy reset** — this will:\n"
            f"• Reset every member's balance to {CURRENCY}**{STARTING_BALANCE:.0f}**\n"
            f"• **Delete all bet history** (active and settled)\n\n"
            f"This cannot be undone. Continue?",
            view=view,
        )
        await view.wait()
        if not view.confirmed:
            return await msg.edit(content="Reset cancelled.", view=None)
        self.bets.clear_all_bets(ctx.guild.id)
        count = await self.economy.reset_all_balances(ctx.guild)
        await msg.edit(
            content=(
                f"✅ Reset {count} member balance(s) to {CURRENCY}**{STARTING_BALANCE:.0f}**"
                f" and cleared all bet history."
            ),
            view=None,
        )

    @admin_group.command(name="resetbets")
    async def admin_resetbets(self, ctx: commands.Context) -> None:
        """Clear ALL bet history for this server without touching balances."""
        view = ConfirmView(ctx.author.id, timeout=30)
        msg  = await ctx.send(
            "⚠️ This will **permanently delete all bet history** "
            "(active and settled) for this server.\n"
            "Member balances are **not** affected. Continue?",
            view=view,
        )
        await view.wait()
        if not view.confirmed:
            return await msg.edit(content="Reset cancelled.", view=None)
        active_cleared, _ = self.bets.clear_all_bets(ctx.guild.id)
        await msg.edit(
            content=f"✅ Cleared all bet history ({active_cleared} active bet(s) removed).",
            view=None,
        )

    @admin_group.command(name="resetstats")
    async def admin_resetstats(self, ctx: commands.Context) -> None:
        """Reset all betting stats (W/L record, wagered, returned) for everyone."""
        view = ConfirmView(ctx.author.id, timeout=30)
        msg  = await ctx.send(
            "⚠️ This will clear **all betting stats** (W/L, wagered, returned) "
            "for every member. Balances are **not** affected. Continue?",
            view=view,
        )
        await view.wait()
        if not view.confirmed:
            return await msg.edit(content="Reset cancelled.", view=None)
        count = await self.economy.reset_all_stats(ctx.guild)
        await msg.edit(
            content=f"✅ Cleared betting stats for {count} member(s).",
            view=None,
        )

    @admin_group.command(name="lookup")
    @app_commands.describe(user="User to inspect")
    async def admin_lookup(self, ctx: commands.Context, user: discord.Member) -> None:
        """Admin view of a user's full economy data and recent bets."""
        data = await self.economy.get_data(ctx.guild.id, user.id)
        bets = self.bets.get_user_bets(ctx.guild.id, user.id, limit=5)

        embed = discord.Embed(
            title=f"🔍 Admin Lookup — {user.display_name}", color=discord.Color.blurple()
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="Balance",        value=f"{CURRENCY}{data.get('balance', 0):.0f}",       inline=True)
        embed.add_field(name="Bets Placed",    value=str(data.get("bets_placed", 0)),                  inline=True)
        embed.add_field(
            name="Record",
            value=f"{data.get('bets_won',0)}W – {data.get('bets_lost',0)}L – {data.get('bets_push',0)}P",
            inline=True,
        )
        embed.add_field(name="Total Wagered",  value=f"{CURRENCY}{data.get('total_wagered',0):.0f}",  inline=True)
        embed.add_field(name="Total Returned", value=f"{CURRENCY}{data.get('total_returned',0):.0f}", inline=True)
        profit = data.get("total_returned", 0.0) - data.get("total_wagered", 0.0)
        p_str  = f"+{profit:.0f}" if profit >= 0 else f"{profit:.0f}"
        embed.add_field(name="Net P/L", value=f"{CURRENCY}{p_str}", inline=True)

        if bets:
            def _bet_label(b: dict) -> str:
                if b.get("bet_type") == "parlay":
                    legs = b.get("legs", [])
                    sel  = f"{len(legs)}-leg parlay"
                else:
                    sel = b.get("selection", "?")
                    if b.get("bet_type") == "player_props":
                        sel = fmt_prop_selection(sel)
                return f"`{b['id']}` {sel} ({b['status']}) {CURRENCY}{b['stake']:.0f}"
            recent = "\n".join(_bet_label(b) for b in bets[:5])
            embed.add_field(name="Last 5 Bets", value=recent, inline=False)

        await ctx.send(embed=embed)

    # ── Settlement control ────────────────────────────────────────────────────

    @admin_group.command(name="settle")
    async def admin_settle(self, ctx: commands.Context) -> None:
        """Force-run bet settlement right now (don't wait for the 10-minute loop)."""
        async with ctx.typing():
            await self._run_settlement()
        await ctx.send("✅ Settlement cycle completed.")

    @admin_group.command(name="voidgame")
    @app_commands.describe(event_id="ESPN Event ID to void all bets for")
    async def admin_voidgame(self, ctx: commands.Context, event_id: str) -> None:
        """Void all pending bets for a specific game and refund stakes."""
        pending   = self.bets.get_all_pending(ctx.guild.id)
        game_bets = [
            b for b in pending
            if b.get("event_id") == event_id
            or any(leg.get("event_id") == event_id for leg in b.get("legs", []))
        ]
        if not game_bets:
            return await ctx.send(f"No pending bets found for event `{event_id}`.")

        view = ConfirmView(ctx.author.id, timeout=30)
        msg  = await ctx.send(
            f"⚠️ Void **{len(game_bets)}** pending bet(s) for event `{event_id}` and refund all stakes?",
            view=view,
        )
        await view.wait()
        if not view.confirmed:
            return await msg.edit(content="Void cancelled.", view=None)

        count = 0
        for bet in game_bets:
            self.bets.settle_bet(ctx.guild.id, bet["id"], "push", bet["stake"])
            await self.economy.add(ctx.guild.id, int(bet["user_id"]), bet["stake"])
            await self.economy.record_push(ctx.guild.id, int(bet["user_id"]), bet["stake"])
            count += 1

        await msg.edit(content=f"✅ Voided {count} bet(s). All stakes refunded.", view=None)

    @admin_group.command(name="voidbet")
    @app_commands.describe(bet_id="Specific Bet ID to void and refund")
    async def admin_voidbet(self, ctx: commands.Context, bet_id: str) -> None:
        """Void a single bet by ID and refund the stake to the bettor."""
        bet_id = bet_id.upper().strip()
        bet    = self.bets.get_bet(ctx.guild.id, bet_id)
        if not bet:
            return await ctx.send(f"❌ Bet `{bet_id}` not found.", ephemeral=True)
        if bet["status"] != "pending":
            return await ctx.send(
                f"❌ Bet `{bet_id}` is already **{bet['status']}** — only pending bets can be voided.",
                ephemeral=True,
            )

        user_id = int(bet["user_id"])
        if bet.get("bet_type") == "parlay":
            legs = bet.get("legs", [])
            sel_display = f"{len(legs)}-leg parlay"
        elif bet.get("bet_type") == "player_props":
            sel_display = fmt_prop_selection(bet.get("selection", ""))
        else:
            sel_display = bet.get("selection", "?")

        view = ConfirmView(ctx.author.id, timeout=30)
        msg  = await ctx.send(
            f"⚠️ Void bet `{bet_id}` (**{sel_display}**, {CURRENCY}{bet['stake']:.0f}) "
            f"and refund the stake to <@{user_id}>?",
            view=view,
        )
        await view.wait()
        if not view.confirmed:
            return await msg.edit(content="Void cancelled.", view=None)

        ok = self.bets.settle_bet(ctx.guild.id, bet_id, "push", bet["stake"])
        if not ok:
            return await msg.edit(
                content="❌ Could not void — bet may have already settled.", view=None
            )

        await self.economy.add(ctx.guild.id, user_id, bet["stake"])
        await self.economy.record_push(ctx.guild.id, user_id, bet["stake"])
        await msg.edit(
            content=f"✅ Bet `{bet_id}` voided. {CURRENCY}**{bet['stake']:.0f}** refunded to <@{user_id}>.",
            view=None,
        )

    # ── Config ────────────────────────────────────────────────────────────────

    @admin_group.command(name="setrole")
    @app_commands.describe(role="Role that can use admin commands (leave blank to require Administrator)")
    async def admin_setrole(
        self, ctx: commands.Context, role: Optional[discord.Role] = None
    ) -> None:
        """Set (or clear) the admin role for this server's betting commands."""
        await self.config.guild(ctx.guild).admin_role.set(role.id if role else None)
        if role:
            await ctx.send(f"✅ Admin role set to **{role.name}**.")
        else:
            await ctx.send("✅ Admin role cleared. Only server administrators can use admin commands.")

    @admin_group.command(name="setlimits")
    @app_commands.describe(
        max_daily_bets="Max bets per user per day (0 = unlimited)",
        max_bet_pct="Max single bet as % of balance, e.g. 50 = 50% (0 = unlimited)",
    )
    async def admin_setlimits(
        self,
        ctx: commands.Context,
        max_daily_bets: Optional[int] = None,
        max_bet_pct: Optional[float] = None,
    ) -> None:
        """Configure per-user betting limits for this server."""
        changed = []
        if max_daily_bets is not None:
            if max_daily_bets < 0:
                return await ctx.send("❌ max_daily_bets must be 0 or greater.", ephemeral=True)
            await self.config.guild(ctx.guild).max_daily_bets.set(max_daily_bets)
            label = "unlimited" if max_daily_bets == 0 else str(max_daily_bets)
            changed.append(f"Max daily bets → **{label}**")
        if max_bet_pct is not None:
            if not (0 <= max_bet_pct <= 100):
                return await ctx.send("❌ max_bet_pct must be between 0 and 100.", ephemeral=True)
            frac = max_bet_pct / 100.0
            await self.config.guild(ctx.guild).max_bet_pct.set(frac)
            label = "unlimited" if max_bet_pct == 0 else f"{max_bet_pct:.0f}% of balance"
            changed.append(f"Max single bet → **{label}**")
        if not changed:
            cfg = await self.config.guild(ctx.guild).all()
            mdb = cfg.get("max_daily_bets", DEFAULT_MAX_DAILY_BETS)
            mbp = cfg.get("max_bet_pct", DEFAULT_MAX_BET_PCT) * 100
            return await ctx.send(
                f"**Current limits:**\n"
                f"• Max daily bets: **{mdb if mdb > 0 else 'unlimited'}**\n"
                f"• Max single bet: **{f'{mbp:.0f}% of balance' if mbp > 0 else 'unlimited'}**\n\n"
                f"Use `/admin setlimits max_daily_bets:<n> max_bet_pct:<pct>` to change."
            )
        await ctx.send("✅ Limits updated:\n" + "\n".join(f"• {c}" for c in changed))

    @admin_group.command(name="notifychannel")
    @app_commands.describe(channel="Channel for settlement announcements (leave blank to disable)")
    async def admin_notifychannel(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None
    ) -> None:
        """Set a channel to announce bet results publicly (in addition to DMs)."""
        await self.config.guild(ctx.guild).notify_channel.set(channel.id if channel else None)
        if channel:
            await ctx.send(f"✅ Settlement announcements will post in {channel.mention}.")
        else:
            await ctx.send("✅ Settlement channel cleared. Results will only be sent via DM.")

    @admin_group.command(name="setnewschannel")
    @app_commands.describe(channel="Channel for ESPN NBA news & injury updates (leave blank to disable)")
    async def admin_setnewschannel(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None
    ) -> None:
        """Set a channel to receive ESPN NBA news headlines and injury updates every 15 minutes."""
        await self.config.guild(ctx.guild).news_channel.set(channel.id if channel else None)
        if channel:
            # Reset cached state so it posts fresh articles to the new channel
            self._news_posted.pop(ctx.guild.id, None)
            self._injury_snapshot.pop(ctx.guild.id, None)
            await ctx.send(
                f"✅ ESPN NBA news & injury updates will post in {channel.mention}.\n"
                f"New articles and injury status changes will appear every ~15 minutes."
            )
        else:
            await ctx.send("✅ News channel cleared. ESPN updates disabled for this server.")

    @admin_group.command(name="newsnow")
    async def admin_newsnow(self, ctx: commands.Context) -> None:
        """Force an immediate ESPN news check and post to the configured news channel."""
        channel_id: Optional[int] = await self.config.guild(ctx.guild).news_channel()
        if not channel_id:
            return await ctx.send(
                "❌ No news channel configured. Use `/admin setnewschannel` first.",
                ephemeral=True,
            )
        async with ctx.typing():
            await self._run_news_check()
        await ctx.send("✅ News check complete — new items (if any) have been posted.")

    @admin_group.command(name="status")
    async def admin_status(self, ctx: commands.Context) -> None:
        """Show current cog configuration and pending bet count."""
        cfg         = await self.config.guild(ctx.guild).all()
        role        = ctx.guild.get_role(cfg["admin_role"]) if cfg.get("admin_role") else None
        notify_ch   = ctx.guild.get_channel(cfg["notify_channel"]) if cfg.get("notify_channel") else None
        news_ch     = ctx.guild.get_channel(cfg["news_channel"]) if cfg.get("news_channel") else None
        pending_cnt = len(self.bets.get_all_pending(ctx.guild.id))

        embed = discord.Embed(title="⚙️ NBABetting Status", color=discord.Color.blurple())
        embed.add_field(name="Odds Source",     value="🟢 ESPN (injury-adjusted)", inline=True)
        embed.add_field(name="Admin Role",      value=role.mention if role else "Admins only", inline=True)
        embed.add_field(name="Notify Channel",  value=notify_ch.mention if notify_ch else "DMs only", inline=True)
        embed.add_field(name="News Channel",    value=news_ch.mention if news_ch else "Disabled", inline=True)
        embed.add_field(name="Pending Bets",    value=str(pending_cnt), inline=True)

        settle_task  = self._settlement_task
        settle_ok    = settle_task is not None and not settle_task.done()
        news_task    = self._news_task
        news_ok      = news_task is not None and not news_task.done()
        embed.add_field(
            name="Settlement Loop",
            value=f"{'🟢 Running' if settle_ok else '🔴 Stopped'} (every 10 min)",
            inline=True,
        )
        embed.add_field(
            name="News Loop",
            value=f"{'🟢 Running' if news_ok else '🔴 Stopped'} (every 15 min)",
            inline=True,
        )
        embed.set_footer(text="Use /admin settle to trigger settlement  ·  /admin newsnow for news check")
        await ctx.send(embed=embed)
