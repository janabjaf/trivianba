from .nbafantasy import NBAFantasy

async def setup(bot):
    await bot.add_cog(NBAFantasy(bot))