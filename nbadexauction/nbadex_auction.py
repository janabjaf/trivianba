import discord
import asyncio
import time
import humanize
from datetime import datetime, timedelta
from typing import Optional, Union
from redbot.core import commands, Config, checks

class NBAdexAuction(commands.Cog):
    """
    Advanced Auction System for NBAdex.
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9283746510, force_registration=True)
        default_guild = {
            "log_channel": None,
            "manager_roles": [],
            "auctions": {}
        }
        self.config.register_guild(**default_guild)
        self.active_tasks = {}

    @commands.group()
    @commands.guild_only()
    async def auctionset(self, ctx):
        """Settings for NBAdex Auction."""
        pass

    @auctionset.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def channel(self, ctx, channel: discord.TextChannel):
        """Set the logging channel for auctions."""
        await self.config.guild(ctx.guild).log_channel.set(channel.id)
        await ctx.send(f"✅ Auction logging channel set to {channel.mention}")

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    async def auction(self, ctx):
        """Auction Management Commands."""
        await ctx.send_help()

    @auction.command()
    @checks.admin_or_permissions(manage_messages=True)
    async def start(self, ctx, item_name: str, duration_mins: int, min_bid: int, buyout: Optional[int] = None):
        """Start a new auction."""
        guild_data = await self.config.guild(ctx.guild).all()
        log_channel_id = guild_data["log_channel"]
        
        if not log_channel_id:
            return await ctx.send("❌ Please set a logging channel first using `[p]auctionset channel`.")

        log_channel = ctx.guild.get_channel(log_channel_id)
        if not log_channel:
            return await ctx.send("❌ Logging channel not found. Please re-set it.")

        # Check if there's already an active auction in this channel
        async with self.config.guild(ctx.guild).auctions() as auctions:
            for aid, data in auctions.items():
                if data["channel_id"] == ctx.channel.id and data["status"] == "active":
                    return await ctx.send("❌ There is already an active auction in this channel. End it first.")

        end_time = time.time() + (duration_mins * 60)
        
        auction_id = str(ctx.message.id)
        auction_data = {
            "id": auction_id,
            "item": item_name,
            "min_bid": min_bid,
            "buyout": buyout,
            "current_bid": 0,
            "highest_bidder": None,
            "end_time": end_time,
            "status": "active",
            "channel_id": ctx.channel.id,
            "message_id": None,
            "history": []
        }

        embed = self.make_auction_embed(auction_data)
        msg = await ctx.send(embed=embed)
        auction_data["message_id"] = msg.id
        
        async with self.config.guild(ctx.guild).auctions() as auctions:
            auctions[auction_id] = auction_data

        # Start background timer task
        task = asyncio.create_task(self.auction_timer(ctx, auction_id))
        self.active_tasks[auction_id] = task
        
        log_embed = discord.Embed(title="🚀 Auction Started", color=discord.Color.blue())
        log_embed.add_field(name="Item", value=item_name)
        log_embed.add_field(name="Duration", value=f"{duration_mins}m")
        log_embed.add_field(name="Min Bid", value=f"`{min_bid}`")
        if buyout: log_embed.add_field(name="Buyout", value=f"`{buyout}`")
        log_embed.set_footer(text=f"Started by {ctx.author} | ID: {auction_id}")
        await log_channel.send(embed=log_embed)

    @commands.command()
    @commands.guild_only()
    async def bid(self, ctx, amount: int):
        """Place a bid on the active auction in this channel."""
        async with self.config.guild(ctx.guild).auctions() as auctions:
            # Find the active auction in the current channel
            target_id = None
            for aid, data in auctions.items():
                if data["channel_id"] == ctx.channel.id and data["status"] == "active":
                    target_id = aid
                    break
            
            if not target_id:
                return await ctx.send("❌ There is no active auction in this channel.")
            
            auc = auctions[target_id]
            
            if amount < auc["min_bid"]:
                return await ctx.send(f"❌ Minimum bid is `{auc['min_bid']}`.")
            
            if amount <= auc["current_bid"]:
                return await ctx.send(f"❌ Bid must be higher than the current bid of `{auc['current_bid']}`.")

            # Anti-snipe: If bid in last 60 seconds, extend by 60 seconds
            time_left = auc["end_time"] - time.time()
            if time_left < 60:
                auc["end_time"] += 60
                await ctx.send("⏱️ **Anti-snipe!** Auction extended by 60s.")

            auc["current_bid"] = amount
            auc["highest_bidder"] = ctx.author.id
            auc["history"].append({"user": ctx.author.id, "amount": amount, "time": time.time()})
            
            # Check buyout
            is_buyout = False
            if auc["buyout"] and amount >= auc["buyout"]:
                is_buyout = True
                auc["status"] = "sold"

            # Update message
            try:
                msg = await ctx.channel.fetch_message(auc["message_id"])
                await msg.edit(embed=self.make_auction_embed(auc))
            except:
                pass

            log_channel_id = await self.config.guild(ctx.guild).log_channel()
            if log_channel_id:
                log_channel = ctx.guild.get_channel(log_channel_id)
                if log_channel:
                    await log_channel.send(f"💰 **New Bid** | **{auc['item']}** | {ctx.author.mention} bid `{amount}`")

            if is_buyout:
                await ctx.send(f"🔥 **BUYOUT!** {ctx.author.mention} has bought **{auc['item']}** for `{amount}`!")
                # Call end_auction from outside the lock if possible, but for simplicity here we just finalize
                # The timer task will pick up the 'sold' status
            else:
                await ctx.message.add_reaction("✅")

    def make_auction_embed(self, auc):
        time_left = max(0, int(auc["end_time"] - time.time()))
        status_color = discord.Color.green() if auc["status"] == "active" else discord.Color.red()
        if auc["status"] == "sold": status_color = discord.Color.gold()
        
        embed = discord.Embed(title=f"📦 Auction: {auc['item']}", color=status_color)
        embed.add_field(name="Current Bid", value=f"`{auc['current_bid']}`" if auc['current_bid'] > 0 else f"Min: `{auc['min_bid']}`", inline=True)
        embed.add_field(name="Highest Bidder", value=f"<@{auc['highest_bidder']}>" if auc['highest_bidder'] else "None", inline=True)
        
        if auc["buyout"]:
            embed.add_field(name="Buyout", value=f"`{auc['buyout']}`", inline=True)
            
        if auc["status"] == "active":
            embed.add_field(name="Ends", value=f"<t:{int(auc['end_time'])}:R>", inline=True)
            if auc["history"]:
                last_3 = auc["history"][-3:]
                history_text = "\n".join([f"<@{h['user']}>: `{h['amount']}`" for h in reversed(last_3)])
                embed.add_field(name="Recent Bids", value=history_text, inline=False)
            embed.set_footer(text=f"Use .bid <amount> to participate")
        else:
            embed.add_field(name="Status", value=f"**{auc['status'].upper()}**", inline=False)
            if auc["highest_bidder"]:
                embed.description = f"Winner: <@{auc['highest_bidder']}> for `{auc['current_bid']}`"
            
        return embed

    async def auction_timer(self, ctx, auction_id):
        while True:
            await asyncio.sleep(10)
            async with self.config.guild(ctx.guild).auctions() as auctions:
                if auction_id not in auctions or auctions[auction_id]["status"] != "active":
                    break
                
                auc = auctions[auction_id]
                if time.time() >= auc["end_time"]:
                    await self.end_auction(ctx.guild, auction_id)
                    break
                
                # Periodically update the timer embed if needed (Discord <t:R> handles it mostly)
                pass

    async def end_auction(self, guild, auction_id, winner=None):
        async with self.config.guild(guild).auctions() as auctions:
            if auction_id not in auctions: return
            auc = auctions[auction_id]
            if auc["status"] not in ["active", "sold"]: return
            
            if auc["status"] == "active":
                auc["status"] = "ended" if auc["highest_bidder"] else "expired"
            
            # Final update
            channel = guild.get_channel(auc["channel_id"])
            if channel:
                try:
                    msg = await channel.fetch_message(auc["message_id"])
                    await msg.edit(embed=self.make_auction_embed(auc))
                except:
                    pass

            log_channel_id = await self.config.guild(guild).log_channel()
            if log_channel_id:
                log_channel = guild.get_channel(log_channel_id)
                if log_channel:
                    if auc["highest_bidder"]:
                        winner_mention = f"<@{auc['highest_bidder']}>"
                        await log_channel.send(f"🏁 **Auction Ended**\nItem: {auc['item']}\nWinner: {winner_mention}\nFinal Price: `{auc['current_bid']}`")
                        if channel:
                            await channel.send(f"🏁 The auction for **{auc['item']}** has ended! Winner: {winner_mention} for `{auc['current_bid']}`!")
                    else:
                        await log_channel.send(f"❌ **Auction Expired**\nItem: {auc['item']}\nReason: No bids placed.")
                        if channel:
                            await channel.send(f"❌ The auction for **{auc['item']}** has expired with no bids.")
