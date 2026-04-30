from redbot.core.bot import Red

from .mediacaption import MediaCaption


async def setup(bot: Red) -> None:
    cog = MediaCaption(bot)
    await bot.add_cog(cog)
