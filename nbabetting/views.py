"""views.py – All Discord UI components for NBABetting."""
from __future__ import annotations

import math
from datetime import datetime
from typing import TYPE_CHECKING, Dict, List, Optional

import discord

from .odds import (
    calc_parlay_odds,
    calc_profit,
    fmt_odds,
    fmt_prop_selection,
    implied_prob,
)

if TYPE_CHECKING:
    from .nbabetting import NBABetting

CURRENCY = "\U0001f4b0"
TYPE_LABELS = {
    "h2h":          "Moneyline",
    "spreads":      "Point Spread",
    "totals":       "Over/Under",
    "player_props": "Player Props",
    "parlay":       "Parlay",
}
STATUS_EMOJI = {
    "pending":   "⏳",
    "won":       "✅",
    "lost":      "❌",
    "push":      "🔄",
    "cancelled": "🚫",
}
PROP_STAT_LABELS = {
    "pts": "Points",
    "reb": "Rebounds",
    "ast": "Assists",
    "pra": "Pts+Reb+Ast",
}


def _discord_ts(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return f"<t:{int(dt.timestamp())}:F>"
    except Exception:
        return iso


# ══════════════════════════════════════════════════════════════════════════════
# Amount modal
# ══════════════════════════════════════════════════════════════════════════════

class AmountModal(discord.ui.Modal, title="Enter Bet Amount"):
    amount: discord.ui.TextInput = discord.ui.TextInput(
        label="Amount",
        placeholder="e.g. 50",
        min_length=1,
        max_length=10,
        required=True,
    )

    def __init__(self, max_balance: float, max_bet: Optional[float] = None) -> None:
        super().__init__()
        self.max_balance = max_balance
        self.max_bet = max_bet if (max_bet is not None and max_bet > 0) else max_balance
        self.effective_max = min(self.max_balance, self.max_bet)
        self.value: Optional[float] = None
        self.modal_interaction: Optional[discord.Interaction] = None
        self.amount.placeholder = f"1 – {int(self.effective_max)}"

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raw = self.amount.value.strip().replace(",", "")
        try:
            v = float(raw)
            if v <= 0:
                raise ValueError("non-positive")
        except ValueError:
            await interaction.response.send_message(
                "❌ Please enter a valid positive number.", ephemeral=True
            )
            return
        if v > self.max_balance:
            await interaction.response.send_message(
                f"❌ Insufficient balance. You have {CURRENCY}**{self.max_balance:.0f}**.",
                ephemeral=True,
            )
            return
        if v > self.max_bet:
            await interaction.response.send_message(
                f"❌ Max single bet is {CURRENCY}**{self.max_bet:.0f}** "
                f"(server limit). Try a lower amount.",
                ephemeral=True,
            )
            return
        self.value = v
        self.modal_interaction = interaction
        await interaction.response.defer()
        self.stop()


# ══════════════════════════════════════════════════════════════════════════════
# Bet placement flow
# ══════════════════════════════════════════════════════════════════════════════

class BetFlowView(discord.ui.View):
    """Multi-step interactive bet placement: game → type → outcome → amount → confirm."""

    def __init__(
        self,
        cog: "NBABetting",
        author_id: int,
        guild_id: int,
        games: List[Dict],
        balance: float,
        max_bet: float = 0.0,
    ) -> None:
        super().__init__(timeout=180)
        self.cog       = cog
        self.author_id = author_id
        self.guild_id  = guild_id
        self.games     = games
        self.balance   = balance
        # 0 = no limit (use full balance); positive = server-configured cap
        self.max_bet: float = max_bet if max_bet > 0 else balance
        self.message: Optional[discord.Message] = None

        # State
        self.selected_game: Optional[Dict]    = None
        self.selected_type: Optional[str]     = None
        self.selected_outcome: Optional[Dict] = None   # {selection, odds, point}
        self.stake: Optional[float]           = None

        self._render_step_game()

    # ── Step builders ──────────────────────────────────────────────────────────

    def _render_step_game(self) -> None:
        self.clear_items()
        options: List[discord.SelectOption] = []
        for g in self.games[:25]:
            label    = f"{g['away_abbr']} @ {g['home_abbr']}"
            away_rec = f" ({g['away_record']})" if g.get("away_record") else ""
            home_rec = f" ({g['home_record']})" if g.get("home_record") else ""
            desc     = f"{g['away_team']}{away_rec} at {g['home_team']}{home_rec}"[:100]
            options.append(
                discord.SelectOption(label=label, description=desc, value=g["event_id"])
            )
        if not options:
            options.append(discord.SelectOption(label="No games available", value="__none__"))
        sel = discord.ui.Select(placeholder="🏀 Select a game…", options=options)
        sel.callback = self._cb_game
        self.add_item(sel)
        self._add_quit(row=1)

    def _render_step_type(self) -> None:
        self.clear_items()
        g    = self.selected_game or {}
        odds = g.get("odds", {})
        props = g.get("player_props", {})
        options: List[discord.SelectOption] = []
        if odds.get("h2h"):
            options.append(discord.SelectOption(
                label="🏆 Moneyline (Match Winner)", value="h2h"))
        if odds.get("spreads"):
            options.append(discord.SelectOption(
                label="📊 Point Spread", value="spreads"))
        if odds.get("totals"):
            options.append(discord.SelectOption(
                label="📈 Total Points (Over / Under)", value="totals"))
        if props:
            options.append(discord.SelectOption(
                label="🎯 Player Props (Pts / Reb / Ast)", value="player_props"))
        if not options:
            options.append(discord.SelectOption(
                label="⚠️ No odds available yet – try closer to tip-off",
                value="__none__",
            ))
        sel = discord.ui.Select(placeholder="📋 Select bet type…", options=options)
        sel.callback = self._cb_type
        self.add_item(sel)
        self._add_back(self._cb_back_to_game, row=1)
        self._add_quit(row=1)

    def _render_step_outcome(self) -> None:
        self.clear_items()
        g        = self.selected_game or {}
        odds     = g.get("odds", {})
        bet_type = self.selected_type
        options: List[discord.SelectOption] = []

        if bet_type == "h2h":
            pub           = (g.get("public_action") or {})
            pub_h2h_total = pub.get("h2h_total", 0)
            for team, price in (odds.get("h2h") or {}).items():
                prob    = int(implied_prob(price) * 100)
                is_home = team == g.get("home_team")
                label   = f"{team}  ({fmt_odds(price)})"[:100]
                if pub_h2h_total >= 10:
                    pub_pct = int((pub.get("home_pct", 0.5) if is_home else pub.get("away_pct", 0.5)) * 100)
                    desc = f"Implied ~{prob}%  ·  {pub_pct}% of server action"
                else:
                    desc = f"Implied win probability: ~{prob}%"
                options.append(discord.SelectOption(
                    label=label, description=desc[:100],
                    value=f"{team}|{price}|None", emoji="🏆"))

        elif bet_type == "spreads":
            for team, d in (odds.get("spreads") or {}).items():
                pt    = d["point"]
                price = d["price"]
                pt_str = f"{'+' if pt > 0 else ''}{pt}"
                label = f"{team}  {pt_str}  ({fmt_odds(price)})"[:100]
                options.append(discord.SelectOption(
                    label=label, value=f"{team}|{price}|{pt}", emoji="📊"))

        elif bet_type == "totals":
            pub          = (g.get("public_action") or {})
            pub_ou_total = pub.get("ou_total", 0)
            for side, d in (odds.get("totals") or {}).items():
                pt    = d["point"]
                price = d["price"]
                label = f"{side} {pt}  ({fmt_odds(price)})"[:100]
                emoji = "📈" if side == "Over" else "📉"
                if pub_ou_total >= 10:
                    pub_pct = int((pub.get("over_pct", 0.5) if side == "Over" else pub.get("under_pct", 0.5)) * 100)
                    desc = f"{pub_pct}% of server action on {side}"
                else:
                    desc = f"{'Over' if side == 'Over' else 'Under'} {pt} total points"
                options.append(discord.SelectOption(
                    label=label, description=desc[:100],
                    value=f"{side}|{price}|{pt}", emoji=emoji))

        elif bet_type == "player_props":
            # Step 1 of props: pick a player
            # Sort: tier 1 first, then tier 2, then tier 3 (stars show at top)
            props = g.get("player_props", {})
            sorted_players = sorted(
                props.items(),
                key=lambda kv: (kv[1].get("tier", 3), kv[0]),
            )
            for pname, pdata in sorted_players[:25]:
                tier = pdata.get("tier", 3)
                is_q = pdata.get("status", "active") == "questionable"
                emoji = "⭐" if tier == 1 else ("🔵" if tier == 2 else "⚪")
                label = (f"⚠️ {pname} (Q)" if is_q else pname)[:100]
                desc  = (
                    f"Pts {pdata['pts']} | Reb {pdata['reb']} | "
                    f"Ast {pdata['ast']} | PRA {pdata['pra']}"
                    + (" | QUESTIONABLE" if is_q else "")
                )[:100]
                options.append(discord.SelectOption(
                    label=label, description=desc,
                    value=f"__player__{pname}", emoji=emoji))

        if not options:
            options.append(discord.SelectOption(
                label="No options available", value="__none__"))

        placeholder = (
            "🎯 Select a player…"
            if bet_type == "player_props"
            else "🎯 Select your pick…"
        )
        sel = discord.ui.Select(placeholder=placeholder, options=options)
        sel.callback = self._cb_outcome
        self.add_item(sel)
        self._add_back(self._cb_back_to_type, row=1)
        self._add_quit(row=1)

    def _render_step_prop_stat(self, player_name: str) -> None:
        """After picking a player, choose which stat to bet on."""
        self.clear_items()
        g     = self.selected_game or {}
        props = g.get("player_props", {})
        pdata = props.get(player_name, {})

        options: List[discord.SelectOption] = []
        is_questionable = pdata.get("status", "active") == "questionable"
        q_suffix = "  ⚠️Q" if is_questionable else ""
        for stat, label in PROP_STAT_LABELS.items():
            line = pdata.get(stat)
            if line is None:
                continue
            for direction in ("Over", "Under"):
                price_key = f"{stat}_{direction.lower()}"
                price   = pdata.get(price_key, -110)
                d_emoji = "📈" if direction == "Over" else "📉"
                val_label = f"{direction} {line} {label} ({fmt_odds(price)}){q_suffix}"[:100]
                options.append(discord.SelectOption(
                    label=val_label,
                    value=f"{player_name}|{stat}|{direction}|{price}|{line}",
                    emoji=d_emoji,
                ))

        if not options:
            options.append(discord.SelectOption(label="No props available", value="__none__"))

        sel = discord.ui.Select(placeholder="📊 Choose stat & direction…", options=options)
        sel.callback = self._cb_prop_stat
        self.add_item(sel)
        self._add_back(self._cb_back_to_type, row=1)
        self._add_quit(row=1)

    def _render_step_confirm(self) -> None:
        self.clear_items()
        outcome = self.selected_outcome or {}
        profit  = calc_profit(self.stake or 0, outcome.get("odds", -110))
        total   = (self.stake or 0) + profit

        confirm = discord.ui.Button(
            label=f"✅  Confirm Bet  ({CURRENCY}{total:.0f} return)",
            style=discord.ButtonStyle.green,
        )
        confirm.callback = self._cb_confirm
        back = discord.ui.Button(label="← Change Amount", style=discord.ButtonStyle.secondary)
        back.callback = self._cb_back_to_outcome
        cancel = discord.ui.Button(label="❌ Cancel", style=discord.ButtonStyle.danger)
        cancel.callback = self._cb_quit
        self.add_item(confirm)
        self.add_item(back)
        self.add_item(cancel)

    # ── Callbacks ──────────────────────────────────────────────────────────────

    async def _cb_game(self, interaction: discord.Interaction) -> None:
        if not await self._check(interaction):
            return
        val = interaction.data["values"][0]
        if val == "__none__":
            return await interaction.response.send_message("No game selected.", ephemeral=True)
        await interaction.response.defer()
        full = await self.cog.fetcher.get_game_with_odds(
            val,
            guild_id=interaction.guild_id,
            bets_manager=self.cog.bets,
        )
        self.selected_game    = full or next((g for g in self.games if g["event_id"] == val), None)
        self.selected_type    = None
        self.selected_outcome = None
        self.stake            = None
        self._render_step_type()
        await self.message.edit(embed=self._build_embed(), view=self)

    async def _cb_type(self, interaction: discord.Interaction) -> None:
        if not await self._check(interaction):
            return
        val = interaction.data["values"][0]
        if val == "__none__":
            return await interaction.response.send_message(
                "No odds available for this game yet. Try again closer to tip-off.",
                ephemeral=True,
            )
        await interaction.response.defer()
        self.selected_type    = val
        self.selected_outcome = None
        self.stake            = None
        self._render_step_outcome()
        await self.message.edit(embed=self._build_embed(), view=self)

    async def _cb_outcome(self, interaction: discord.Interaction) -> None:
        if not await self._check(interaction):
            return
        val = interaction.data["values"][0]
        if val == "__none__":
            return await interaction.response.send_message("No odds available.", ephemeral=True)

        # Player props: first pick is the player, then we show stat selector
        if val.startswith("__player__"):
            player_name = val[len("__player__"):]
            await interaction.response.defer()
            self._render_step_prop_stat(player_name)
            await self.message.edit(embed=self._build_embed(), view=self)
            return

        parts = val.split("|")
        self.selected_outcome = {
            "selection": parts[0],
            "odds":      int(parts[1]),
            "point":     float(parts[2]) if parts[2] != "None" else None,
        }
        # Refresh balance before asking for amount
        self.balance = await self.cog.economy.get_balance(
            interaction.guild_id, self.author_id
        )
        modal = AmountModal(max_balance=self.balance, max_bet=self.max_bet)
        await interaction.response.send_modal(modal)
        timed_out = await modal.wait()
        if timed_out or modal.value is None:
            return
        self.stake = modal.value
        self._render_step_confirm()
        await self.message.edit(embed=self._build_embed(), view=self)

    async def _cb_prop_stat(self, interaction: discord.Interaction) -> None:
        """Callback after the player-stat direction is selected."""
        if not await self._check(interaction):
            return
        val = interaction.data["values"][0]
        if val == "__none__":
            return await interaction.response.send_message("No props available.", ephemeral=True)

        # value format: "PlayerName|stat|direction|price|line"
        parts = val.split("|")
        if len(parts) < 5:
            return await interaction.response.send_message("Malformed option.", ephemeral=True)

        pname, stat, direction, price_str, line_str = (
            parts[0], parts[1], parts[2], parts[3], parts[4]
        )
        # Encode selection as pipe-delimited string for settlement
        selection = f"{pname}|{stat}|{direction}"

        self.selected_outcome = {
            "selection":      selection,
            "odds":           int(price_str),
            "point":          float(line_str),
            "display":        fmt_prop_selection(selection),
        }
        self.balance = await self.cog.economy.get_balance(
            interaction.guild_id, self.author_id
        )
        modal = AmountModal(max_balance=self.balance, max_bet=self.max_bet)
        await interaction.response.send_modal(modal)
        timed_out = await modal.wait()
        if timed_out or modal.value is None:
            return
        self.stake = modal.value
        self._render_step_confirm()
        await self.message.edit(embed=self._build_embed(), view=self)

    async def _cb_confirm(self, interaction: discord.Interaction) -> None:
        """Show a final Yes/No confirmation before deducting balance."""
        if not await self._check(interaction):
            return
        await interaction.response.defer()

        outcome = self.selected_outcome or {}
        stake   = self.stake or 0.0
        profit  = calc_profit(stake, outcome["odds"])
        g       = self.selected_game or {}

        # Show a clear confirmation prompt — money moves after this
        confirm_view = ConfirmView(self.author_id, timeout=60)
        pick_display = outcome.get("display") or outcome.get("selection", "")
        if self.selected_type in ("spreads", "totals") and outcome.get("point") is not None:
            pt = outcome["point"]
            pick_display += f"  ({'+' if pt > 0 else ''}{pt})"

        await self.message.edit(
            content=(
                f"⚠️ **Final confirmation — are you sure?**\n"
                f"**{g.get('away_team')} @ {g.get('home_team')}**\n"
                f"Pick: **{pick_display}** `({fmt_odds(outcome['odds'])})`\n"
                f"Stake: {CURRENCY}**{stake:.0f}**  →  Potential return: {CURRENCY}**{stake + profit:.0f}**\n"
                f"*This cannot be undone once confirmed.*"
            ),
            embed=None,
            view=confirm_view,
        )
        await confirm_view.wait()

        if not confirm_view.confirmed:
            # User cancelled or timed out — restore the confirm screen
            self._render_step_confirm()
            await self.message.edit(
                content=None, embed=self._build_embed(), view=self
            )
            return

        # ── Actually place the bet ─────────────────────────────────────────────
        try:
            ok = await self.cog.economy.deduct(self.guild_id, self.author_id, stake)
            if not ok:
                await self.message.edit(
                    content="❌ Insufficient balance.", embed=None, view=None
                )
                self.stop()
                return

            bet_id = self.cog.bets.place_bet(
                self.guild_id,
                self.author_id,
                event_id=g["event_id"],
                home_team=g["home_team"],
                away_team=g["away_team"],
                game_name=g.get("name", ""),
                commence_time=g.get("commence_time", ""),
                bet_type=self.selected_type,
                selection=outcome["selection"],
                odds=outcome["odds"],
                point=outcome["point"],
                stake=stake,
                potential_payout=profit,
            )
            await self.cog.economy.record_bet_placed(self.guild_id, self.author_id, stake)

            embed = discord.Embed(title="✅ Bet Placed!", color=discord.Color.green())
            embed.add_field(name="Bet ID",   value=f"`{bet_id}`",                          inline=True)
            embed.add_field(name="Game",     value=f"{g['away_team']} @ {g['home_team']}", inline=False)
            embed.add_field(
                name="Bet Type",
                value=TYPE_LABELS.get(self.selected_type, self.selected_type),
                inline=True,
            )
            embed.add_field(
                name="Your Pick",
                value=f"**{outcome.get('display') or outcome['selection']}**  ({fmt_odds(outcome['odds'])})",
                inline=True,
            )
            if self.selected_type != "player_props" and outcome.get("point") is not None:
                pt = outcome["point"]
                embed.add_field(name="Line", value=f"{'+' if pt > 0 else ''}{pt}", inline=True)
            elif self.selected_type == "player_props" and outcome.get("point") is not None:
                embed.add_field(name="Line", value=str(outcome["point"]), inline=True)
            embed.add_field(name="Stake",            value=f"{CURRENCY}**{stake:.0f}**",          inline=True)
            embed.add_field(name="Potential Profit", value=f"{CURRENCY}**{profit:.0f}**",         inline=True)
            embed.add_field(name="Total Return",     value=f"{CURRENCY}**{stake + profit:.0f}**", inline=True)
            embed.set_footer(text="Results settle automatically after the game ends. Use /bet history to track.")
            await self.message.edit(content=None, embed=embed, view=None)
            self.stop()

        except Exception as exc:
            await self.message.edit(
                content=f"❌ Something went wrong placing your bet: `{exc}`\nPlease try again.",
                embed=None,
                view=None,
            )
            self.stop()

    async def _cb_back_to_game(self, interaction: discord.Interaction) -> None:
        if not await self._check(interaction):
            return
        await interaction.response.defer()
        self.selected_game    = None
        self.selected_type    = None
        self.selected_outcome = None
        self.stake            = None
        self._render_step_game()
        await self.message.edit(embed=self._build_embed(), view=self)

    async def _cb_back_to_type(self, interaction: discord.Interaction) -> None:
        if not await self._check(interaction):
            return
        await interaction.response.defer()
        self.selected_type    = None
        self.selected_outcome = None
        self.stake            = None
        self._render_step_type()
        await self.message.edit(embed=self._build_embed(), view=self)

    async def _cb_back_to_outcome(self, interaction: discord.Interaction) -> None:
        if not await self._check(interaction):
            return
        await interaction.response.defer()
        self.stake = None
        self._render_step_outcome()
        await self.message.edit(embed=self._build_embed(), view=self)

    async def _cb_quit(self, interaction: discord.Interaction) -> None:
        if not await self._check(interaction):
            return
        await interaction.response.defer()
        await self.message.edit(content="❌ Betting session cancelled.", embed=None, view=None)
        self.stop()

    # ── Helpers ────────────────────────────────────────────────────────────────

    async def _check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This bet session belongs to someone else.", ephemeral=True
            )
            return False
        return True

    def _add_back(self, callback, row: int = 1) -> None:
        btn = discord.ui.Button(label="← Back", style=discord.ButtonStyle.secondary, row=row)
        btn.callback = callback
        self.add_item(btn)

    def _add_quit(self, row: int = 1) -> None:
        btn = discord.ui.Button(label="Quit", style=discord.ButtonStyle.danger, emoji="🚪", row=row)
        btn.callback = self._cb_quit
        self.add_item(btn)

    def _build_embed(self) -> discord.Embed:
        if self.selected_game is None:
            title = "🏀 NBA Bet — Step 1 / 4 — Select a Game"
        elif self.selected_type is None:
            title = "🏀 NBA Bet — Step 2 / 4 — Select Bet Type"
        elif self.selected_outcome is None:
            title = "🏀 NBA Bet — Step 3 / 4 — Select Your Pick"
        elif self.stake is None:
            title = "🏀 NBA Bet — Step 4 / 4 — Enter Amount"
        else:
            title = "🏀 NBA Bet — Confirm"

        embed = discord.Embed(title=title, color=discord.Color.gold())
        embed.add_field(name="Balance", value=f"{CURRENCY}**{self.balance:.0f}**", inline=True)

        if self.selected_game:
            g   = self.selected_game
            val = f"**{g['away_team']}** @ **{g['home_team']}**\n{_discord_ts(g['commence_time'])}"
            # Show injury notes if any
            inj_notes = g.get("odds", {}).get("injury_notes", [])
            if inj_notes:
                val += "\n" + "\n".join(inj_notes[:4])
            embed.add_field(name="Game", value=val, inline=False)

            # Show line movement if notable
            meta         = (g.get("odds") or {}).get("_meta", {})
            spread_move  = meta.get("spread_move", 0)
            total_move   = meta.get("total_move",  0)
            b2b_home     = meta.get("h_back_to_back", False)
            b2b_away     = meta.get("a_back_to_back", False)
            move_parts: List[str] = []
            if abs(spread_move) >= 0.5:
                sym = "📈" if spread_move > 0 else "📉"
                move_parts.append(f"Spread {spread_move:+.1f} {sym}")
            if abs(total_move) >= 0.5:
                sym = "📈" if total_move > 0 else "📉"
                move_parts.append(f"Total {total_move:+.1f} {sym}")
            if b2b_home:
                move_parts.append(f"⚡ {g['home_team']} on B2B")
            if b2b_away:
                move_parts.append(f"⚡ {g['away_team']} on B2B")
            if move_parts:
                embed.add_field(name="📊 Line Notes", value="  ·  ".join(move_parts), inline=False)

        if self.selected_type:
            embed.add_field(
                name="Bet Type",
                value=TYPE_LABELS.get(self.selected_type, self.selected_type),
                inline=True,
            )

        if self.selected_outcome:
            o = self.selected_outcome
            pick_str = f"**{o.get('display') or o['selection']}**  ({fmt_odds(o['odds'])})"
            if self.selected_type not in ("player_props",) and o.get("point") is not None:
                pt = o["point"]
                pick_str += f"  Line: {'+' if pt > 0 else ''}{pt}"
            embed.add_field(name="Your Pick", value=pick_str, inline=True)

        if self.stake is not None and self.selected_outcome:
            profit = calc_profit(self.stake, self.selected_outcome["odds"])
            embed.add_field(name="Stake",         value=f"{CURRENCY}**{self.stake:.0f}**",         inline=True)
            embed.add_field(name="Profit If Win", value=f"{CURRENCY}**{profit:.0f}**",             inline=True)
            embed.add_field(name="Total Return",  value=f"{CURRENCY}**{self.stake + profit:.0f}**", inline=True)

        embed.set_footer(text="Times out in 3 min  •  Use Back / Quit to navigate")
        return embed

    async def on_timeout(self) -> None:
        if self.message:
            try:
                await self.message.edit(
                    content="⏰ Betting session timed out.", embed=None, view=None
                )
            except Exception:
                pass
        self.stop()


