"""nbabetting.py – Main NBABetting cog: commands, economy, auto-settlement."""
from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

import discord
from discord import app_commands
from redbot.core import Config, commands
from redbot.core.bot import Red

from .data import BetsManager
from .economy import CURRENCY, STARTING_BALANCE, Economy
from .odds import OddsFetcher, calc_profit, evaluate_bet, fmt_odds
from .views import (
    BetFlowView,
    ConfirmView,
    GamesView,
    LeaderboardView,
    MyBetsView,
)

log = logging.getLogger("red.jaffar-cogs.nbabetting")

ADMIN_SERVER_ID = 1440962506796433519


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
    """NBA betting with live odds, economy, and auto-settlement. Slash-command first."""

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
        )

        # ── Helpers ───────────────────────────────────────────────────────────
        self.economy = Economy(self.config, bot)
        self.fetcher = OddsFetcher()
        self.bets    = BetsManager(self)

        self._settlement_task: Optional[asyncio.Task] = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def cog_load(self) -> None:
        self._settlement_task = asyncio.create_task(self._settlement_loop())

    async def cog_unload(self) -> None:
        if self._settlement_task:
            self._settlement_task.cancel()
            try:
                await self._settlement_task
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

            for bet in pending:
                game = completed_by_id.get(bet["event_id"])
                if not game:
                    continue
                if game.get("home_score") is None or game.get("away_score") is None:
                    continue

                result = evaluate_bet(
                    bet_type=bet["bet_type"],
                    selection=bet["selection"],
                    point=bet.get("point"),
                    home_team=bet["home_team"],
                    away_team=bet["away_team"],
                    home_score=game["home_score"],
                    away_score=game["away_score"],
                )

                user_id = int(bet["user_id"])
                stake   = bet["stake"]
                profit  = bet["potential_payout"]

                if result == "won":
                    payout = stake + profit
                    await self.economy.add(guild_id, user_id, payout)
                    await self.economy.record_win(guild_id, user_id, profit)
                elif result == "push":
                    payout = stake
                    await self.economy.add(guild_id, user_id, payout)
                    await self.economy.record_push(guild_id, user_id)
                else:   # lost
                    payout = 0.0
                    await self.economy.record_loss(guild_id, user_id)

                self.bets.settle_bet(guild_id, bet["id"], result, payout)
                await self._notify_user(guild_id, user_id, bet, result, payout)

    async def _notify_user(
        self,
        guild_id: int,
        user_id: int,
        bet: dict,
        result: str,
        payout: float,
    ) -> None:
        """DM the user their bet result."""
        user = self.bot.get_user(user_id)
        if not user:
            return
        emoji = {"won": "✅", "lost": "❌", "push": "🔄"}.get(result, "❓")
        color = {
            "won":  discord.Color.green(),
            "lost": discord.Color.red(),
            "push": discord.Color.gold(),
        }.get(result, discord.Color.greyple())

        embed = discord.Embed(
            title=f"{emoji} Bet Settled — {result.upper()}",
            color=color,
        )
        embed.add_field(name="Bet ID",   value=f"`{bet['id']}`",                        inline=True)
        embed.add_field(name="Game",     value=f"{bet['away_team']} @ {bet['home_team']}",inline=False)
        embed.add_field(name="Your Pick",value=f"{bet['selection']}  ({fmt_odds(bet['odds'])})",inline=True)
        embed.add_field(name="Stake",    value=f"{CURRENCY}{bet['stake']:.0f}",           inline=True)
        if result == "won":
            embed.add_field(name="You Won!", value=f"{CURRENCY}**{payout:.0f}**", inline=True)
        elif result == "push":
            embed.add_field(name="Push",     value="Stake returned.", inline=True)
        try:
            await user.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

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
        wagered   = data.get("total_wagered",  0.0)
        returned  = data.get("total_returned", 0.0)
        profit    = returned - wagered
        win_pct   = f"{w / (w + l) * 100:.1f}%" if (w + l) > 0 else "—"

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
        embed.add_field(name="Profit / Loss", value=f"{CURRENCY}{profit_str}", inline=True)
        await ctx.send(embed=embed)

    @economy_group.command(name="leaderboard", aliases=["lb"])
    @commands.guild_only()
    async def eco_leaderboard(self, ctx: commands.Context) -> None:
        """Top-100 players by balance with full stats."""
        async with ctx.typing():
            entries = await self.economy.get_leaderboard(ctx.guild)
        if not entries:
            return await ctx.send("No economy data yet. Use `/economy balance` to get started!")
        view    = LeaderboardView(entries, ctx.guild, ctx.author.id)
        msg     = await ctx.send(embed=view.build_embed(), view=view)
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

        ok = await self.economy.deduct(ctx.guild.id, ctx.author.id, amount)
        if not ok:
            return await ctx.send("❌ Insufficient balance.", ephemeral=True)
        await self.economy.add(ctx.guild.id, recipient.id, amount)

        embed = discord.Embed(title="💸 Transfer Complete", color=discord.Color.green())
        embed.add_field(name="From",   value=ctx.author.mention,   inline=True)
        embed.add_field(name="To",     value=recipient.mention,    inline=True)
        embed.add_field(name="Amount", value=f"{CURRENCY}**{amount:.0f}**", inline=True)
        await ctx.send(embed=embed)

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

        view = GamesView(games, ctx.author.id)
        msg  = await ctx.send(embed=view.build_embed(), view=view)
        view.message = msg

    @bet_group.command(name="place")
    async def bet_place(self, ctx: commands.Context) -> None:
        """Open the interactive bet placement menu."""
        async with ctx.typing():
            games   = await self.fetcher.get_games()
            balance = await self.economy.get_balance(ctx.guild.id, ctx.author.id)

        upcoming = [g for g in games if not g.get("completed")]
        if not upcoming:
            return await ctx.send(
                "No upcoming NBA games found right now. Try again when games are scheduled!"
            )

        view = BetFlowView(self, ctx.author.id, upcoming, balance)
        msg  = await ctx.send(embed=view._build_embed(), view=view)
        view.message = msg

    @bet_group.command(name="mybets")
    async def bet_mybets(self, ctx: commands.Context) -> None:
        """View and cancel your active (pending) bets."""
        bets = self.bets.get_user_bets(ctx.guild.id, ctx.author.id, "pending")
        if not bets:
            return await ctx.send("You have no pending bets. Use `/bet place` to get started!")
        view = MyBetsView(bets, self, ctx.author.id, ctx.guild.id,
                          title="📋 My Active Bets", show_cancel=True)
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
                          title=f"📜 Bet History — {target.display_name}",
                          show_cancel=False)
        msg  = await ctx.send(embed=view.build_embed(), view=view)
        view.message = msg

    @bet_group.command(name="cancel")
    @app_commands.describe(bet_id="Bet ID to cancel (use autocomplete)")
    async def bet_cancel(self, ctx: commands.Context, bet_id: str) -> None:
        """Cancel a specific pending bet and get your stake refunded."""
        bet_id = bet_id.upper().strip()
        bet    = self.bets.get_bet(ctx.guild.id, bet_id)
        if not bet:
            return await ctx.send(f"❌ Bet `{bet_id}` not found.", ephemeral=True)
        if bet["user_id"] != str(ctx.author.id):
            return await ctx.send("❌ That's not your bet.", ephemeral=True)
        if bet["status"] != "pending":
            return await ctx.send(
                f"❌ Bet `{bet_id}` is already **{bet['status']}** and cannot be cancelled.",
                ephemeral=True,
            )

        view = ConfirmView(ctx.author.id, timeout=30)
        msg  = await ctx.send(
            f"Cancel bet `{bet_id}` (**{bet['selection']}**,  "
            f"{CURRENCY}{bet['stake']:.0f} stake) and get refunded?",
            view=view,
        )
        await view.wait()
        if not view.confirmed:
            return await msg.edit(content="Cancellation aborted.", view=None)

        cancelled = self.bets.cancel_bet(ctx.guild.id, bet_id)
        if not cancelled:
            return await msg.edit(content="❌ Could not cancel — bet may have already settled.", view=None)

        await self.economy.add(ctx.guild.id, ctx.author.id, cancelled["stake"])
        await msg.edit(
            content=f"✅ Bet `{bet_id}` cancelled. {CURRENCY}**{cancelled['stake']:.0f}** refunded.",
            view=None,
        )

    @bet_cancel.autocomplete("bet_id")
    async def _autocomplete_bet_id(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        bets = self.bets.get_user_bets(interaction.guild_id, interaction.user.id, "pending")
        cur  = current.upper()
        return [
            app_commands.Choice(
                name=f"[{b['id']}] {b['away_team']} @ {b['home_team']} — {b['selection']}  ({fmt_odds(b['odds'])})",
                value=b["id"],
            )
            for b in bets
            if cur in b["id"]
        ][:25]

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
        """Reset ALL members' balances to 100💰 (asks for confirmation)."""
        view = ConfirmView(ctx.author.id, timeout=30)
        msg  = await ctx.send(
            f"⚠️ This will reset **every member's balance** to {CURRENCY}**{STARTING_BALANCE:.0f}**.\n"
            "Bet history and stats are **not** affected. Continue?",
            view=view,
        )
        await view.wait()
        if not view.confirmed:
            return await msg.edit(content="Reset cancelled.", view=None)
        count = await self.economy.reset_all_balances(ctx.guild)
        await msg.edit(
            content=f"✅ Reset {count} member balance(s) to {CURRENCY}**{STARTING_BALANCE:.0f}**.",
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
        embed.add_field(name="Balance",       value=f"{CURRENCY}{data.get('balance', 0):.0f}", inline=True)
        embed.add_field(name="Bets Placed",   value=str(data.get("bets_placed", 0)),           inline=True)
        embed.add_field(name="Record",
            value=f"{data.get('bets_won',0)}W – {data.get('bets_lost',0)}L – {data.get('bets_push',0)}P",
            inline=True)
        embed.add_field(name="Total Wagered", value=f"{CURRENCY}{data.get('total_wagered',0):.0f}", inline=True)
        embed.add_field(name="Total Returned",value=f"{CURRENCY}{data.get('total_returned',0):.0f}",inline=True)

        if bets:
            recent = "\n".join(
                f"`{b['id']}` {b['selection']} ({b['status']}) {CURRENCY}{b['stake']:.0f}"
                for b in bets[:5]
            )
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
        pending = self.bets.get_all_pending(ctx.guild.id)
        game_bets = [b for b in pending if b["event_id"] == event_id]
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
            count += 1

        await msg.edit(content=f"✅ Voided {count} bet(s). All stakes refunded.", view=None)

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

    @admin_group.command(name="status")
    async def admin_status(self, ctx: commands.Context) -> None:
        """Show current cog configuration and pending bet count."""
        cfg         = await self.config.guild(ctx.guild).all()
        role        = ctx.guild.get_role(cfg["admin_role"]) if cfg["admin_role"] else None
        channel     = ctx.guild.get_channel(cfg["notify_channel"]) if cfg["notify_channel"] else None
        pending_cnt = len(self.bets.get_all_pending(ctx.guild.id))

        embed = discord.Embed(title="⚙️ NBABetting Status", color=discord.Color.blurple())
        embed.add_field(name="Odds Source",     value="🟢 Auto-generated (ESPN)", inline=True)
        embed.add_field(name="Admin Role",      value=role.mention if role else "Admins only", inline=True)
        embed.add_field(name="Notify Channel",  value=channel.mention if channel else "DMs only", inline=True)
        embed.add_field(name="Pending Bets",    value=str(pending_cnt), inline=True)
        embed.add_field(name="Settlement Loop", value="🟢 Running", inline=True)
        embed.set_footer(text="Settlement runs every 10 minutes. Use /admin settle to trigger immediately.")
        await ctx.send(embed=embed)
