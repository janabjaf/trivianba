import asyncio
import random
import discord
from typing import Dict, List, Optional, Tuple
from ..game_base import BaseGame, VotingView
from ..game_data import (
    TRIVIA_QUESTIONS, WOULD_YOU_RATHER_QUESTIONS, PRICE_IS_RIGHT_ITEMS,
    GLADIATOR_FIGHTERS, generate_math_question, generate_bingo_card,
    format_bingo_card, check_bingo,
)


# ── Shared modal ──────────────────────────────────────────────────────────────

class TextModal(discord.ui.Modal):
    answer = discord.ui.TextInput(label="Your Answer", style=discord.TextStyle.short, max_length=200)

    def __init__(self, title: str, label: str, placeholder: str, storage: dict, key, max_length: int = 200):
        super().__init__(title=title)
        self.answer.label = label
        self.answer.placeholder = placeholder
        self.answer.max_length = max_length
        self._storage = storage
        self._key = key

    async def on_submit(self, interaction: discord.Interaction):
        self._storage[self._key] = self.answer.value
        await interaction.response.send_message("✅ Answer submitted!", ephemeral=True)


class SubmitView(discord.ui.View):
    def __init__(self, eligible: list, storage: dict, modal_kwargs: dict, timeout: float, button_label: str):
        super().__init__(timeout=timeout)
        self._eligible = eligible
        self._storage = storage
        self._modal_kwargs = modal_kwargs
        btn = discord.ui.Button(label=button_label, style=discord.ButtonStyle.primary)
        btn.callback = self._on_click
        self.add_item(btn)

    async def _on_click(self, interaction: discord.Interaction):
        if interaction.user not in self._eligible:
            await interaction.response.send_message("You're not in this game!", ephemeral=True)
            return
        modal = TextModal(**self._modal_kwargs, storage=self._storage, key=interaction.user)
        await interaction.response.send_modal(modal)
        if len(self._storage) >= len(self._eligible):
            self.stop()


# ── Trivia Clash ──────────────────────────────────────────────────────────────

class TriviaClash(BaseGame):
    GAME_INFO = {
        "name": "Trivia Clash",
        "description": "Classic trivia! Questions from Geography, Science, History, Pop Culture, and Math. First player to type the correct answer earns the point!",
        "min_players": 2,
        "max_players": 30,
        "emoji": "🎓",
        "duration": "10–20 min",
        "category": "Competition",
    }

    async def run(self):
        questions = random.sample(TRIVIA_QUESTIONS, 10)
        scores: Dict[discord.Member, int] = {p: 0 for p in self.players}

        intro = discord.Embed(
            title="🎓 Trivia Clash — Questions Begin!",
            description="**10 questions** across Geography, Science, History, Pop Culture, and Math!\n\n"
                        "⚡ First to type the correct answer earns **1 point**.\n"
                        "**25 seconds** per question.",
            color=discord.Color.blurple(),
        )
        await self.channel.send(embed=intro)
        if await self.wait_or_stop(5):
            return

        for q_num, q in enumerate(questions, 1):
            if self.is_stopped():
                return

            q_embed = discord.Embed(
                title=f"🎓 Question {q_num} / 10 — [{q['category']}]",
                description=f"**{q['question']}**",
                color=discord.Color.blurple(),
            )
            if "options" in q:
                q_embed.add_field(
                    name="Options",
                    value="\n".join(f"**{chr(65+i)}.** {opt}" for i, opt in enumerate(q["options"])),
                )
            await self.channel.send(embed=q_embed)

            correct = q["a"].lower()
            winner_msg = await self.listen_for_answer(
                check=lambda m, ans=correct, opts=q.get("options", []): (
                    m.channel == self.channel
                    and m.author in self.players
                    and (
                        ans in m.content.lower()
                        or any(
                            (chr(65+i) + ".") in m.content.upper()
                            or (chr(65+i) == m.content.upper().strip())
                            or (opt.lower() in m.content.lower())
                            for i, opt in enumerate(opts)
                            if opt.lower() == ans
                        )
                    )
                ),
                timeout=25.0,
            )

            if winner_msg:
                scores[winner_msg.author] = scores.get(winner_msg.author, 0) + 1
                await self.channel.send(
                    embed=discord.Embed(
                        title=f"✅ {winner_msg.author.display_name} got it!",
                        description=f"**Answer:** {q['a'].title()}\n"
                                    f"*{winner_msg.author.display_name}* now has **{scores[winner_msg.author]}** point(s).",
                        color=discord.Color.green(),
                    )
                )
            else:
                await self.channel.send(
                    embed=discord.Embed(
                        title="⏱️ Nobody answered in time!",
                        description=f"**Answer:** {q['a'].title()}",
                        color=discord.Color.red(),
                    )
                )

            if await self.wait_or_stop(2):
                return

        if self.is_stopped():
            return

        ranking = sorted(scores.items(), key=lambda x: -x[1])
        result = discord.Embed(title="🎓 Trivia Clash — Final Scores!", color=discord.Color.gold())
        result.add_field(
            name="Leaderboard",
            value="\n".join(f"{'🥇' if i==0 else '🥈' if i==1 else '🥉' if i==2 else '▪️'} {p.display_name}: {s} pts" for i, (p, s) in enumerate(ranking)),
        )
        if ranking:
            result.set_footer(text=f"🏆 Winner: {ranking[0][0].display_name}")
        await self.channel.send(embed=result)