# ══════════════════════════════════════════════════════════════════════════════
# Games list view
# ══════════════════════════════════════════════════════════════════════════════

class GamesView(discord.ui.View):
    """Paginated NBA schedule with live scores and injury flags."""

    PAGE_SIZE = 5

    def __init__(self, games: List[Dict], author_id: int, *, cog=None) -> None:
        super().__init__(timeout=120)
        self.games     = games
        self.author_id = author_id
        self.cog       = cog
        self.page      = 0
        self.total     = max(1, math.ceil(len(games) / self.PAGE_SIZE))
        self.message: Optional[discord.Message] = None
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        self.prev_btn.disabled = self.page == 0
        self.next_btn.disabled = self.page >= self.total - 1
        self.page_btn.label    = f"Page {self.page + 1} / {self.total}"

    def build_embed(self) -> discord.Embed:
        start = self.page * self.PAGE_SIZE
        chunk = self.games[start: start + self.PAGE_SIZE]
        embed = discord.Embed(
            title="🏀 NBA Games Schedule",
            color=discord.Color.blue(),
            description=f"Showing {start+1}–{start+len(chunk)} of {len(self.games)} game(s).",
        )
        for g in chunk:
            state = g.get("state", "")
            h_sc = g.get("home_score")
            a_sc = g.get("away_score")
            if state == "STATUS_IN_PROGRESS" and h_sc is not None and a_sc is not None:
                status = f"🔴 **LIVE**  {a_sc} – {h_sc}"
            elif g.get("completed") and h_sc is not None and a_sc is not None:
                status = f"✅ Final  **{a_sc} – {h_sc}**"
            elif g.get("completed"):
                status = "✅ Final"
            else:
                status = _discord_ts(g.get("commence_time", ""))

            away_rec = f" ({g['away_record']})" if g.get("away_record") else ""
            home_rec = f" ({g['home_record']})" if g.get("home_record") else ""
            name = f"{g['away_team']}{away_rec} @ {g['home_team']}{home_rec}"
            embed.add_field(name=name, value=status, inline=False)

        embed.set_footer(text="🔒 Betting locks once a game tips off. Use /bet place for upcoming games.")
        return embed

    @discord.ui.button(emoji="⬅️", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.page = max(0, self.page - 1)
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Page 1/1", style=discord.ButtonStyle.secondary, disabled=True)
    async def page_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer()

    @discord.ui.button(emoji="➡️", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.page = min(self.total - 1, self.page + 1)
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.primary, emoji="🔄")
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer()
        if self.cog is not None:
            try:
                fresh = await self.cog.fetcher.get_games(force=True)
                if fresh:
                    self.games = fresh
                    self.total = max(1, math.ceil(len(fresh) / self.PAGE_SIZE))
                    self.page  = min(self.page, self.total - 1)
                    self._sync_buttons()
            except Exception:
                pass
        await self.message.edit(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, emoji="❌")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(view=None)
        self.stop()

    async def on_timeout(self) -> None:
        if self.message:
            try:
                await self.message.edit(view=None)
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════════
# Leaderboard view
# ══════════════════════════════════════════════════════════════════════════════

class LeaderboardView(discord.ui.View):
    """Paginated economy leaderboard (10 per page, up to 100 entries)."""

    PAGE_SIZE = 10

    def __init__(self, entries: List[Dict], guild: discord.Guild, author_id: int) -> None:
        super().__init__(timeout=120)
        self.entries   = entries
        self.guild     = guild
        self.author_id = author_id
        self.page      = 0
        self.total     = max(1, math.ceil(len(entries) / self.PAGE_SIZE))
        self.message: Optional[discord.Message] = None
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        self.prev_btn.disabled = self.page == 0
        self.next_btn.disabled = self.page >= self.total - 1
        self.page_btn.label    = f"Page {self.page + 1} / {self.total}"

    def build_embed(self) -> discord.Embed:
        start = self.page * self.PAGE_SIZE
        chunk = self.entries[start: start + self.PAGE_SIZE]
        embed = discord.Embed(title="🏆 Economy Leaderboard", color=discord.Color.gold())
        medals = {0: "🥇", 1: "🥈", 2: "🥉"}
        lines  = []
        for i, e in enumerate(chunk):
            rank   = start + i
            medal  = medals.get(rank, f"**#{rank + 1}**")
            member = self.guild.get_member(int(e["user_id"]))
            name   = member.display_name if member else f"Unknown ({e['user_id']})"
            w      = e.get("bets_won",  0)
            l      = e.get("bets_lost", 0)
            total_bets = w + l
            win_pct = f"{w / total_bets * 100:.0f}%" if total_bets > 0 else "—"
            profit  = e.get("total_returned", 0.0) - e.get("total_wagered", 0.0)
            p_str   = f"+{profit:.0f}" if profit >= 0 else f"{profit:.0f}"
            lines.append(
                f"{medal} **{name}**\n"
                f"　{CURRENCY}`{e.get('balance', 0):.0f}` · "
                f"W/L `{w}/{l}` · Win% `{win_pct}` · P/L `{p_str}`"
            )
        embed.description = "\n".join(lines) if lines else "No players yet."
        embed.set_footer(text=f"{start + 1}–{start + len(chunk)} of {len(self.entries)} players")
        return embed

    @discord.ui.button(emoji="⬅️", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.page = max(0, self.page - 1)
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Page 1/1", style=discord.ButtonStyle.secondary, disabled=True)
    async def page_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer()

    @discord.ui.button(emoji="➡️", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.page = min(self.total - 1, self.page + 1)
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, emoji="❌")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(view=None)
        self.stop()

    async def on_timeout(self) -> None:
        if self.message:
            try:
                await self.message.edit(view=None)
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════════
# My Bets / History view
# ══════════════════════════════════════════════════════════════════════════════

class MyBetsView(discord.ui.View):
    """Paginated bets view — no cancellation, bets are final once placed."""

    PAGE_SIZE = 3

    def __init__(
        self,
        bets: List[Dict],
        cog: "NBABetting",
        author_id: int,
        guild_id: int,
        title: str = "📋 My Active Bets",
    ) -> None:
        super().__init__(timeout=120)
        self.bets      = bets
        self.cog       = cog
        self.author_id = author_id
        self.guild_id  = guild_id
        self.title     = title
        self.page      = 0
        self.message: Optional[discord.Message] = None
        self._rebuild()

    def _rebuild(self) -> None:
        self.clear_items()
        total = max(1, math.ceil(len(self.bets) / self.PAGE_SIZE))

        prev = discord.ui.Button(emoji="⬅️", style=discord.ButtonStyle.secondary,
                                 disabled=self.page == 0, row=0)
        prev.callback = self._prev
        page_lbl = discord.ui.Button(label=f"Page {self.page+1}/{total}",
                                     style=discord.ButtonStyle.secondary, disabled=True, row=0)
        nxt = discord.ui.Button(emoji="➡️", style=discord.ButtonStyle.secondary,
                                disabled=self.page >= total - 1, row=0)
        nxt.callback = self._next
        close = discord.ui.Button(label="Close", style=discord.ButtonStyle.danger,
                                  emoji="❌", row=0)
        close.callback = self._close
        self.add_item(prev)
        self.add_item(page_lbl)
        self.add_item(nxt)
        self.add_item(close)

    def build_embed(self) -> discord.Embed:
        start = self.page * self.PAGE_SIZE
        chunk = self.bets[start: start + self.PAGE_SIZE]
        embed = discord.Embed(title=self.title, color=discord.Color.blurple())
        if not chunk:
            embed.description = "No bets to display."
            return embed
        for bet in chunk:
            emoji = STATUS_EMOJI.get(bet["status"], "❓")
            tl    = TYPE_LABELS.get(bet["bet_type"], bet["bet_type"])
            line  = ""
            if bet.get("point") is not None and bet["bet_type"] != "player_props":
                pt   = bet["point"]
                line = f"  Line: {'+' if pt > 0 else ''}{pt}"
            elif bet.get("point") is not None and bet["bet_type"] == "player_props":
                line = f"  Line: {bet['point']}"

            # Nice display for selection
            sel_display = bet["selection"]
            if bet["bet_type"] == "player_props":
                sel_display = fmt_prop_selection(bet["selection"])

            payout_str = ""
            if bet["status"] == "won" and bet.get("actual_payout") is not None:
                payout_str = f"\n**Won:** {CURRENCY}**{bet['actual_payout']:.0f}**"
            elif bet["status"] == "push":
                payout_str = "\n**Push** – stake returned"

            if bet.get("bet_type") == "parlay":
                legs         = bet.get("legs", [])
                legs_summary = "  ·  ".join(
                    (
                        fmt_prop_selection(lg.get("selection", ""))
                        if lg.get("leg_type") == "player_props"
                        else lg.get("selection", "?")
                    ) + f" ({fmt_odds(lg['odds'])})"
                    for lg in legs[:4]
                )
                if len(legs) > 4:
                    legs_summary += f"  +{len(legs)-4} more"
                val = (
                    f"**Parlay:** {len(legs)} legs  |  Combined: {fmt_odds(bet['odds'])}\n"
                    f"{legs_summary}\n"
                    f"**Stake:** {CURRENCY}{bet['stake']:.0f}  →  "
                    f"**Potential Win:** {CURRENCY}{bet['potential_payout']:.0f}"
                    f"{payout_str}\n"
                    f"**Placed:** {_discord_ts(bet['placed_at'])}"
                )
            else:
                val = (
                    f"**Game:** {bet['away_team']} @ {bet['home_team']}\n"
                    f"**Type:** {tl}  |  **Pick:** {sel_display}  ({fmt_odds(bet['odds'])}){line}\n"
                    f"**Stake:** {CURRENCY}{bet['stake']:.0f}  →  "
                    f"**Potential Win:** {CURRENCY}{bet['potential_payout']:.0f}"
                    f"{payout_str}\n"
                    f"**Placed:** {_discord_ts(bet['placed_at'])}"
                )
            embed.add_field(
                name=f"{emoji} `{bet['id']}`  —  {bet['status'].upper()}",
                value=val,
                inline=False,
            )
        total = max(1, math.ceil(len(self.bets) / self.PAGE_SIZE))
        embed.set_footer(text=f"Page {self.page+1}/{total} · {len(self.bets)} total bet(s)")
        return embed

    async def _prev(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Not yours.", ephemeral=True)
        await interaction.response.defer()
        self.page = max(0, self.page - 1)
        self._rebuild()
        await self.message.edit(embed=self.build_embed(), view=self)

    async def _next(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Not yours.", ephemeral=True)
        await interaction.response.defer()
        self.page = min(max(0, math.ceil(len(self.bets) / self.PAGE_SIZE) - 1), self.page + 1)
        self._rebuild()
        await self.message.edit(embed=self.build_embed(), view=self)

    async def _close(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(view=None)
        self.stop()

    async def on_timeout(self) -> None:
        if self.message:
            try:
                await self.message.edit(view=None)
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════════
# Generic confirm view
# ══════════════════════════════════════════════════════════════════════════════

class ConfirmView(discord.ui.View):
    def __init__(self, author_id: int, timeout: float = 30.0) -> None:
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.confirmed: Optional[bool] = None

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Not your action.", ephemeral=True)
        await interaction.response.defer()   # acknowledge FIRST — must happen before stop()
        self.confirmed = True
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Not your action.", ephemeral=True)
        await interaction.response.defer()   # acknowledge FIRST — must happen before stop()
        self.confirmed = False
        self.stop()

    async def on_timeout(self) -> None:
        self.confirmed = None
        self.stop()


# ══════════════════════════════════════════════════════════════════════════════
# Odds board view  (/bet odds)
# ══════════════════════════════════════════════════════════════════════════════

class OddsView(discord.ui.View):
    """Read-only full odds board for a single game."""

    def __init__(
        self,
        game: Dict,
        author_id: int,
        cog: Optional["NBABetting"] = None,
        guild_id: Optional[int] = None,
        event_id: Optional[str] = None,
    ) -> None:
        super().__init__(timeout=120)
        self.game      = game
        self.author_id = author_id
        self.cog       = cog
        self.guild_id  = guild_id
        self.event_id  = event_id
        self.message: Optional[discord.Message] = None

    def build_embed(self) -> discord.Embed:
        g    = self.game
        odds = g.get("odds") or {}
        meta = odds.get("_meta", {})
        pub  = g.get("public_action") or {}

        embed = discord.Embed(
            title=f"📋 Odds Board — {g.get('away_team')} @ {g.get('home_team')}",
            color=discord.Color.dark_gold(),
            description=_discord_ts(g.get("commence_time", "")),
        )

        # ── Moneyline ─────────────────────────────────────────────────────────
        h2h = odds.get("h2h") or {}
        if h2h:
            lines = []
            pub_total = pub.get("h2h_total", 0)
            for team, price in h2h.items():
                prob    = int(implied_prob(price) * 100)
                is_home = team == g.get("home_team")
                pub_pct = ""
                if pub_total >= 10:
                    pct = int((pub.get("home_pct", 0.5) if is_home else pub.get("away_pct", 0.5)) * 100)
                    pub_pct = f"  |  {pct}% action"
                lines.append(f"**{team}** `{fmt_odds(price)}` (~{prob}%){pub_pct}")
            embed.add_field(name="🏆 Moneyline", value="\n".join(lines), inline=True)

        # ── Spread ────────────────────────────────────────────────────────────
        spreads = odds.get("spreads") or {}
        if spreads:
            lines = []
            for team, d in spreads.items():
                pt = d["point"]; pr = d["price"]
                pt_str = f"{'+' if pt > 0 else ''}{pt}"
                lines.append(f"**{team}** `{pt_str}` ({fmt_odds(pr)})")
            embed.add_field(name="📊 Spread", value="\n".join(lines), inline=True)

        # ── Total ─────────────────────────────────────────────────────────────
        totals = odds.get("totals") or {}
        if totals:
            lines = []
            pub_ou = pub.get("ou_total", 0)
            for side, d in totals.items():
                pt = d["point"]; pr = d["price"]
                pub_pct = ""
                if pub_ou >= 10:
                    pct = int((pub.get("over_pct", 0.5) if side == "Over" else pub.get("under_pct", 0.5)) * 100)
                    pub_pct = f"  |  {pct}% action"
                emoji = "📈" if side == "Over" else "📉"
                lines.append(f"{emoji} **{side} {pt}** `{fmt_odds(pr)}`{pub_pct}")
            embed.add_field(name="📈 Total", value="\n".join(lines), inline=True)

        # ── Line movement ─────────────────────────────────────────────────────
        spread_move = meta.get("spread_move", 0)
        total_move  = meta.get("total_move",  0)
        b2b_home    = meta.get("h_back_to_back", False)
        b2b_away    = meta.get("a_back_to_back", False)
        notes: List[str] = []
        if abs(spread_move) >= 0.5:
            sym = "📈" if spread_move > 0 else "📉"
            notes.append(f"Spread moved {spread_move:+.1f} {sym}")
        if abs(total_move) >= 0.5:
            sym = "📈" if total_move > 0 else "📉"
            notes.append(f"Total moved {total_move:+.1f} {sym}")
        opening_spread = meta.get("opening_spread")
        opening_total  = meta.get("opening_total")
        if opening_spread is not None:
            notes.append(f"Opening spread: {opening_spread:+.1f}")
        if opening_total is not None:
            notes.append(f"Opening total: {opening_total}")
        if b2b_home:
            notes.append(f"⚡ {g.get('home_team')} on B2B")
        if b2b_away:
            notes.append(f"⚡ {g.get('away_team')} on B2B")
        if notes:
            embed.add_field(name="📊 Line Movement", value="\n".join(notes), inline=False)

        # ── Injuries / notes ──────────────────────────────────────────────────
        inj_notes = odds.get("injury_notes", [])
        if inj_notes:
            embed.add_field(
                name="🏥 Injury Notes",
                value="\n".join(inj_notes[:8]),
                inline=False,
            )

        # ── Top props preview ─────────────────────────────────────────────────
        props = g.get("player_props") or {}
        if props:
            top_players = sorted(props.items(), key=lambda kv: kv[1].get("tier", 3))[:5]
            prop_lines = []
            for pname, pd in top_players:
                is_q = pd.get("status", "active") == "questionable"
                q_tag = " ⚠️Q" if is_q else ""
                pts_o = fmt_odds(pd.get("pts_over", -110))
                pts_u = fmt_odds(pd.get("pts_under", -110))
                prop_lines.append(
                    f"**{pname}**{q_tag}  pts {pd['pts']}  ({pts_o} / {pts_u})"
                )
            embed.add_field(
                name="🎯 Top Props (Pts)",
                value="\n".join(prop_lines),
                inline=False,
            )

        embed.set_footer(text="Use /bet place or /bet parlay to wager  ·  Odds update with server action")
        return embed

    @discord.ui.button(label="🔄 Refresh", style=discord.ButtonStyle.primary)
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer()
        if self.cog and self.event_id:
            try:
                fresh = await self.cog.fetcher.get_game_with_odds(
                    self.event_id,
                    guild_id=self.guild_id,
                    bets_manager=self.cog.bets,
                )
                if fresh:
                    self.game = fresh
            except Exception:
                pass
        await self.message.edit(embed=self.build_embed(), view=self)

    @discord.ui.button(label="❌ Close", style=discord.ButtonStyle.danger)
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(view=None)
        self.stop()

    async def on_timeout(self) -> None:
        if self.message:
            try:
                await self.message.edit(view=None)
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════════
# Parlay builder view  (/bet parlay)
# ══════════════════════════════════════════════════════════════════════════════

class ParlayBuilderView(discord.ui.View):
    """
    Multi-step parlay builder — 2 to 5 legs, combined odds multiply.
    Flow: select game → select bet type → select pick → add more / finalize
          → enter amount → final confirm → place parlay.
    """

    MAX_LEGS = 5
    MIN_LEGS = 2

    def __init__(
        self,
        cog: "NBABetting",
        author_id: int,
        guild_id: int,
        games: List[Dict],
        balance: float,
        max_bet: float = 0.0,
    ) -> None:
        super().__init__(timeout=300)
        self.cog       = cog
        self.author_id = author_id
        self.guild_id  = guild_id
        self.games     = games
        self.balance   = balance
        self.max_bet   = max_bet if max_bet > 0 else balance
        self.message: Optional[discord.Message] = None

        self.legs: List[Dict]                = []
        self.building_game: Optional[Dict]  = None
        self.building_type: Optional[str]   = None
        self.building_player: Optional[str] = None
        self.stake: Optional[float]         = None
        self._step: str                     = "game"

        self._render()

    # ── Computed ──────────────────────────────────────────────────────────────

    def _combo_odds(self) -> int:
        return calc_parlay_odds([leg["odds"] for leg in self.legs]) if self.legs else -110

    # ── Renderers ─────────────────────────────────────────────────────────────

    def _render(self) -> None:
        if self._step == "game":
            self._render_step_game()
        elif self._step == "type":
            self._render_step_type()
        elif self._step == "outcome":
            self._render_step_outcome()
        elif self._step == "prop_player":
            self._render_step_prop_player()
        elif self._step == "prop_stat":
            self._render_step_prop_stat()
        elif self._step == "done_leg":
            self._render_step_done_leg()
        elif self._step == "confirm":
            self._render_step_confirm()

    def _render_step_game(self) -> None:
        self.clear_items()
        # Always show all games — same-game outcome restriction is enforced at the
        # type-selection step, so users can still add a prop from a game that
        # already has an outcome leg in this parlay.
        options: List[discord.SelectOption] = []
        for g in self.games[:25]:
            label = f"{g['away_abbr']} @ {g['home_abbr']}"
            desc  = f"{g['away_team']} at {g['home_team']}"[:100]
            options.append(discord.SelectOption(
                label=label, description=desc, value=g["event_id"], emoji="🏀",
            ))
        if not options:
            options.append(discord.SelectOption(label="No games available right now", value="__none__"))
        sel = discord.ui.Select(placeholder="🏀 Select a game for this leg…", options=options)
        sel.callback = self._cb_game
        self.add_item(sel)
        if self.legs:
            fin = discord.ui.Button(
                label=f"✅ Finalize ({len(self.legs)} legs · {fmt_odds(self._combo_odds())})",
                style=discord.ButtonStyle.green, row=1,
            )
            fin.callback = self._cb_finalize
            self.add_item(fin)
        cancel = discord.ui.Button(label="❌ Cancel", style=discord.ButtonStyle.danger, row=1)
        cancel.callback = self._cb_cancel
        self.add_item(cancel)

    def _render_step_type(self) -> None:
        self.clear_items()
        g          = self.building_game or {}
        odds       = (g.get("odds") or {})
        props      = (g.get("player_props") or {})
        event_id   = g.get("event_id", "")
        # If this game already has an outcome leg in the parlay, only props are
        # available — prevents correlated same-game outcome stacking.
        _OUTCOME_TYPES = {"h2h", "spreads", "totals"}
        has_outcome_leg = any(
            leg.get("event_id") == event_id and leg.get("leg_type") in _OUTCOME_TYPES
            for leg in self.legs
        )
        options: List[discord.SelectOption] = []
        if not has_outcome_leg:
            if odds.get("h2h"):
                options.append(discord.SelectOption(label="🏆 Moneyline", value="h2h"))
            if odds.get("spreads"):
                options.append(discord.SelectOption(label="📊 Point Spread", value="spreads"))
            if odds.get("totals"):
                options.append(discord.SelectOption(label="📈 Over / Under", value="totals"))
        if props:
            options.append(discord.SelectOption(label="🎯 Player Props", value="player_props"))
        if not options:
            options.append(discord.SelectOption(label="No odds available", value="__none__"))
        sel = discord.ui.Select(placeholder="📋 Select bet type for this leg…", options=options)
        sel.callback = self._cb_type
        self.add_item(sel)
        back = discord.ui.Button(label="← Back", style=discord.ButtonStyle.secondary, row=1)
        back.callback = self._cb_back_game
        self.add_item(back)
        cancel = discord.ui.Button(label="❌ Cancel", style=discord.ButtonStyle.danger, row=1)
        cancel.callback = self._cb_cancel
        self.add_item(cancel)

    def _render_step_prop_player(self) -> None:
        self.clear_items()
        g     = self.building_game or {}
        props = (g.get("player_props") or {})
        sorted_players = sorted(
            props.items(),
            key=lambda kv: (kv[1].get("tier", 3), kv[0])
        )
        options: List[discord.SelectOption] = []
        for pname, pdata in sorted_players[:25]:
            tier   = pdata.get("tier", 3)
            is_q   = pdata.get("status") == "questionable"
            emoji  = "⭐" if tier == 1 else ("🔵" if tier == 2 else "⚪")
            label  = (f"⚠️ {pname} (Q)" if is_q else pname)[:100]
            pts    = pdata.get("pts", 0.0)
            reb    = pdata.get("reb", 0.0)
            ast    = pdata.get("ast", 0.0)
            pra    = pdata.get("pra", 0.0)
            desc   = f"O/U Pts {pts} | Reb {reb} | Ast {ast} | PRA {pra}"[:100]
            options.append(discord.SelectOption(
                label=label, description=desc, value=pname, emoji=emoji,
            ))
        if not options:
            options.append(discord.SelectOption(label="No players available", value="__none__"))
        sel = discord.ui.Select(placeholder="🎯 Select a player…", options=options)
        sel.callback = self._cb_prop_player
        self.add_item(sel)
        back = discord.ui.Button(label="← Back", style=discord.ButtonStyle.secondary, row=1)
        back.callback = self._cb_back_type
        self.add_item(back)
        cancel = discord.ui.Button(label="❌ Cancel", style=discord.ButtonStyle.danger, row=1)
        cancel.callback = self._cb_cancel
        self.add_item(cancel)

    def _render_step_prop_stat(self) -> None:
        self.clear_items()
        g     = self.building_game or {}
        props = (g.get("player_props") or {})
        pname = self.building_player or ""
        pdata = props.get(pname, {})
        stat_labels = {"pts": "Points", "reb": "Rebounds", "ast": "Assists", "pra": "Pts+Reb+Ast"}
        is_q = pdata.get("status") == "questionable"
        options: List[discord.SelectOption] = []
        for stat, label in stat_labels.items():
            line_val = pdata.get(stat)      # key is the stat name, not f"{stat}_line"
            if line_val is None:
                continue
            for direction in ("Over", "Under"):
                price = pdata.get(f"{stat}_{direction.lower()}", -110)
                d_emoji = "📈" if direction == "Over" else "📉"
                q_suffix = "  ⚠️Q" if is_q else ""
                opt_label = f"{direction} {line_val} {label}  ({fmt_odds(price)}){q_suffix}"[:100]
                options.append(discord.SelectOption(
                    label=opt_label,
                    value=f"{pname}|{stat}|{direction}|{price}|{line_val}",
                    emoji=d_emoji,
                ))
        if not options:
            options.append(discord.SelectOption(label="No props available for this player", value="__none__"))
        sel = discord.ui.Select(placeholder="📊 Choose stat & direction…", options=options)
        sel.callback = self._cb_prop_stat_select
        self.add_item(sel)
        back = discord.ui.Button(label="← Back", style=discord.ButtonStyle.secondary, row=1)
        back.callback = self._cb_back_prop_player
        self.add_item(back)
        cancel = discord.ui.Button(label="❌ Cancel", style=discord.ButtonStyle.danger, row=1)
        cancel.callback = self._cb_cancel
        self.add_item(cancel)

    def _render_step_outcome(self) -> None:
        self.clear_items()
        g        = self.building_game or {}
        odds     = (g.get("odds") or {})
        bet_type = self.building_type
        options: List[discord.SelectOption] = []

        if bet_type == "h2h":
            for team, price in (odds.get("h2h") or {}).items():
                options.append(discord.SelectOption(
                    label=f"{team}  ({fmt_odds(price)})"[:100],
                    value=f"{team}|{price}|None", emoji="🏆",
                ))
        elif bet_type == "spreads":
            for team, d in (odds.get("spreads") or {}).items():
                pt = d["point"]; pr = d["price"]
                pt_str = f"{'+' if pt > 0 else ''}{pt}"
                options.append(discord.SelectOption(
                    label=f"{team}  {pt_str}  ({fmt_odds(pr)})"[:100],
                    value=f"{team}|{pr}|{pt}", emoji="📊",
                ))
        elif bet_type == "totals":
            for side, d in (odds.get("totals") or {}).items():
                pt = d["point"]; pr = d["price"]
                emoji = "📈" if side == "Over" else "📉"
                options.append(discord.SelectOption(
                    label=f"{side} {pt}  ({fmt_odds(pr)})"[:100],
                    value=f"{side}|{pr}|{pt}", emoji=emoji,
                ))
        if not options:
            options.append(discord.SelectOption(label="No options", value="__none__"))
        sel = discord.ui.Select(placeholder="🎯 Select your pick…", options=options)
        sel.callback = self._cb_outcome
        self.add_item(sel)
        back = discord.ui.Button(label="← Back", style=discord.ButtonStyle.secondary, row=1)
        back.callback = self._cb_back_type
        self.add_item(back)
        cancel = discord.ui.Button(label="❌ Cancel", style=discord.ButtonStyle.danger, row=1)
        cancel.callback = self._cb_cancel
        self.add_item(cancel)

    def _render_step_done_leg(self) -> None:
        self.clear_items()
        if len(self.legs) < self.MAX_LEGS:
            add = discord.ui.Button(
                label=f"➕ Add Leg {len(self.legs) + 1}",
                style=discord.ButtonStyle.primary,
            )
            add.callback = self._cb_add_more
            self.add_item(add)
        fin = discord.ui.Button(
            label=f"✅ Finalize  ({fmt_odds(self._combo_odds())})",
            style=discord.ButtonStyle.green,
        )
        fin.callback = self._cb_finalize
        self.add_item(fin)
        cancel = discord.ui.Button(label="❌ Cancel", style=discord.ButtonStyle.danger, row=1)
        cancel.callback = self._cb_cancel
        self.add_item(cancel)

    def _render_step_confirm(self) -> None:
        self.clear_items()
        combo  = self._combo_odds()
        profit = calc_profit(self.stake or 0, combo)
        total  = (self.stake or 0) + profit
        confirm = discord.ui.Button(
            label=f"✅ Confirm Parlay  ({CURRENCY}{total:.0f} return)",
            style=discord.ButtonStyle.green,
        )
        confirm.callback = self._cb_confirm_place
        back = discord.ui.Button(label="← Change Amount", style=discord.ButtonStyle.secondary)
        back.callback = self._cb_back_finalize
        cancel = discord.ui.Button(label="❌ Cancel", style=discord.ButtonStyle.danger)
        cancel.callback = self._cb_cancel
        self.add_item(confirm)
        self.add_item(back)
        self.add_item(cancel)

    # ── Embed ──────────────────────────────────────────────────────────────────

    def _build_embed(self) -> discord.Embed:
        embed = discord.Embed(title="🎰 Parlay Builder", color=discord.Color.purple())
        embed.add_field(name="Balance", value=f"{CURRENCY}**{self.balance:.0f}**", inline=True)
        embed.add_field(name="Legs",    value=str(len(self.legs)),                  inline=True)
        if self.legs:
            embed.add_field(name="Combined Odds", value=fmt_odds(self._combo_odds()), inline=True)

        for i, leg in enumerate(self.legs, 1):
            lt = leg.get("leg_type", "")
            tl = {"h2h": "ML", "spreads": "Spread", "totals": "O/U", "player_props": "Prop"}.get(lt, lt)
            if lt == "player_props":
                sel_disp = fmt_prop_selection(leg["selection"])
                pt_str   = f"  Line: {leg['point']}" if leg.get("point") is not None else ""
            else:
                sel_disp = leg["selection"]
                if leg.get("point") is not None:
                    pt = leg["point"]
                    pt_str = f" ({'+' if pt > 0 else ''}{pt})"
                else:
                    pt_str = ""
            embed.add_field(
                name=f"Leg {i}  [{tl}]  {leg.get('away_team','')} @ {leg.get('home_team','')}",
                value=f"**{sel_disp}**{pt_str}  ({fmt_odds(leg['odds'])})",
                inline=False,
            )

        if self.building_game and self._step in ("type", "outcome", "prop_player", "prop_stat"):
            g = self.building_game
            embed.add_field(
                name=f"Adding Leg {len(self.legs) + 1}…",
                value=f"{g['away_team']} @ {g['home_team']}",
                inline=False,
            )

        if self.stake is not None and self._step == "confirm":
            combo  = self._combo_odds()
            profit = calc_profit(self.stake, combo)
            embed.add_field(name="Stake",           value=f"{CURRENCY}**{self.stake:.0f}**",             inline=True)
            embed.add_field(name="Potential Profit", value=f"{CURRENCY}**{profit:.0f}**",                inline=True)
            embed.add_field(name="Total Return",    value=f"{CURRENCY}**{self.stake + profit:.0f}**",    inline=True)

        if not self.legs:
            embed.description = (
                "Build a parlay with 2–5 legs across any games.\n"
                "All legs must win. Combined odds multiply together.\n"
                "*Bets are final once placed. No cancellations.*"
            )
        embed.set_footer(text=f"Min {self.MIN_LEGS} legs · Max {self.MAX_LEGS} legs · Times out in 5 min")
        return embed

    # ── Callbacks ──────────────────────────────────────────────────────────────

    async def _cb_game(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Not your session.", ephemeral=True)
        val = interaction.data["values"][0]
        if val == "__none__":
            return await interaction.response.send_message("No games available.", ephemeral=True)
        await interaction.response.defer()
        full = await self.cog.fetcher.get_game_with_odds(
            val, guild_id=self.guild_id, bets_manager=self.cog.bets,
        )
        self.building_game = full or next((g for g in self.games if g["event_id"] == val), None)
        self.building_type = None
        self._step = "type"
        self._render()
        await self.message.edit(embed=self._build_embed(), view=self)

    async def _cb_type(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Not your session.", ephemeral=True)
        val = interaction.data["values"][0]
        if val == "__none__":
            return await interaction.response.send_message("No odds available.", ephemeral=True)
        await interaction.response.defer()
        self.building_type = val
        if val == "player_props":
            self._step = "prop_player"
        else:
            self._step = "outcome"
        self._render()
        await self.message.edit(embed=self._build_embed(), view=self)

    async def _cb_outcome(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Not your session.", ephemeral=True)
        val = interaction.data["values"][0]
        if val == "__none__":
            return await interaction.response.send_message("No options.", ephemeral=True)
        await interaction.response.defer()

        parts     = val.split("|")
        selection = parts[0]
        price     = int(parts[1])
        point     = float(parts[2]) if parts[2] != "None" else None
        g         = self.building_game or {}

        self.legs.append({
            "event_id":      g.get("event_id", ""),
            "home_team":     g.get("home_team", ""),
            "away_team":     g.get("away_team", ""),
            "game_name":     g.get("name", ""),
            "commence_time": g.get("commence_time", ""),
            "leg_type":      self.building_type,
            "selection":     selection,
            "odds":          price,
            "point":         point,
        })
        self.building_game = None
        self.building_type = None
        self._step = "done_leg"
        self._render()
        await self.message.edit(embed=self._build_embed(), view=self)

    async def _cb_prop_player(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Not your session.", ephemeral=True)
        val = interaction.data["values"][0]
        if val == "__none__":
            return await interaction.response.send_message("No players available.", ephemeral=True)
        await interaction.response.defer()
        self.building_player = val
        self._step = "prop_stat"
        self._render()
        await self.message.edit(embed=self._build_embed(), view=self)

    async def _cb_prop_stat_select(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Not your session.", ephemeral=True)
        val = interaction.data["values"][0]
        if val == "__none__":
            return await interaction.response.send_message("No props available for this player.", ephemeral=True)

        parts = val.split("|")
        if len(parts) < 5:
            return await interaction.response.send_message("Malformed prop option.", ephemeral=True)

        await interaction.response.defer()

        pname, stat, direction, price_str, line_str = parts[0], parts[1], parts[2], parts[3], parts[4]
        g = self.building_game or {}

        self.legs.append({
            "event_id":      g.get("event_id", ""),
            "home_team":     g.get("home_team", ""),
            "away_team":     g.get("away_team", ""),
            "game_name":     g.get("name", ""),
            "commence_time": g.get("commence_time", ""),
            "leg_type":      "player_props",
            "selection":     f"{pname}|{stat}|{direction}",
            "odds":          int(price_str),
            "point":         float(line_str),
        })
        self.building_game   = None
        self.building_type   = None
        self.building_player = None
        self._step = "done_leg"
        self._render()
        await self.message.edit(embed=self._build_embed(), view=self)

    async def _cb_back_prop_player(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Not your session.", ephemeral=True)
        await interaction.response.defer()
        self.building_player = None
        self._step = "prop_player"
        self._render()
        await self.message.edit(embed=self._build_embed(), view=self)

    async def _cb_add_more(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Not your session.", ephemeral=True)
        await interaction.response.defer()
        self._step = "game"
        self._render()
        await self.message.edit(embed=self._build_embed(), view=self)

    async def _cb_finalize(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Not your session.", ephemeral=True)
        if len(self.legs) < self.MIN_LEGS:
            return await interaction.response.send_message(
                f"❌ Need at least {self.MIN_LEGS} legs for a parlay.", ephemeral=True
            )
        self.balance = await self.cog.economy.get_balance(self.guild_id, self.author_id)
        modal = AmountModal(max_balance=self.balance, max_bet=self.max_bet)
        await interaction.response.send_modal(modal)
        timed_out = await modal.wait()
        if timed_out or modal.value is None:
            return
        self.stake = modal.value
        self._step = "confirm"
        self._render()
        await self.message.edit(embed=self._build_embed(), view=self)

    async def _cb_back_finalize(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Not your session.", ephemeral=True)
        await interaction.response.defer()
        self.stake = None
        self._step = "done_leg"
        self._render()
        await self.message.edit(embed=self._build_embed(), view=self)

    async def _cb_confirm_place(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Not your session.", ephemeral=True)
        await interaction.response.defer()

        combo  = self._combo_odds()
        profit = calc_profit(self.stake or 0.0, combo)

        confirm_view = ConfirmView(self.author_id, timeout=60)
        legs_lines_parts = []
        for leg in self.legs:
            if leg.get("leg_type") == "player_props":
                sel_str = fmt_prop_selection(leg["selection"])
            else:
                sel_str = leg["selection"]
            legs_lines_parts.append(
                f"• **{sel_str}** ({fmt_odds(leg['odds'])})  —  "
                f"{leg.get('away_team','')} @ {leg.get('home_team','')}"
            )
        legs_lines = "\n".join(legs_lines_parts)
        await self.message.edit(
            content=(
                f"⚠️ **Final Parlay Confirmation**\n{legs_lines}\n\n"
                f"Combined: **{fmt_odds(combo)}**  ·  "
                f"Stake: {CURRENCY}**{(self.stake or 0):.0f}**  ·  "
                f"Return: {CURRENCY}**{(self.stake or 0) + profit:.0f}**\n"
                f"*All legs must win. Bets are final once placed.*"
            ),
            embed=None, view=confirm_view,
        )
        await confirm_view.wait()
        if not confirm_view.confirmed:
            self._render()
            await self.message.edit(content=None, embed=self._build_embed(), view=self)
            return

        # ── Place parlay ───────────────────────────────────────────────────────
        try:
            ok = await self.cog.economy.deduct(self.guild_id, self.author_id, self.stake or 0.0)
            if not ok:
                await self.message.edit(content="❌ Insufficient balance.", embed=None, view=None)
                self.stop()
                return

            parlay_id = self.cog.bets.place_parlay(
                self.guild_id, self.author_id,
                legs=self.legs,
                combined_odds=combo,
                stake=self.stake or 0.0,
                potential_payout=profit,
            )
            await self.cog.economy.record_bet_placed(self.guild_id, self.author_id, self.stake or 0.0)

            embed = discord.Embed(title="🎰 Parlay Placed!", color=discord.Color.purple())
            embed.add_field(name="Parlay ID",      value=f"`{parlay_id}`",            inline=True)
            embed.add_field(name="Legs",           value=str(len(self.legs)),          inline=True)
            embed.add_field(name="Combined Odds",  value=fmt_odds(combo),             inline=True)
            for i, leg in enumerate(self.legs, 1):
                lt = leg.get("leg_type", "")
                tl = {"h2h": "ML", "spreads": "Spread", "totals": "O/U", "player_props": "Prop"}.get(lt, lt)
                if lt == "player_props":
                    sel_disp = fmt_prop_selection(leg["selection"])
                    pt_str   = f"  Line: {leg['point']}" if leg.get("point") is not None else ""
                else:
                    sel_disp = leg["selection"]
                    if leg.get("point") is not None:
                        pt = leg["point"]
                        pt_str = f" ({'+' if pt > 0 else ''}{pt})"
                    else:
                        pt_str = ""
                embed.add_field(
                    name=f"Leg {i}  [{tl}]",
                    value=f"**{sel_disp}**{pt_str} ({fmt_odds(leg['odds'])})\n"
                          f"{leg.get('away_team','')} @ {leg.get('home_team','')}",
                    inline=False,
                )
            embed.add_field(name="Stake",            value=f"{CURRENCY}**{(self.stake or 0):.0f}**",           inline=True)
            embed.add_field(name="Potential Profit", value=f"{CURRENCY}**{profit:.0f}**",                      inline=True)
            embed.add_field(name="Total Return",     value=f"{CURRENCY}**{(self.stake or 0) + profit:.0f}**",  inline=True)
            embed.set_footer(text="All legs must win. Results settle automatically after all games end.")
            await self.message.edit(content=None, embed=embed, view=None)
            self.stop()

        except Exception as exc:
            await self.message.edit(
                content=f"❌ Error placing parlay: `{exc}`", embed=None, view=None
            )
            self.stop()

    async def _cb_back_game(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Not your session.", ephemeral=True)
        await interaction.response.defer()
        self.building_game = None
        self.building_type = None
        self._step = "game"
        self._render()
        await self.message.edit(embed=self._build_embed(), view=self)

    async def _cb_back_type(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Not your session.", ephemeral=True)
        await interaction.response.defer()
        self.building_type = None
        self._step = "type"
        self._render()
        await self.message.edit(embed=self._build_embed(), view=self)

    async def _cb_cancel(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Not your session.", ephemeral=True)
        await interaction.response.defer()
        await self.message.edit(content="❌ Parlay cancelled.", embed=None, view=None)
        self.stop()

    async def on_timeout(self) -> None:
        if self.message:
            try:
                await self.message.edit(content="⏰ Parlay session timed out.", embed=None, view=None)
            except Exception:
                pass
        self.stop()
