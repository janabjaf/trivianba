"""economy.py – Per-guild economy manager backed by Red's Config."""
from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List

import discord
from redbot.core import Config

if TYPE_CHECKING:
    from redbot.core.bot import Red

STARTING_BALANCE: float = 1000.0
CURRENCY: str = "\U0001f4b0"


class Economy:
    """Wraps Red Config to provide per-guild, per-user economy operations."""

    def __init__(self, config: Config, bot: "Red") -> None:
        self.config = config
        self.bot = bot

    # ── Single-user helpers ────────────────────────────────────────────────────

    async def get_data(self, guild_id: int, user_id: int) -> Dict:
        return await self.config.member_from_ids(guild_id, user_id).all()

    async def get_balance(self, guild_id: int, user_id: int) -> float:
        return await self.config.member_from_ids(guild_id, user_id).balance()

    async def add(self, guild_id: int, user_id: int, amount: float) -> float:
        """Add amount and return new balance."""
        conf    = self.config.member_from_ids(guild_id, user_id)
        bal     = await conf.balance()
        new_bal = round(bal + amount, 2)
        await conf.balance.set(new_bal)
        return new_bal

    async def deduct(self, guild_id: int, user_id: int, amount: float) -> bool:
        """Deduct amount. Returns False if insufficient funds."""
        conf = self.config.member_from_ids(guild_id, user_id)
        bal  = await conf.balance()
        if bal < amount:
            return False
        await conf.balance.set(round(bal - amount, 2))
        return True

    async def set_balance(self, guild_id: int, user_id: int, amount: float) -> None:
        await self.config.member_from_ids(guild_id, user_id).balance.set(round(amount, 2))

    async def record_bet_placed(self, guild_id: int, user_id: int, stake: float) -> None:
        conf = self.config.member_from_ids(guild_id, user_id)
        tw   = await conf.total_wagered()
        await conf.total_wagered.set(round(tw + stake, 2))
        bp   = await conf.bets_placed()
        await conf.bets_placed.set(bp + 1)

    async def record_win(self, guild_id: int, user_id: int, payout: float) -> None:
        """
        Record a win.  payout = full amount returned to player (stake + profit).
        This is what gets added to total_returned so that P/L = returned - wagered is correct.
        """
        conf = self.config.member_from_ids(guild_id, user_id)
        tr   = await conf.total_returned()
        await conf.total_returned.set(round(tr + payout, 2))
        bw   = await conf.bets_won()
        await conf.bets_won.set(bw + 1)

    async def record_loss(self, guild_id: int, user_id: int) -> None:
        conf = self.config.member_from_ids(guild_id, user_id)
        bl   = await conf.bets_lost()
        await conf.bets_lost.set(bl + 1)

    async def record_push(self, guild_id: int, user_id: int, stake: float) -> None:
        """Record a push.  stake is returned, so add it to total_returned."""
        conf = self.config.member_from_ids(guild_id, user_id)
        tr   = await conf.total_returned()
        await conf.total_returned.set(round(tr + stake, 2))
        bpush = await conf.bets_push()
        await conf.bets_push.set(bpush + 1)

    # ── Bulk operations (admin) ────────────────────────────────────────────────

    async def reset_balance(self, guild_id: int, user_id: int) -> None:
        await self.config.member_from_ids(guild_id, user_id).balance.set(STARTING_BALANCE)

    async def reset_all_balances(self, guild: discord.Guild) -> int:
        """Reset every member's balance to starting value. Returns count."""
        all_data = await self.config.all_members(guild)
        count = 0
        for uid in all_data:
            await self.config.member_from_ids(guild.id, int(uid)).balance.set(STARTING_BALANCE)
            count += 1
        return count

    async def reset_all_stats(self, guild: discord.Guild) -> int:
        """Clear all betting stats (not balance). Returns count."""
        all_data = await self.config.all_members(guild)
        count = 0
        for uid in all_data:
            conf = self.config.member_from_ids(guild.id, int(uid))
            await conf.total_wagered.set(0.0)
            await conf.total_returned.set(0.0)
            await conf.bets_placed.set(0)
            await conf.bets_won.set(0)
            await conf.bets_lost.set(0)
            await conf.bets_push.set(0)
            count += 1
        return count

    # ── Leaderboard ───────────────────────────────────────────────────────────

    async def get_leaderboard(self, guild: discord.Guild) -> List[Dict]:
        """Return top-100 members sorted by balance desc."""
        all_data = await self.config.all_members(guild)
        entries  = [{"user_id": str(uid), **data} for uid, data in all_data.items()]
        entries.sort(key=lambda e: e.get("balance", 0.0), reverse=True)
        return entries[:100]
