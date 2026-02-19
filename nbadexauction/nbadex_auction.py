import discord
import asyncio
import time
import re
from datetime import datetime
from typing import Optional, Union
from redbot.core import commands, Config, checks
from discord import app_commands

class NBAdexAuction(commands.Cog):
    """
    Advanced Auction System for NBAdex with Ping Roles and Reminders.
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

    def parse_amount(self, amount_str: Union[str, int]) -> Optional[int]:
        if isinstance(amount_str, int):
            return amount_str
        
        amount_str = str(amount_str).lower().strip().replace(",", "")
        multipliers = {'k': 1000, 'm': 1000000, 'b': 1000000000}
        
        match = re.match(r"(\d+(?:\.\d+)?)([kmb])?", amount_str)
        if not match:
            return None
        
        val, mult = match.groups()
        val = float(val)
        if mult:
            val *= multipliers[mult]
        return int(val)

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

    @auction.command(name="start")
    @checks.admin_or_permissions(manage_messages=True)
    async def prefix_start(self, ctx, duration_mins: int, min_bid: str, bidding_channel: discord.TextChannel, item: str, buyout: str = None, min_increase: str = None):
        """
        Start an auction.
        Usage: .auction start <duration_mins> <min_bid> <bidding_channel> <item> [buyout] [min_increase]
        """
        parsed_min = self.parse_amount(min_bid)
        parsed_buyout = self.parse_amount(buyout) if buyout else None
        parsed_increase = self.parse_amount(min_increase) if min_increase else None

        if parsed_min is None:
            return await ctx.send("❌ Invalid minimum bid format. Use 100k, 1m, etc.")

        await self._start_auction(
            ctx=ctx,
            item=item,
            bidding_channel=bidding_channel,
            duration_mins=duration_mins,
            parsed_min=parsed_min,
            parsed_buyout=parsed_buyout,
            parsed_increase=parsed_increase,
            user=ctx.author
        )

    @auction.command()
    @checks.admin_or_permissions(manage_messages=True)
    async def end(self, ctx):
        """Force end the active auction in this channel."""
        async with self.config.guild(ctx.guild).auctions() as auctions:
            target_id = None
            for aid, data in auctions.items():
                if data["channel_id"] == ctx.channel.id and data["status"] == "active":
                    target_id = aid
                    break
            
            if not target_id:
                return await ctx.send("❌ No active auction in this channel.")
            
            auc = auctions[target_id]
            auc["status"] = "ended" if auc["highest_bidder"] else "expired"
            
            channel = ctx.channel
            msg = f"🏁 The auction for **{auc['item']}** has been manually ended!"
            if auc["highest_bidder"]:
                msg += f" Winner: <@{auc['highest_bidder']}> for `{auc['current_bid']:,}`!"
            
            await channel.send(embed=discord.Embed(description=msg, color=discord.Color.red()))
            
            try:
                m = await channel.fetch_message(auc["message_id"])
                await m.edit(embed=self.make_auction_embed(auc))
            except: pass
            
            ping_role = ctx.guild.get_role(auc["ping_role_id"])
            if ping_role:
                try: await ping_role.delete(reason="Auction manually ended")
                except: pass

        await ctx.send("✅ Auction ended.")

    @auction.command()
    @checks.admin_or_permissions(manage_messages=True)
    async def extend(self, ctx, minutes: int):
        """Extend the active auction in this channel by X minutes."""
        async with self.config.guild(ctx.guild).auctions() as auctions:
            target_id = None
            for aid, data in auctions.items():
                if data["channel_id"] == ctx.channel.id and data["status"] == "active":
                    target_id = aid
                    break
            
            if not target_id:
                return await ctx.send("❌ No active auction in this channel.")
            
            auc = auctions[target_id]
            auc["end_time"] += (minutes * 60)
            
            try:
                m = await ctx.channel.fetch_message(auc["message_id"])
                await m.edit(embed=self.make_auction_embed(auc))
            except: pass
            
        await ctx.send(f"✅ Auction extended by {minutes} minutes.")

    @app_commands.command(name="auction_start", description="Start a new auction")
    @app_commands.describe(
        item="The name of the item being auctioned",
        bidding_channel="The channel where bidding will happen",
        duration_mins="Auction duration in minutes",
        min_bid="Starting bid (e.g. 100k, 1m)",
        buyout="Optional buyout price (e.g. 5m)",
        min_increase="Minimum bid increase (e.g. 10k, 50k)",
        thumbnail_url="Optional URL for the auction image thumbnail"
    )
    async def slash_start(
        self, 
        interaction: discord.Interaction, 
        item: str, 
        bidding_channel: discord.TextChannel,
        duration_mins: int, 
        min_bid: str, 
        buyout: Optional[str] = None,
        min_increase: Optional[str] = None,
        thumbnail_url: Optional[str] = None
    ):
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("❌ You don't have permission to start auctions.", ephemeral=True)

        parsed_min = self.parse_amount(min_bid)
        parsed_buyout = self.parse_amount(buyout) if buyout else None
        parsed_increase = self.parse_amount(min_increase) if min_increase else None
        
        if parsed_min is None:
            return await interaction.response.send_message("❌ Invalid minimum bid format. Use 100k, 1m, etc.", ephemeral=True)

        # Defer immediately to prevent "Thinking..." getting stuck
        await interaction.response.defer()
        
        await self._start_auction(
            interaction=interaction,
            item=item,
            bidding_channel=bidding_channel,
            duration_mins=duration_mins,
            parsed_min=parsed_min,
            parsed_buyout=parsed_buyout,
            parsed_increase=parsed_increase,
            thumbnail_url=thumbnail_url,
            user=interaction.user
        )

    async def _start_auction(self, ctx=None, interaction=None, item=None, bidding_channel=None, duration_mins=None, parsed_min=None, parsed_buyout=None, parsed_increase=None, thumbnail_url=None, user=None):
        guild = ctx.guild if ctx else interaction.guild
        log_channel_id = await self.config.guild(guild).log_channel()
        
        log_channel = guild.get_channel(log_channel_id) if log_channel_id else None
        
        # Create unique ping role for this auction
        role_name = f"Auction: {item}"[:32]
        ping_role = await guild.create_role(name=role_name, mentionable=True, reason="Auction start")

        end_time = time.time() + (duration_mins * 60)
        auction_id = str(interaction.id if interaction else ctx.message.id)
        
        auction_data = {
            "id": auction_id,
            "item": item,
            "min_bid": parsed_min,
            "buyout": parsed_buyout,
            "min_increase": parsed_increase,
            "current_bid": 0,
            "highest_bidder": None,
            "end_time": end_time,
            "status": "active",
            "channel_id": bidding_channel.id,
            "message_id": None,
            "ping_role_id": ping_role.id,
            "thumbnail_url": thumbnail_url,
            "history": [],
            "reminders_sent": []
        }

        embed = self.make_auction_embed(auction_data)
        msg = await bidding_channel.send(content=ping_role.mention, embed=embed)
        auction_data["message_id"] = msg.id
        
        async with self.config.guild(guild).auctions() as auctions:
            auctions[auction_id] = auction_data

        # Cleanup existing task if any
        if auction_id in self.active_tasks:
            self.active_tasks[auction_id].cancel()

        self.active_tasks[auction_id] = asyncio.create_task(self.auction_timer(guild, auction_id))
        
        if log_channel:
            log_embed = discord.Embed(title="🚀 Auction Started", color=discord.Color.blue())
            log_embed.add_field(name="Item", value=item)
            log_embed.add_field(name="Channel", value=bidding_channel.mention)
            log_embed.add_field(name="Role", value=ping_role.mention)
            if thumbnail_url: log_embed.set_thumbnail(url=thumbnail_url)
            log_embed.set_footer(text=f"Started by {user}")
            await log_channel.send(embed=log_embed)
        
        success_msg = f"✅ Auction for **{item}** started in {bidding_channel.mention}!"
        if interaction: await interaction.followup.send(success_msg)
        else: await ctx.send(success_msg)

    @app_commands.command(name="auction_cancel", description="Cancel an active auction")
    @app_commands.describe(auction_id="ID of the auction to cancel (found in logs or footer)")
    @checks.admin_or_permissions(manage_messages=True)
    async def slash_cancel(self, interaction: discord.Interaction, auction_id: str):
        async with self.config.guild(interaction.guild).auctions() as auctions:
            if auction_id not in auctions:
                return await interaction.response.send_message("❌ Auction not found.", ephemeral=True)
            
            auc = auctions[auction_id]
            if auc["status"] != "active":
                return await interaction.response.send_message("❌ This auction is already ended.", ephemeral=True)
            
            auc["status"] = "cancelled"
            
            # Cleanup
            channel = interaction.guild.get_channel(auc["channel_id"])
            if channel:
                try:
                    m = await channel.fetch_message(auc["message_id"])
                    await m.edit(embed=self.make_auction_embed(auc))
                    await channel.send(f"🚫 The auction for **{auc['item']}** has been cancelled by an administrator.")
                except: pass
            
            ping_role = interaction.guild.get_role(auc["ping_role_id"])
            if ping_role:
                try: await ping_role.delete(reason="Auction cancelled")
                except: pass
                
        await interaction.response.send_message(f"✅ Auction `{auction_id}` cancelled.")

    @commands.command()
    @commands.guild_only()
    async def bid(self, ctx, amount: str):
        """Place a bid (e.g. .bid 100k, .bid 1.5m)"""
        parsed_amount = self.parse_amount(amount)
        if parsed_amount is None:
            return await ctx.send("❌ Invalid amount. Use 100k, 1m, etc.")

        async with self.config.guild(ctx.guild).auctions() as auctions:
            # Find active auction in this channel
            target_id = None
            for aid, data in auctions.items():
                if data["channel_id"] == ctx.channel.id and data["status"] == "active":
                    target_id = aid
                    break
            
            if not target_id:
                return await ctx.send("❌ There is no active auction in this channel.")
            
            auc = auctions[target_id]
            
            if auc["highest_bidder"] == ctx.author.id:
                return await ctx.send("⚠️ You are already the highest bidder!")

            if parsed_amount < auc["min_bid"]:
                return await ctx.send(f"❌ Minimum bid is `{auc['min_bid']:,}`.")
            
            if parsed_amount <= auc["current_bid"]:
                return await ctx.send(f"❌ Your bid must be higher than the current bid of `{auc['current_bid']:,}`.")

            min_inc_val = auc.get("min_increase")
            if min_inc_val is None:
                min_inc_val = max(1000, int(auc["current_bid"] * 0.01))
            
            if auc["current_bid"] > 0 and (parsed_amount - auc["current_bid"]) < min_inc_val:
                return await ctx.send(f"⚠️ Minimum bid increase is `{min_inc_val:,}`. Try bidding `{auc['current_bid'] + min_inc_val:,}` or more.")

            time_left = auc["end_time"] - time.time()
            if time_left < 60:
                auc["end_time"] += 60
                await ctx.send("⏱️ **Anti-snipe!** Auction extended by 60 seconds.")

            old_bidder_id = auc["highest_bidder"]
            auc["current_bid"] = parsed_amount
            auc["highest_bidder"] = ctx.author.id
            auc["history"].append({"user": ctx.author.id, "amount": parsed_amount, "time": time.time()})
            
            ping_role = ctx.guild.get_role(auc["ping_role_id"])
            if ping_role:
                try: await ctx.author.add_roles(ping_role)
                except: pass

            is_buyout = False
            if auc["buyout"] and parsed_amount >= auc["buyout"]:
                is_buyout = True
                auc["status"] = "sold"

            try:
                msg = await ctx.channel.fetch_message(auc["message_id"])
                await msg.edit(embed=self.make_auction_embed(auc))
            except: pass

            log_channel_id = await self.config.guild(ctx.guild).log_channel()
            if log_channel_id:
                log_channel = ctx.guild.get_channel(log_channel_id)
                if log_channel:
                    await log_channel.send(f"💰 **New Bid** | **{auc['item']}** | {ctx.author.mention} bid `{parsed_amount:,}`")

            if old_bidder_id and old_bidder_id != ctx.author.id:
                await ctx.send(f"🔔 <@{old_bidder_id}>, you have been outbid on **{auc['item']}**!")

            if is_buyout:
                await ctx.send(f"🔥 **BUYOUT!** {ctx.author.mention} has bought **{auc['item']}** for `{parsed_amount:,}`!")
            else:
                await ctx.message.add_reaction("✅")

    def make_auction_embed(self, auc):
        status_color = discord.Color.green() if auc["status"] == "active" else discord.Color.gold() if auc["status"] == "sold" else discord.Color.red()
        
        embed = discord.Embed(title=f"📦 Auction: {auc['item']}", color=status_color)
        embed.add_field(name="Current Bid", value=f"`{auc['current_bid']:,}`" if auc['current_bid'] > 0 else f"Min: `{auc['min_bid']:,}`", inline=True)
        embed.add_field(name="Highest Bidder", value=f"<@{auc['highest_bidder']}>" if auc['highest_bidder'] else "None", inline=True)
        
        if auc["buyout"]:
            embed.add_field(name="Buyout", value=f"`{auc['buyout']:,}`", inline=True)
        
        if auc.get("min_increase"):
            embed.add_field(name="Min Increase", value=f"`{auc['min_increase']:,}`", inline=True)
            
        if auc["status"] == "active":
            embed.add_field(name="Ends", value=f"<t:{int(auc['end_time'])}:R>", inline=True)
            if auc["history"]:
                history = "\n".join([f"<@{h['user']}>: `{h['amount']:,}`" for h in reversed(auc['history'][-5:])])
                embed.add_field(name="Recent Bids", value=history, inline=False)
            embed.set_footer(text=f"ID: {auc['id']} | Use .bid <amount> to participate")
        else:
            embed.add_field(name="Status", value=f"**{auc['status'].upper()}**", inline=False)
            if auc["highest_bidder"]:
                embed.description = f"Winner: <@{auc['highest_bidder']}> for `{auc['current_bid']:,}`"
        
        if auc.get("thumbnail_url"):
            embed.set_image(url=auc["thumbnail_url"])
            
        return embed

    async def auction_timer(self, guild, auction_id):
        while True:
            await asyncio.sleep(30)
            async with self.config.guild(guild).auctions() as auctions:
                if auction_id not in auctions: break
                auc = auctions[auction_id]
                if auc["status"] != "active": break
                
                now = time.time()
                time_left = auc["end_time"] - now
                channel = guild.get_channel(auc["channel_id"])
                ping_role = guild.get_role(auc["ping_role_id"])
                
                for reminder_min in [60, 10]:
                    reminder_key = f"reminder_{reminder_min}"
                    if time_left <= (reminder_min * 60) and reminder_key not in auc["reminders_sent"]:
                        if channel and ping_role:
                            await channel.send(f"⏰ {ping_role.mention} - **{auc['item']}** ends in {reminder_min} minutes!")
                        auc["reminders_sent"].append(reminder_key)

                if now >= auc["end_time"]:
                    auc["status"] = "ended" if auc["highest_bidder"] else "expired"
                    if channel:
                        msg = f"🏁 The auction for **{auc['item']}** has ended!"
                        if auc["highest_bidder"]:
                            msg += f" Winner: <@{auc['highest_bidder']}> for `{auc['current_bid']:,}`!"
                        else:
                            msg += " Expired with no bids."
                        
                        ping_content = ping_role.mention if ping_role else ""
                        await channel.send(content=ping_content, embed=discord.Embed(description=msg, color=discord.Color.red()))
                        
                        try:
                            m = await channel.fetch_message(auc["message_id"])
                            await m.edit(embed=self.make_auction_embed(auc))
                        except: pass
                    
                    if ping_role:
                        try: await ping_role.delete(reason="Auction ended")
                        except: pass
                    break
        # Cleanup task reference
        if auction_id in self.active_tasks:
            del self.active_tasks[auction_id]