# ── Would You Rather ──────────────────────────────────────────────────────────

class WouldYouRather(BaseGame):
    GAME_INFO = {
        "name": "Would You Rather",
        "description": "Vote A or B on tough dilemmas. Points for matching the majority! Who knows the group best?",
        "min_players": 2,
        "max_players": 30,
        "emoji": "🤔",
        "duration": "5–15 min",
        "category": "Competition",
    }

    async def run(self):
        questions = random.sample(WOULD_YOU_RATHER_QUESTIONS, min(8, len(WOULD_YOU_RATHER_QUESTIONS)))
        scores: Dict[discord.Member, int] = {p: 0 for p in self.players}

        intro = discord.Embed(
            title="🤔 Would You Rather — Vote!",
            description=f"**{len(questions)} dilemmas!**\n\n"
                        "Vote **A** or **B** for each question.\n"
                        "Match the majority → **+1 point**.\n"
                        "**20 seconds** per question.",
            color=discord.Color.blurple(),
        )
        await self.channel.send(embed=intro)
        if await self.wait_or_stop(5):
            return

        for q_num, (side_a, side_b) in enumerate(questions, 1):
            if self.is_stopped():
                return

            q_e = discord.Embed(
                title=f"🤔 Question {q_num} / {len(questions)}",
                description="**Would you rather…**",
                color=discord.Color.teal(),
            )
            q_e.add_field(name="🅰️ Option A", value=side_a, inline=True)
            q_e.add_field(name="🅱️ Option B", value=side_b, inline=True)

            view = self.track_view(VotingView(self.players, [f"🅰️ {side_a[:60]}", f"🅱️ {side_b[:60]}"], timeout=20.0))
            await self.channel.send(embed=q_e, view=view)
            await asyncio.wait_for(view.wait(), timeout=22.0)

            if self.is_stopped():
                return

            tally = view.tally()
            a_votes = tally.get(0, 0)
            b_votes = tally.get(1, 0)
            majority_idx = 0 if a_votes >= b_votes else 1

            for voter, choice in view.votes.items():
                if choice == majority_idx:
                    scores[voter] = scores.get(voter, 0) + 1

            majority_name = f"🅰️ {side_a}" if majority_idx == 0 else f"🅱️ {side_b}"
            result_e = discord.Embed(
                title=f"🤔 Q{q_num} Results",
                description=f"**A votes:** {a_votes} | **B votes:** {b_votes}\n"
                            f"**Majority:** {majority_name[:80]}",
                color=discord.Color.gold(),
            )
            await self.channel.send(embed=result_e)
            if await self.wait_or_stop(3):
                return

        if self.is_stopped():
            return

        ranking = sorted(scores.items(), key=lambda x: -x[1])
        final = discord.Embed(title="🤔 Would You Rather — Final Scores!", color=discord.Color.gold())
        final.add_field(
            name="Leaderboard",
            value="\n".join(f"{'🥇' if i==0 else '▪️'} {p.display_name}: {s} pts" for i, (p, s) in enumerate(ranking)),
        )
        await self.channel.send(embed=final)


# ── Price Is Right ─────────────────────────────────────────────────────────────

