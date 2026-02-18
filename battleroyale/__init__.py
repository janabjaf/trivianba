from redbot.core import commands
import asyncio

async def setup(bot):
    from .battleroyale import BattleRoyale
    await bot.add_cog(BattleRoyale(bot))
