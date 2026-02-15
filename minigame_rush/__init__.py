from .minigame_rush import MinigameRush

async def setup(bot):
    await bot.add_cog(MinigameRush(bot))