class PriceIsRight(BaseGame):
    GAME_INFO = {
        "name": "Price Is Right",
        "description": "Guess the price of items without going over! Closest guess without exceeding the real price wins each round.",
        "min_players": 2,
        "max_players": 20,
        "emoji": "💰",
        "duration": "10–20 min",
        "category": "Competition",
    }

    async def run(self):
        items = random.sample(PRICE_IS_RIGHT_ITEMS, min(5, len(PRICE_IS_RIGHT_ITEMS)))
        scores: Dict[discord.Member, int] = {p: 0 for p in self.players}

        intro = discord.Embed(
            title="💰 Price Is Right — Come On Down!",
            description=f"**{len(items)} items** up for guessing!\n\n"
                        "For each item, submit your best price guess.\n"
                        "**Closest without going over** wins the round! (+2 pts)\n"
                        "If everyone goes over, closest overall wins (+1 pt).",
            color=discord.Color.gold(),
        )
        await self.channel.send(embed=intro)
        if await self.wait_or_stop(5):
            return

        for item_num, item in enumerate(items, 1):
            if self.is_stopped():
                return

            guesses: Dict = {}
            item_e = discord.Embed(
                title=f"💰 Item {item_num} / {len(items)}: {item['item']}",
                description=f"*{item['hint']}*\n\n"
                            "Type your price guess (numbers only, e.g. `19.99`) in the channel!\n**30 seconds.**",
                color=discord.Color.gold(),
            )
            await self.channel.send(embed=item_e)

            end_time = asyncio.get_event_loop().time() + 30
            while asyncio.get_event_loop().time() < end_time:
                if self.is_stopped():
                    return
                remaining = end_time - asyncio.get_event_loop().time()
                msg = await self.listen_for_answer(
                    check=lambda m: (
                        m.channel == self.channel
                        and m.author in self.players
                        and m.author not in guesses
                    ),
                    timeout=min(remaining, 5.0),
                )
                if msg:
                    try:
                        val = float(msg.content.strip().replace("$", "").replace(",", ""))
                        guesses[msg.author] = val
                    except ValueError:
                        pass
                if len(guesses) >= len(self.players):
                    break

            if not guesses:
                await self.channel.send(f"No guesses! The price was **${item['price']:,.2f}**")
                continue

            real_price = item["price"]
            valid_guesses = {p: g for p, g in guesses.items() if g <= real_price}

            if valid_guesses:
                round_winner = max(valid_guesses, key=valid_guesses.get)
                scores[round_winner] = scores.get(round_winner, 0) + 2
                winner_pts = 2
            else:
                round_winner = min(guesses, key=lambda p: abs(guesses[p] - real_price))
                scores[round_winner] = scores.get(round_winner, 0) + 1
                winner_pts = 1

            guess_lines = "\n".join(
                f"• {p.display_name}: ${g:,.2f} {'✅' if g <= real_price else '❌ (over)'}"
                for p, g in sorted(guesses.items(), key=lambda x: -x[1])
            )
            result_e = discord.Embed(
                title=f"💰 Item {item_num} Results: **${real_price:,.2f}**",
                description=f"**Winner:** {round_winner.display_name} (+{winner_pts} pts)\n\n{guess_lines}",
                color=discord.Color.green(),
            )
            await self.channel.send(embed=result_e)
            if await self.wait_or_stop(3):
                return

        if self.is_stopped():
            return

        ranking = sorted(scores.items(), key=lambda x: -x[1])
        final = discord.Embed(title="💰 Price Is Right — Final Scores!", color=discord.Color.gold())
        final.add_field(
            name="Leaderboard",
            value="\n".join(f"{'🥇' if i==0 else '▪️'} {p.display_name}: {s} pts" for i, (p, s) in enumerate(ranking)),
        )
        await self.channel.send(embed=final)


# ── Hot Seat ──────────────────────────────────────────────────────────────────

class HotSeat(BaseGame):
    GAME_INFO = {
        "name": "Hot Seat",
        "description": "One player sits in the hot seat each round. Others ask them anything. The group votes: was their answer honest or BS? Fun, revealing, and hilarious!",
        "min_players": 3,
        "max_players": 15,
        "emoji": "🔥",
        "duration": "10–30 min",
        "category": "Competition",
    }

    async def run(self):
        scores: Dict[discord.Member, int] = {p: 0 for p in self.players}

        intro = discord.Embed(
            title="🔥 Hot Seat — Who's Brave Enough?",
            description="Each player takes a turn in the **Hot Seat**!\n\n"
                        "**The Hot Seat player** must answer any question asked by the group.\n"
                        "After answering, the group votes: **Honest 🟢** or **BS 🔴**\n\n"
                        "• If majority votes BS and you were honest → you get **+2 pts** (brave!)\n"
                        "• If majority votes Honest → **+1 pt** for a convincing answer\n\n"
                        "Each player gets **3 questions** in the hot seat.",
            color=discord.Color.red(),
        )
        await self.channel.send(embed=intro)
        if await self.wait_or_stop(5):
            return

        for hot_player in self.players:
            if self.is_stopped():
                return

            questioners = [p for p in self.players if p != hot_player]

            seat_e = discord.Embed(
                title=f"🔥 {hot_player.display_name} Is In The Hot Seat!",
                description=f"**{hot_player.mention}** — get ready!\n\n"
                            f"Others: ask **3 questions** one at a time. **{hot_player.display_name}** must answer each one!",
                color=discord.Color.red(),
            )
            await self.channel.send(embed=seat_e)

            for q_num in range(1, 4):
                if self.is_stopped():
                    return

                await self.channel.send(
                    embed=discord.Embed(
                        title=f"🔥 Question {q_num}/3 for {hot_player.display_name}",
                        description="Ask your question! **30 seconds.**",
                        color=discord.Color.orange(),
                    )
                )

                q_msg = await self.listen_for_answer(
                    check=lambda m: m.channel == self.channel and m.author in questioners and len(m.content) > 3,
                    timeout=30.0,
                )
                if not q_msg:
                    await self.channel.send("No question asked — skipping.")
                    continue

                await self.channel.send(
                    embed=discord.Embed(
                        title=f"❓ Question: {q_msg.content[:200]}",
                        description=f"**{hot_player.mention}** — answer! **45 seconds.**",
                        color=discord.Color.blurple(),
                    )
                )

                ans_msg = await self.listen_for_answer(
                    check=lambda m: m.channel == self.channel and m.author == hot_player,
                    timeout=45.0,
                )
                if not ans_msg:
                    await self.channel.send(f"*(No answer from {hot_player.display_name})*")
                    continue

                # Vote
                view = self.track_view(VotingView(questioners, ["🟢 Honest", "🔴 BS / Dodged"], timeout=15.0))
                await self.channel.send(
                    embed=discord.Embed(
                        title="🗳️ Honest or BS? (15 sec)",
                        description=f"*\"{ans_msg.content[:200]}\"*",
                        color=discord.Color.purple(),
                    ),
                    view=view,
                )
                await asyncio.wait_for(view.wait(), timeout=17.0)

                if self.is_stopped():
                    return

                tally = view.tally()
                honest_votes = tally.get(0, 0)
                bs_votes = tally.get(1, 0)

                if bs_votes > honest_votes:
                    scores[hot_player] = scores.get(hot_player, 0) + 2
                    await self.channel.send(f"🔴 Majority votes BS! But {hot_player.display_name} stands firm — +2 pts!")
                else:
                    scores[hot_player] = scores.get(hot_player, 0) + 1
                    await self.channel.send(f"🟢 Majority believes them! +1 pt for {hot_player.display_name}!")

        if self.is_stopped():
            return

        ranking = sorted(scores.items(), key=lambda x: -x[1])
        final = discord.Embed(title="🔥 Hot Seat — Final Scores!", color=discord.Color.gold())
        final.add_field(
            name="Leaderboard",
            value="\n".join(f"{'🥇' if i==0 else '▪️'} {p.display_name}: {s} pts" for i, (p, s) in enumerate(ranking)),
        )
        await self.channel.send(embed=final)


