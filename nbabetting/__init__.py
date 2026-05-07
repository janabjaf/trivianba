"""NBABetting – Real-money-style NBA betting cog for Red-DiscordBot."""
import sys as _sys

_PKG = __name__
for _mod in list(_sys.modules.keys()):
    if _mod.startswith(_PKG + "."):
        del _sys.modules[_mod]

from .nbabetting import NBABetting


async def setup(bot) -> None:
    await bot.add_cog(NBABetting(bot))
