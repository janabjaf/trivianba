from .nba_fantasy import NBAFantasy

async def setup(bot):
    await bot.add_cog(NBAFantasy(bot))