# ── Gladiator Draft ────────────────────────────────────────────────────────────

class GladiatorDraft(BaseGame):
    GAME_INFO = {
        "name": "Gladiator Draft",
        "description": "Draft warriors from a pool of epic gladiators, then watch auto-simulated battles determine the champion! Stats + luck = epic fights.",
        "min_players": 2,
        "max_players": 8,
        "emoji": "⚔️",
        "duration": "10–25 min",
        "category": "Competition",
    }

    async def run(self):
        available = list(GLADIATOR_FIGHTERS)
        random.shuffle(available)
        rosters: Dict[discord.Member, List] = {p: [] for p in self.players}

        intro = discord.Embed(
            title="⚔️ Gladiator Draft — Pick Your Warriors!",
            description=f"**{len(available)} gladiators** available for {len(self.players)} commanders!\n\n"
                        "**Draft order:** each player picks one gladiator per round.\n"
                        "**3 rounds** of picking, then battles begin!",
            color=discord.Color.dark_red(),
        )
        await self.channel.send(embed=intro)
        if await self.wait_or_stop(5):
            return

        for draft_round in range(1, 4):
            order = self.players if draft_round % 2 == 1 else list(reversed(self.players))
            for player in order:
                if self.is_stopped():
                    return
                if not available:
                    break

                pool_text = "\n".join(
                    f"**{i+1}.** {f['emoji']} {f['name']} — HP:{f['hp']} ATK:{f['atk']} SPD:{f['spd']} | *{f['special']}*"
                    for i, f in enumerate(available[:10])
                )
                pick_e = discord.Embed(
                    title=f"⚔️ Round {draft_round} — {player.display_name}, Pick Your Gladiator!",
                    description=f"**Available Gladiators:**\n{pool_text}\n\nType the **number** of your pick! **20 seconds.**",
                    color=discord.Color.red(),
                )
                await self.channel.send(embed=pick_e, content=player.mention)

                msg = await self.listen_for_answer(
                    check=lambda m, p=player: (
                        m.channel == self.channel
                        and m.author == p
                        and m.content.strip().isdigit()
                        and 1 <= int(m.content.strip()) <= min(len(available), 10)
                    ),
                    timeout=20.0,
                )

                if msg:
                    idx = int(msg.content.strip()) - 1
                    pick = available.pop(idx)
                else:
                    pick = available.pop(0)
                    await self.channel.send(f"⏱️ Auto-picked for {player.display_name}: {pick['emoji']} **{pick['name']}**")

                rosters[player].append(pick)
                if msg:
                    await self.channel.send(f"⚔️ **{player.display_name}** drafted **{pick['emoji']} {pick['name']}**!")

        if self.is_stopped():
            return

        # Show rosters
        for player, roster in rosters.items():
            roster_text = "\n".join(f"• {f['emoji']} **{f['name']}** — HP:{f['hp']} ATK:{f['atk']} SPD:{f['spd']}" for f in roster)
            await self.channel.send(
                embed=discord.Embed(
                    title=f"⚔️ {player.display_name}'s Roster",
                    description=roster_text,
                    color=discord.Color.blurple(),
                )
            )

        if await self.wait_or_stop(5):
            return

        # Simulate tournament
        await self.channel.send(embed=discord.Embed(title="⚔️ BATTLES BEGIN!", color=discord.Color.red()))

        def sim_fight(f1, f2) -> Tuple[dict, str]:
            hp1, hp2 = f1["hp"], f2["hp"]
            log = [f"**{f1['emoji']} {f1['name']}** vs **{f2['emoji']} {f2['name']}**\n"]
            turn = 0
            while hp1 > 0 and hp2 > 0 and turn < 20:
                turn += 1
                dmg1 = max(1, f1["atk"] + random.randint(-5, 5))
                dmg2 = max(1, f2["atk"] + random.randint(-5, 5))
                if random.random() < 0.2:
                    log.append(f"✨ {f1['name']} uses **{f1['special']}**!")
                    dmg1 = int(dmg1 * 1.5)
                if random.random() < 0.2:
                    log.append(f"✨ {f2['name']} uses **{f2['special']}**!")
                    dmg2 = int(dmg2 * 1.5)
                hp2 -= dmg1
                hp1 -= dmg2
                if turn <= 3:
                    log.append(f"Round {turn}: {f1['name']} hits for {dmg1}, {f2['name']} hits for {dmg2}")
            winner = f1 if hp1 > hp2 else f2
            log.append(f"\n🏆 **{winner['emoji']} {winner['name']}** wins!")
            return winner, "\n".join(log)

        team_scores: Dict[discord.Member, int] = {p: 0 for p in self.players}
        players_list = list(self.players)
        for i in range(len(players_list)):
            for j in range(i + 1, len(players_list)):
                if self.is_stopped():
                    return
                p1, p2 = players_list[i], players_list[j]
                fighter1 = random.choice(rosters[p1])
                fighter2 = random.choice(rosters[p2])
                winner_fighter, battle_log = sim_fight(fighter1, fighter2)
                match_winner = p1 if winner_fighter == fighter1 else p2
                team_scores[match_winner] = team_scores.get(match_winner, 0) + 1

                battle_e = discord.Embed(
                    title=f"⚔️ {p1.display_name} vs {p2.display_name}",
                    description=battle_log[:900],
                    color=discord.Color.dark_red(),
                )
                battle_e.set_footer(text=f"Commander {match_winner.display_name} wins this match!")
                await self.channel.send(embed=battle_e)
                if await self.wait_or_stop(3):
                    return

        if self.is_stopped():
            return

        ranking = sorted(team_scores.items(), key=lambda x: -x[1])
        final = discord.Embed(title="⚔️ Gladiator Draft — Champion Crowned!", color=discord.Color.gold())
        final.add_field(
            name="Tournament Standings",
            value="\n".join(f"{'👑' if i==0 else '▪️'} {p.display_name}: {w} win(s)" for i, (p, w) in enumerate(ranking)),
        )
        await self.channel.send(embed=final)


