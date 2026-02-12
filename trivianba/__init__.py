from .nba_trivia import NBATrivia

async def setup(bot):
    await bot.add_cog(NBATrivia(bot))
