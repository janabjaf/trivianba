from .nbadex_auction import NBAdexAuction

async def setup(bot):
    await bot.add_cog(NBAdexAuction(bot))