# ── Math Duel ──────────────────────────────────────────────────────────────────

class MathDuel(BaseGame):
    GAME_INFO = {
        "name": "Math Duel",
        "description": "Speed math competition! Problems get harder each round. First to type the correct answer wins the point. Mental math or bust!",
        "min_players": 2,
        "max_players": 20,
        "emoji": "🧮",
        "duration": "5–10 min",
        "category": "Competition",
    }

    async def run(self):
        scores: Dict[discord.Member, int] = {p: 0 for p in self.players}
        rounds = 10

        intro = discord.Embed(
            title="🧮 Math Duel — Calculate or Perish!",
            description=f"**{rounds} rounds** of speed math!\n\n"
                        "Problems get harder as you go.\n"
                        "⚡ First to type the correct answer wins **1 point**.\n"
                        "**15 seconds** per problem.",
            color=discord.Color.blurple(),
        )
        await self.channel.send(embed=intro)
        if await self.wait_or_stop(5):
            return

        for round_num in range(1, rounds + 1):
            if self.is_stopped():
                return

            difficulty = 1 if round_num <= 3 else 2 if round_num <= 7 else 3
            question, answer = generate_math_question(difficulty)

            q_e = discord.Embed(
                title=f"🧮 Problem {round_num} / {rounds}",
                description=f"**{question}**\n\n⏱️ 15 seconds — type your answer!",
                color=discord.Color.blurple(),
            )
            await self.channel.send(embed=q_e)

            msg = await self.listen_for_answer(
                check=lambda m, ans=answer: (
                    m.channel == self.channel
                    and m.author in self.players
                    and m.content.strip().lower().replace(",", "").replace(" ", "") == ans.lower().replace(",", "").replace(" ", "")
                ),
                timeout=15.0,
            )

            if msg:
                scores[msg.author] = scores.get(msg.author, 0) + 1
                await self.channel.send(f"✅ **{msg.author.display_name}** got it! `{question}` = **{answer}** (+1 pt)")
            else:
                await self.channel.send(f"⏱️ Time's up! `{question}` = **{answer}**")

            if await self.wait_or_stop(1.5):
                return

        if self.is_stopped():
            return

        ranking = sorted(scores.items(), key=lambda x: -x[1])
        result = discord.Embed(title="🧮 Math Duel — Final Scores!", color=discord.Color.gold())
        result.add_field(
            name="Leaderboard",
            value="\n".join(f"{'🥇' if i==0 else '▪️'} {p.display_name}: {s} pts" for i, (p, s) in enumerate(ranking)),
        )
        await self.channel.send(embed=result)


# ── Bingo ─────────────────────────────────────────────────────────────────────

