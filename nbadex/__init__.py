from .nbadex import NBAdex


async def setup(bot):
    await bot.add_cog(NBAdex(bot))
