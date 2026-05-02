from redbot.core.bot import Red

from .gambling import Gambling


async def setup(bot: Red) -> None:
    await bot.add_cog(Gambling(bot))