class Bingo(BaseGame):
    GAME_INFO = {
        "name": "Bingo",
        "description": "Classic B-I-N-G-O! Each player gets a unique card. Numbers are called one by one. First to complete a row, column, or diagonal wins!",
        "min_players": 2,
        "max_players": 20,
        "emoji": "🎱",
        "duration": "5–15 min",
        "category": "Competition",
    }

    async def run(self):
        cards = {p: generate_bingo_card() for p in self.players}
        called: set = set()
        all_numbers = list(range(1, 76))
        random.shuffle(all_numbers)

        intro = discord.Embed(
            title="🎱 BINGO — Cards Dealt!",
            description="Click the button below to secretly view your Bingo card!\n\n"
                        "Numbers will be called one at a time. Mark them off!\n"
                        "**Shout BINGO** in the channel when you complete a row, column, or diagonal!",
            color=discord.Color.blurple(),
        )
        await self.channel.send(embed=intro)

        # Send cards via ephemeral button
        card_embeds: Dict[discord.Member, discord.Embed] = {}
        for p, card in cards.items():
            card_display = format_bingo_card(card, called)
            e = discord.Embed(title="🎱 Your Bingo Card!", description=card_display, color=discord.Color.blurple())
            e.set_footer(text="Numbers are called in the channel — shout BINGO when you win!")
            card_embeds[p] = e

        await self.reveal_roles(
            card_embeds,
            title="🎱 Bingo Cards Assigned!",
            description="Click the button to privately view your Bingo card — only you will see it.",
            button_label="🎱 View My Card",
        )

        if await self.wait_or_stop(5):
            return

        winner = None
        for number in all_numbers:
            if self.is_stopped():
                return

            called.add(number)
            col = "BINGO"[min((number - 1) // 15, 4)]
            await self.channel.send(
                embed=discord.Embed(
                    title=f"🎱 **{col}-{number}** called!",
                    description=f"Numbers called: {len(called)} | Type **BINGO** if you have a winner!",
                    color=discord.Color.blurple(),
                )
            )

            # Wait 6 seconds for BINGO call
            bingo_msg = await self.listen_for_answer(
                check=lambda m: m.channel == self.channel and m.author in self.players
                               and "bingo" in m.content.lower(),
                timeout=6.0,
            )

            if bingo_msg:
                caller = bingo_msg.author
                card = cards[caller]
                if check_bingo(card, called):
                    winner = caller
                    await self.channel.send(
                        embed=discord.Embed(
                            title=f"🎉 BINGO! {caller.display_name} wins!",
                            description=f"**{caller.display_name}** has a valid BINGO after **{len(called)} numbers** called!\n\n"
                                        + format_bingo_card(card, called),
                            color=discord.Color.gold(),
                        )
                    )
                    break
                else:
                    await self.channel.send(f"❌ False BINGO from {caller.display_name}! Keep playing...")

        if self.is_stopped():
            return

        if not winner:
            await self.channel.send(
                embed=discord.Embed(
                    title="🎱 Bingo — All Numbers Called!",
                    description="All 75 numbers were called with no winner. Everyone gets a participation trophy! 🏅",
                    color=discord.Color.blurple(),
                )
            )


# ── Two Truths and a Lie ──────────────────────────────────────────────────────

class TwoTruthsAndALie(BaseGame):
    GAME_INFO = {
        "name": "Two Truths and a Lie",
        "description": "Each player submits 2 true statements and 1 lie. Others vote on which is the lie. Fool everyone = max points!",
        "min_players": 3,
        "max_players": 20,
        "emoji": "🤥",
        "duration": "10–20 min",
        "category": "Competition",
    }

    async def run(self):
        intro = discord.Embed(
            title="🤥 Two Truths and a Lie — Confess Your Lies!",
            description="Each player will submit **3 statements** about themselves:\n"
                        "• 2 must be **TRUE**\n"
                        "• 1 must be a **LIE**\n\n"
                        "Others vote for which one they think is the lie!\n\n"
                        "**Scoring:**\n"
                        "• +1 pt for each person you fool\n"
                        "• +1 pt for correctly guessing others' lies",
            color=discord.Color.blurple(),
        )
        await self.channel.send(embed=intro)

        # Collect all statements first
        all_submissions: Dict = {}

        for player in self.players:
            if self.is_stopped():
                return

            submissions: Dict = {}

            class StatementsModal(discord.ui.Modal, title="Two Truths and a Lie"):
                s1 = discord.ui.TextInput(label="Statement 1", placeholder="A true statement about yourself", max_length=150)
                s2 = discord.ui.TextInput(label="Statement 2", placeholder="Another true statement about yourself", max_length=150)
                s3 = discord.ui.TextInput(label="Statement 3 (THE LIE)", placeholder="Your lie", max_length=150)

                async def on_submit(self_modal, interaction: discord.Interaction):
                    submissions[player] = [self_modal.s1.value, self_modal.s2.value, self_modal.s3.value]
                    await interaction.response.send_message("✅ Submitted!", ephemeral=True)

            view = discord.ui.View(timeout=60.0)
            btn = discord.ui.Button(label=f"✍️ Submit for {player.display_name}", style=discord.ButtonStyle.primary)
            async def btn_cb(interaction: discord.Interaction, p=player):
                if interaction.user != p:
                    await interaction.response.send_message("This button is for someone else!", ephemeral=True)
                    return
                await interaction.response.send_modal(StatementsModal())
            btn.callback = btn_cb
            view.add_item(btn)
            self.track_view(view)

            await self.channel.send(
                content=player.mention,
                embed=discord.Embed(
                    title=f"🤥 {player.display_name}'s Turn to Submit",
                    description="Click below to submit your 2 truths and 1 lie! **60 seconds.**",
                    color=discord.Color.blurple(),
                ),
                view=view,
            )

            end_time = asyncio.get_event_loop().time() + 60
            while asyncio.get_event_loop().time() < end_time and player not in submissions:
                if self.is_stopped():
                    return
                await asyncio.sleep(1)

            if player in submissions:
                all_submissions[player] = submissions[player]
            else:
                # fallback
                all_submissions[player] = ["I once ate 3 pizzas in one sitting", "I have never seen snow", "I can speak 4 languages"]

        if self.is_stopped():
            return

        scores: Dict[discord.Member, int] = {p: 0 for p in self.players}

        for player in self.players:
            if self.is_stopped():
                return

            statements = all_submissions[player]
            # Shuffle so lie position is not obvious (lie is index 2 in submission)
            lie_original_idx = 2
            indexed = list(enumerate(statements))
            random.shuffle(indexed)
            shuffled_statements = [s for _, s in indexed]
            lie_new_idx = next(i for i, (orig_idx, _) in enumerate(indexed) if orig_idx == lie_original_idx)

            reveal_e = discord.Embed(
                title=f"🤥 {player.display_name}'s Statements",
                color=discord.Color.teal(),
            )
            for i, s in enumerate(shuffled_statements, 1):
                reveal_e.add_field(name=f"Statement {i}", value=s, inline=False)

            options = ["Statement 1", "Statement 2", "Statement 3"]
            guessers = [p for p in self.players if p != player]
            view = self.track_view(VotingView(guessers, options, timeout=25.0))
            await self.channel.send(
                embed=discord.Embed(
                    title=f"🗳️ Which is {player.display_name}'s LIE? (25 sec)",
                    color=discord.Color.purple(),
                ),
                view=view,
            )
            # Also show statements
            await self.channel.send(embed=reveal_e)
            await asyncio.wait_for(view.wait(), timeout=27.0)

            if self.is_stopped():
                return

            tally = view.tally()
            for voter, choice_idx in view.votes.items():
                if choice_idx == lie_new_idx:
                    scores[voter] = scores.get(voter, 0) + 1
                else:
                    scores[player] = scores.get(player, 0) + 1

            await self.channel.send(
                embed=discord.Embed(
                    title=f"🤥 The Lie Was: Statement {lie_new_idx + 1}",
                    description=f"*\"{shuffled_statements[lie_new_idx]}\"*\n\n"
                                f"The truths were:\n"
                                + "\n".join(f"• {shuffled_statements[i]}" for i in range(3) if i != lie_new_idx),
                    color=discord.Color.gold(),
                )
            )
            if await self.wait_or_stop(4):
                return

        if self.is_stopped():
            return

        ranking = sorted(scores.items(), key=lambda x: -x[1])
        final = discord.Embed(title="🤥 Two Truths and a Lie — Final Scores!", color=discord.Color.gold())
        final.add_field(
            name="Leaderboard",
            value="\n".join(f"{'🥇' if i==0 else '▪️'} {p.display_name}: {s} pts" for i, (p, s) in enumerate(ranking)),
        )
        await self.channel.send(embed=final)


# ── Gladiator Tournament ───────────────────────────────────────────────────────

class GladiatorTournament(BaseGame):
    GAME_INFO = {
        "name": "Gladiator Tournament",
        "description": "Create your own gladiator with a name and special ability! The bot narrates epic auto-battles in a tournament bracket. May the best warrior win!",
        "min_players": 2,
        "max_players": 16,
        "emoji": "🏆",
        "duration": "10–30 min",
        "category": "Competition",
    }

    BATTLE_FLAVORS = [
        "With a roar that shakes the arena, {a} charges at {b}!",
        "The crowd goes wild as {a} and {b} clash in the center!",
        "{a} ducks under {b}'s swing and counters with blinding speed!",
        "Sand flies as {a} slides under {b}'s strike!",
        "{b} stumbles, and {a} seizes the moment!",
        "Lightning fast, {a} lands three blows before {b} can react!",
        "The match turns — {b} rallies with a devastating counter!",
        "{a} activates their secret technique!",
        "The crowd is on their feet as {a} gains the upper hand!",
        "{b} fights back with everything they have — but it's not enough!",
    ]

    async def run(self):
        gladiators: Dict[discord.Member, Dict] = {}
        submissions: Dict = {}

        class GladiatorModal(discord.ui.Modal, title="Create Your Gladiator!"):
            name_field = discord.ui.TextInput(label="Gladiator Name", placeholder="The Destroyer of Worlds", max_length=50)
            ability = discord.ui.TextInput(label="Special Ability", placeholder="Can summon lightning from thin air", max_length=100)

            async def on_submit(self_modal, interaction: discord.Interaction):
                submissions[interaction.user] = {
                    "display_name": self_modal.name_field.value,
                    "ability": self_modal.ability.value,
                    "hp": random.randint(80, 130),
                    "atk": random.randint(15, 25),
                    "owner": interaction.user,
                }
                await interaction.response.send_message(
                    f"✅ **{self_modal.name_field.value}** has entered the arena!", ephemeral=True
                )
                if len(submissions) >= len(self.players):
                    view.stop()

        view = discord.ui.View(timeout=90.0)
        btn = discord.ui.Button(label="⚔️ Create My Gladiator", style=discord.ButtonStyle.red)
        async def btn_cb(interaction: discord.Interaction):
            if interaction.user not in self.players:
                await interaction.response.send_message("You're not in this game!", ephemeral=True)
                return
            if interaction.user in submissions:
                await interaction.response.send_message("You already created your gladiator!", ephemeral=True)
                return
            await interaction.response.send_modal(GladiatorModal())
        btn.callback = btn_cb
        view.add_item(btn)
        self.track_view(view)

        intro = discord.Embed(
            title="🏆 Gladiator Tournament — Forge Your Champion!",
            description="Create your **custom gladiator** with a name and special ability!\n\n"
                        "Click below to enter your warrior into the tournament. **90 seconds.**",
            color=discord.Color.dark_red(),
        )
        await self.channel.send(embed=intro, view=view)
        await asyncio.wait_for(view.wait(), timeout=92.0)

        if self.is_stopped():
            return

        # Anyone who didn't submit gets a random gladiator
        for p in self.players:
            if p not in submissions:
                fighter = random.choice(GLADIATOR_FIGHTERS)
                submissions[p] = {
                    "display_name": fighter["name"],
                    "ability": fighter["special"],
                    "hp": fighter["hp"],
                    "atk": fighter["atk"],
                    "owner": p,
                }

        fighters = list(submissions.values())
        random.shuffle(fighters)

        # Show entrants
        entrants_e = discord.Embed(title="🏆 The Entrants!", color=discord.Color.gold())
        for f in fighters:
            entrants_e.add_field(
                name=f"⚔️ {f['display_name']} ({f['owner'].display_name})",
                value=f"*Special: {f['ability']}*",
                inline=False,
            )
        await self.channel.send(embed=entrants_e)
        if await self.wait_or_stop(5):
            return

        # Run tournament bracket
        bracket = list(fighters)
        round_num = 1
        while len(bracket) > 1:
            if self.is_stopped():
                return

            await self.channel.send(
                embed=discord.Embed(
                    title=f"🏆 Tournament Round {round_num}!",
                    description=f"**{len(bracket)} gladiators** remain!",
                    color=discord.Color.red(),
                )
            )

            next_round = []
            pairs = list(zip(bracket[::2], bracket[1::2]))
            if len(bracket) % 2:
                bye_fighter = bracket[-1]
                next_round.append(bye_fighter)
                await self.channel.send(f"🎖️ **{bye_fighter['display_name']}** gets a bye this round!")

            for f1, f2 in pairs:
                if self.is_stopped():
                    return

                # Simulate battle
                hp1, hp2 = f1["hp"], f2["hp"]
                battle_lines = [f"**{f1['display_name']}** vs **{f2['display_name']}**\n"]
                for _ in range(random.randint(4, 7)):
                    flavor = random.choice(self.BATTLE_FLAVORS)
                    battle_lines.append(flavor.format(a=f1["display_name"], b=f2["display_name"]))
                    dmg1 = max(1, f1["atk"] + random.randint(-3, 8))
                    dmg2 = max(1, f2["atk"] + random.randint(-3, 8))
                    # Special ability chance
                    if random.random() < 0.3:
                        battle_lines.append(f"✨ *{f1['display_name']}* uses: _{f1['ability']}_!")
                        dmg1 = int(dmg1 * 1.4)
                    hp2 -= dmg1
                    hp1 -= dmg2
                    if hp1 <= 0 or hp2 <= 0:
                        break

                winner_fighter = f1 if hp1 > hp2 else f2
                loser_fighter = f2 if winner_fighter == f1 else f1
                battle_lines.append(f"\n💀 **{loser_fighter['display_name']}** falls!")
                battle_lines.append(f"🏆 **{winner_fighter['display_name']}** advances!")

                battle_e = discord.Embed(
                    title=f"⚔️ {f1['display_name']} ({f1['owner'].display_name}) vs {f2['display_name']} ({f2['owner'].display_name})",
                    description="\n".join(battle_lines[:20]),
                    color=discord.Color.dark_red(),
                )
                await self.channel.send(embed=battle_e)
                next_round.append(winner_fighter)
                if await self.wait_or_stop(3):
                    return

            bracket = next_round
            round_num += 1

        if self.is_stopped():
            return

        if bracket:
            champion = bracket[0]
            final_e = discord.Embed(
                title=f"🏆 CHAMPION: {champion['display_name']}!",
                description=f"Owned by **{champion['owner'].display_name}**\n\n"
                            f"*Special Ability: {champion['ability']}*\n\n"
                            "The crowd erupts! The arena shakes! A new legend is born!",
                color=discord.Color.gold(),
            )
            await self.channel.send(embed=final_e)
