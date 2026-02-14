from .f1trivia import F1Trivia

async def setup(bot):
    await bot.add_cog(F1Trivia(bot))
