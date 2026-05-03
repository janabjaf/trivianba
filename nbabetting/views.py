"""views.py – All Discord UI components for NBABetting."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import discord

from .odds import calc_profit, evaluate_bet, fmt_odds, implied_prob

if TYPE_CHECKING:
    from .nbabetting import NBABetting

CURRENCY = "\U0001f4b0"
TYPE_LABELS = {"h2h": "Moneyline", "spreads": "Point Spread", "totals": "Over/Under"}
STATUS_EMOJI = {
    "pending":   "⏳",
    "won":       "✅",
    "lost":      "❌",
    "push":      "🔄",
    "cancelled": "🚫",
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

    def __init__(self, max_balance: float) -> None:
        super().__init__()
        self.max_balance    = max_balance
        self.value: Optional[float]  = None
        self.modal_interaction: Optional[discord.Interaction] = None
        self.amount.placeholder = f"1 – {int(max_balance)}"

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
        self.value              = v
        self.modal_interaction  = interaction
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
        games: List[Dict],
        balance: float,
    ) -> None:
        super().__init__(timeout=180)
        self.cog       = cog
        self.author_id = author_id
        self.games     = games
        self.balance   = balance
        self.message: Optional[discord.Message] = None

        # State
        self.selected_game: Optional[Dict]    = None
        self.selected_type: Optional[str]     = None   # "h2h" | "spreads" | "totals"
        self.selected_outcome: Optional[Dict] = None   # {selection, odds, point}
        self.stake: Optional[float]           = None

        self._render_step_game()

    # ── Step builders ──────────────────────────────────────────────────────────

    def _render_step_game(self) -> None:
        self.clear_items()
        options: List[discord.SelectOption] = []
        for g in self.games[:25]:
            label = f"{g['away_abbr']} @ {g['home_abbr']}"
            away_rec = f" ({g['away_record']})" if g.get("away_record") else ""
            home_rec = f" ({g['home_record']})" if g.get("home_record") else ""
            desc = f"{g['away_team']}{away_rec} at {g['home_team']}{home_rec}"[:100]
            state_tag = ""
            if g.get("state") == "STATUS_IN_PROGRESS":
                state_tag = " 🔴 LIVE"
            elif g.get("completed"):
                state_tag = " ✅ Final"
            options.append(
                discord.SelectOption(label=label + state_tag, description=desc, value=g["event_id"])
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
        options: List[discord.SelectOption] = []
        if odds.get("h2h"):
            options.append(discord.SelectOption(label="🏆 Moneyline (Match Winner)", value="h2h"))
        if odds.get("spreads"):
            options.append(discord.SelectOption(label="📊 Point Spread", value="spreads"))
        if odds.get("totals"):
            options.append(discord.SelectOption(label="📈 Total Points (Over / Under)", value="totals"))
        if not options:
            options.append(
                discord.SelectOption(
                    label="⚠️ No odds available yet – try closer to tip-off",
                    value="__none__",
                )
            )
        sel = discord.ui.Select(placeholder="📋 Select bet type…", options=options)
        sel.callback = self._cb_type
        self.add_item(sel)
        self._add_back(self._cb_back_to_game, row=1)
        self._add_quit(row=1)

    def _render_step_outcome(self) -> None:
        self.clear_items()
        g    = self.selected_game or {}
        odds = g.get("odds", {})
        bet_type = self.selected_type
        options: List[discord.SelectOption] = []

        if bet_type == "h2h":
            for team, price in (odds.get("h2h") or {}).items():
                prob = int(implied_prob(price) * 100)
                label = f"{team}  ({fmt_odds(price)})"[:100]
                desc  = f"Implied win probability: ~{prob}%"
                options.append(discord.SelectOption(label=label, description=desc,
                                                    value=f"{team}|{price}|None", emoji="🏆"))

        elif bet_type == "spreads":
            for team, d in (odds.get("spreads") or {}).items():
                pt    = d["point"]
                price = d["price"]
                pt_str = f"{'+' if pt > 0 else ''}{pt}"
                label = f"{team}  {pt_str}  ({fmt_odds(price)})"[:100]
                options.append(discord.SelectOption(label=label,
                                                    value=f"{team}|{price}|{pt}", emoji="📊"))

        elif bet_type == "totals":
            for side, d in (odds.get("totals") or {}).items():
                pt    = d["point"]
                price = d["price"]
                label = f"{side} {pt}  ({fmt_odds(price)})"[:100]
                emoji = "📈" if side == "Over" else "📉"
                options.append(discord.SelectOption(label=label,
                                                    value=f"{side}|{price}|{pt}", emoji=emoji))

        if not options:
            options.append(discord.SelectOption(label="No odds available", value="__none__"))

        sel = discord.ui.Select(placeholder="🎯 Select your pick…", options=options)
        sel.callback = self._cb_outcome
        self.add_item(sel)
        self._add_back(self._cb_back_to_type, row=1)
        self._add_quit(row=1)

    def _render_step_confirm(self) -> None:
        self.clear_items()
        g       = self.selected_game or {}
        outcome = self.selected_outcome or {}
        profit  = calc_profit(self.stake or 0, outcome.get("odds", -110))
        total   = (self.stake or 0) + profit

        confirm = discord.ui.Button(
            label=f"✅  Place Bet  ({CURRENCY}{total:.0f} return)",
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
        full = await self.cog.fetcher.get_game_with_odds(val)
        self.selected_game = full or next((g for g in self.games if g["event_id"] == val), None)
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
        modal = AmountModal(max_balance=self.balance)
        await interaction.response.send_modal(modal)
        timed_out = await modal.wait()
        if timed_out or modal.value is None:
            return
        self.stake = modal.value
        self._render_step_confirm()
        await self.message.edit(embed=self._build_embed(), view=self)

    async def _cb_confirm(self, interaction: discord.Interaction) -> None:
        if not await self._check(interaction):
            return
        await interaction.response.defer()
        g       = self.selected_game or {}
        outcome = self.selected_outcome or {}
        stake   = self.stake or 0.0
        profit  = calc_profit(stake, outcome["odds"])

        ok = await self.cog.economy.deduct(interaction.guild_id, self.author_id, stake)
        if not ok:
            await self.message.edit(
                content="❌ Insufficient balance.", embed=None, view=None
            )
            self.stop()
            return

        bet_id = self.cog.bets.place_bet(
            interaction.guild_id,
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
        await self.cog.economy.record_bet_placed(interaction.guild_id, self.author_id, stake)

        embed = discord.Embed(title="✅ Bet Placed!", color=discord.Color.green())
        embed.add_field(name="Bet ID",    value=f"`{bet_id}`",                       inline=True)
        embed.add_field(name="Game",      value=f"{g['away_team']} @ {g['home_team']}",inline=False)
        embed.add_field(name="Bet Type",  value=TYPE_LABELS.get(self.selected_type, self.selected_type), inline=True)
        embed.add_field(name="Your Pick", value=f"**{outcome['selection']}**  ({fmt_odds(outcome['odds'])})", inline=True)
        if outcome.get("point") is not None:
            pt = outcome["point"]
            embed.add_field(name="Line", value=f"{'+' if pt > 0 else ''}{pt}", inline=True)
        embed.add_field(name="Stake",           value=f"{CURRENCY}**{stake:.0f}**",       inline=True)
        embed.add_field(name="Potential Profit", value=f"{CURRENCY}**{profit:.0f}**",      inline=True)
        embed.add_field(name="Total Return",    value=f"{CURRENCY}**{stake + profit:.0f}**",inline=True)
        embed.set_footer(text="Results settle automatically after the game ends. Use /bet mybets to check.")
        await self.message.edit(embed=embed, view=None)
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
        steps = {
            None: "Step 1 / 4 — Select a Game",
        }
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
            bm  = g.get("bookmaker", "")
            val = f"**{g['away_team']}** @ **{g['home_team']}**\n{_discord_ts(g['commence_time'])}"
            if bm:
                val += f"\nOdds: {bm}"
            embed.add_field(name="Game", value=val, inline=False)

        if self.selected_type:
            embed.add_field(name="Bet Type", value=TYPE_LABELS.get(self.selected_type, self.selected_type), inline=True)

        if self.selected_outcome:
            o = self.selected_outcome
            pick_str = f"**{o['selection']}**  ({fmt_odds(o['odds'])})"
            if o.get("point") is not None:
                pt = o["point"]
                pick_str += f"  Line: {'+' if pt > 0 else ''}{pt}"
            embed.add_field(name="Your Pick", value=pick_str, inline=True)

        if self.stake is not None and self.selected_outcome:
            profit = calc_profit(self.stake, self.selected_outcome["odds"])
            embed.add_field(name="Stake",          value=f"{CURRENCY}**{self.stake:.0f}**", inline=True)
            embed.add_field(name="Profit If Win",  value=f"{CURRENCY}**{profit:.0f}**",    inline=True)
            embed.add_field(name="Total Return",   value=f"{CURRENCY}**{self.stake+profit:.0f}**", inline=True)

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
    """Paginated NBA schedule with live scores."""

    PAGE_SIZE = 5

    def __init__(self, games: List[Dict], author_id: int) -> None:
        super().__init__(timeout=120)
        self.games     = games
        self.author_id = author_id
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
            if state == "STATUS_IN_PROGRESS":
                status = f"🔴 **LIVE**  {g['away_score']} – {g['home_score']}"
            elif g.get("completed"):
                status = f"✅ Final  **{g['away_score']} – {g['home_score']}**"
            else:
                status = _discord_ts(g.get("commence_time", ""))

            away_rec = f" ({g['away_record']})" if g.get("away_record") else ""
            home_rec = f" ({g['home_record']})" if g.get("home_record") else ""
            name = f"{g['away_team']}{away_rec} @ {g['home_team']}{home_rec}"
            embed.add_field(name=name, value=status, inline=False)

        embed.set_footer(text="Use /bet place to place a bet on any upcoming game.")
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
        # Caller refreshes the games list from outside; here we just re-render
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
            w      = e.get("bets_won", 0)
            l      = e.get("bets_lost", 0)
            total_bets = w + l
            win_pct = f"{w/total_bets*100:.0f}%" if total_bets > 0 else "—"
            profit  = e.get("total_returned", 0.0) - e.get("total_wagered", 0.0)
            p_str   = f"+{profit:.0f}" if profit >= 0 else f"{profit:.0f}"
            lines.append(
                f"{medal} **{name}**\n"
                f"　{CURRENCY}`{e.get('balance', 0):.0f}` · "
                f"W/L `{w}/{l}` · Win% `{win_pct}` · P/L `{p_str}`"
            )
        embed.description = "\n".join(lines) if lines else "No players yet."
        embed.set_footer(
            text=f"{start + 1}–{start + len(chunk)} of {len(self.entries)} players"
        )
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
# My Bets view (with per-item cancel buttons)
# ══════════════════════════════════════════════════════════════════════════════

class _CancelBetButton(discord.ui.Button):
    """A cancel button that knows which bet ID it belongs to."""

    def __init__(self, bet_id: str, row: int = 1) -> None:
        super().__init__(
            label=f"Cancel {bet_id}",
            style=discord.ButtonStyle.secondary,
            emoji="🗑️",
            row=row,
        )
        self.bet_id = bet_id

    async def callback(self, interaction: discord.Interaction) -> None:
        v: MyBetsView = self.view  # type: ignore[assignment]
        if interaction.user.id != v.author_id:
            return await interaction.response.send_message("Not your bets.", ephemeral=True)

        await interaction.response.defer()
        cancelled = v.cog.bets.cancel_bet(v.guild_id, self.bet_id)
        if cancelled:
            await v.cog.economy.add(v.guild_id, v.author_id, cancelled["stake"])
            # Refresh list
            v.bets = v.cog.bets.get_user_bets(v.guild_id, v.author_id, "pending")
            v.page = min(v.page, max(0, math.ceil(len(v.bets) / v.PAGE_SIZE) - 1))
            v._rebuild()
            await v.message.edit(
                content=f"✅ Bet `{self.bet_id}` cancelled. {CURRENCY}**{cancelled['stake']:.0f}** refunded.",
                embed=v.build_embed(),
                view=v,
            )
        else:
            await interaction.followup.send("Bet not found or already settled.", ephemeral=True)


class MyBetsView(discord.ui.View):
    """Paginated active-bets view with inline cancel buttons."""

    PAGE_SIZE = 3

    def __init__(
        self,
        bets: List[Dict],
        cog: "NBABetting",
        author_id: int,
        guild_id: int,
        title: str = "📋 My Active Bets",
        show_cancel: bool = True,
    ) -> None:
        super().__init__(timeout=120)
        self.bets        = bets
        self.cog         = cog
        self.author_id   = author_id
        self.guild_id    = guild_id
        self.title       = title
        self.show_cancel = show_cancel
        self.page        = 0
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

        if self.show_cancel:
            start = self.page * self.PAGE_SIZE
            chunk = self.bets[start: start + self.PAGE_SIZE]
            for bet in chunk:
                if bet["status"] == "pending":
                    self.add_item(_CancelBetButton(bet_id=bet["id"], row=1))

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
            if bet.get("point") is not None:
                pt   = bet["point"]
                line = f"  Line: {'+' if pt > 0 else ''}{pt}"
            payout_str = ""
            if bet["status"] == "won" and bet.get("actual_payout") is not None:
                payout_str = f"\n**Won:** {CURRENCY}**{bet['actual_payout']:.0f}**"
            elif bet["status"] == "push":
                payout_str = f"\n**Push** – stake returned"
            val = (
                f"**Game:** {bet['away_team']} @ {bet['home_team']}\n"
                f"**Type:** {tl}  |  **Pick:** {bet['selection']}  ({fmt_odds(bet['odds'])}){line}\n"
                f"**Stake:** {CURRENCY}{bet['stake']:.0f}  →  "
                f"**Potential Win:** {CURRENCY}{bet['potential_payout']:.0f}"
                f"{payout_str}\n"
                f"**Placed:** {_discord_ts(bet['placed_at'])}"
            )
            embed.add_field(name=f"{emoji} `{bet['id']}`  —  {bet['status'].upper()}", value=val, inline=False)
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
        self.confirmed = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Not your action.", ephemeral=True)
        self.confirmed = False
        self.stop()
        await interaction.response.defer()

    async def on_timeout(self) -> None:
        self.confirmed = None
        self.stop()
