"""NBABetting – Real-money-style NBA betting cog for Red-DiscordBot."""
from .nbabetting import NBABetting


async def setup(bot) -> None:
    await bot.add_cog(NBABetting(bot))
