from .partygames import PartyGames


async def setup(bot):
    await bot.add_cog(PartyGames(bot))
