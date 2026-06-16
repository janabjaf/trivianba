import asyncio
import random
import discord
from typing import Dict, List, Optional, Set
from ..game_base import BaseGame, VotingView
from ..game_data import (
    WORD_BOMB_COMBOS, ALPHABET_CHAIN_CATEGORIES, HANGMAN_STAGES, HANGMAN_WORDS,
    ESCAPE_ROOM_PUZZLES, WAVELENGTH_SPECTRUMS, CODENAMES_WORDS,
)


# ── Taboo data ─────────────────────────────────────────────────────────────────
TABOO_CARDS = [
    {"word": "OCEAN", "forbidden": ["water", "sea", "waves", "fish", "blue"]},
    {"word": "CHRISTMAS", "forbidden": ["holiday", "santa", "gifts", "tree", "december"]},
    {"word": "BASKETBALL", "forbidden": ["ball", "hoop", "NBA", "sport", "dunk"]},
    {"word": "AIRPLANE", "forbidden": ["fly", "wings", "plane", "airport", "sky"]},
    {"word": "LIBRARY", "forbidden": ["books", "read", "quiet", "shelves", "borrow"]},
    {"word": "PIZZA", "forbidden": ["cheese", "Italy", "tomato", "slice", "crust"]},
    {"word": "DOCTOR", "forbidden": ["hospital", "medicine", "sick", "health", "nurse"]},
    {"word": "GUITAR", "forbidden": ["music", "strings", "rock", "instrument", "band"]},
    {"word": "VOLCANO", "forbidden": ["lava", "erupt", "fire", "mountain", "magma"]},
    {"word": "RAINBOW", "forbidden": ["colors", "rain", "sky", "spectrum", "arc"]},
    {"word": "TELESCOPE", "forbidden": ["stars", "space", "lens", "view", "astronomy"]},
    {"word": "SUBMARINE", "forbidden": ["underwater", "ocean", "navy", "dive", "torpedo"]},
    {"word": "CHOCOLATE", "forbidden": ["sweet", "candy", "cocoa", "brown", "dessert"]},
    {"word": "DETECTIVE", "forbidden": ["solve", "crime", "mystery", "clue", "police"]},
    {"word": "ELEPHANT", "forbidden": ["trunk", "big", "grey", "Africa", "animal"]},
    {"word": "CASTLE", "forbidden": ["king", "fortress", "medieval", "moat", "knight"]},
    {"word": "HURRICANE", "forbidden": ["storm", "wind", "rain", "weather", "tropical"]},
    {"word": "COMPASS", "forbidden": ["north", "direction", "navigate", "magnetic", "map"]},
    {"word": "ARCHITECT", "forbidden": ["build", "design", "house", "structure", "blueprint"]},
    {"word": "MARATHON", "forbidden": ["run", "race", "26", "miles", "endurance"]},
]


# ── Word Bomb ─────────────────────────────────────────────────────────────────

class WordBomb(BaseGame):
    GAME_INFO = {
        "name": "Word Bomb",
        "description": "A letter combo is revealed. Type a word containing it before time runs out! Fail or repeat a word = eliminated. Last player standing wins!",
        "min_players": 2,
        "max_players": 20,
        "emoji": "💣",
        "duration": "5–15 min",
        "category": "Word & Puzzle",
    }

    async def run(self):
        alive = list(self.players)
        used_words: Set[str] = set()

        intro = discord.Embed(
            title="💣 Word Bomb — Ready?",
            description="A letter combination will appear. Type a word that **contains those letters** in the channel!\n\n"
                        "⚠️ **Rules:**\n"
                        "• You have **12 seconds** to respond\n"
                        "• Words must contain the combo somewhere inside them\n"
                        "• No repeating words!\n"
                        "• Fail to respond in time = eliminated\n\n"
                        "💡 Example: Combo `ST` → acceptable: *fast*, *stone*, *mast*",
            color=discord.Color.red(),
        )
        await self.channel.send(embed=intro)
        if await self.wait_or_stop(5):
            return

        round_num = 0
        while len(alive) > 1:
            if self.is_stopped():
                return

            round_num += 1
            current_player = alive[(round_num - 1) % len(alive)]
            combo = random.choice(WORD_BOMB_COMBOS)

            bomb_e = discord.Embed(
                title=f"💣 `{combo}` — {current_player.display_name}!",
                description=f"**{current_player.mention}** — type a word containing **`{combo}`**!\n⏱️ **12 seconds!**",
                color=discord.Color.orange(),
            )
            await self.channel.send(embed=bomb_e)

            msg = await self.listen_for_answer(
                check=lambda m, p=current_player, c=combo: (
                    m.channel == self.channel
                    and m.author == p
                    and c.lower() in m.content.lower()
                    and m.content.lower().strip() not in used_words
                    and m.content.strip().isalpha()
                    and len(m.content.strip()) > 1
                ),
                timeout=12.0,
            )

            if msg:
                word = msg.content.strip().lower()
                used_words.add(word)
                await self.channel.send(f"✅ **{word}** accepted!")
            else:
                alive.remove(current_player)
                await self.channel.send(
                    embed=discord.Embed(
                        title="💥 BOOM!",
                        description=f"**{current_player.display_name}** didn't answer in time and is **eliminated**!\n"
                                    f"Remaining: {len(alive)} players",
                        color=discord.Color.red(),
                    )
                )

            if len(alive) <= 1:
                break

            if await self.wait_or_stop(1.5):
                return

        if self.is_stopped():
            return

        winner = alive[0] if alive else None
        result = discord.Embed(title="💣 Word Bomb — Winner!", color=discord.Color.gold())
        result.add_field(
            name="🏆 Last Standing",
            value=f"**{winner.display_name}** defuses the final bomb!" if winner else "No winner",
        )
        result.add_field(name="Words Used This Game", value=str(len(used_words)))
        await self.channel.send(embed=result)


# ── Alphabet Chain ─────────────────────────────────────────────────────────────

class AlphabetChain(BaseGame):
    GAME_INFO = {
        "name": "Alphabet Chain",
        "description": "A category is given. Players take turns naming something in that category in alphabetical order. Fail to answer in time or break the chain = out!",
        "min_players": 2,
        "max_players": 20,
        "emoji": "🔤",
        "duration": "5–15 min",
        "category": "Word & Puzzle",
    }

    async def run(self):
        category = random.choice(ALPHABET_CHAIN_CATEGORIES)
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        alive = list(self.players)
        letter_idx = 0

        intro = discord.Embed(
            title="🔤 Alphabet Chain — Let's Go!",
            description=f"**Category:** {category.upper()}\n\n"
                        "Players take turns naming something in this category in **alphabetical order**.\n"
                        "**15 seconds per turn.** Fail to answer or break the alphabet = eliminated!\n\n"
                        f"Starting with **A**!",
            color=discord.Color.blurple(),
        )
        await self.channel.send(embed=intro)
        if await self.wait_or_stop(5):
            return

        used: Set[str] = set()
        turn_idx = 0

        while len(alive) > 1 and letter_idx < len(alphabet):
            if self.is_stopped():
                return

            current = alive[turn_idx % len(alive)]
            letter = alphabet[letter_idx]

            turn_e = discord.Embed(
                title=f"🔤 Letter **{letter}** — {current.display_name}",
                description=f"**Category:** {category}\n"
                            f"**{current.mention}** — name something in **{category}** starting with **{letter}**! **15 seconds.**",
                color=discord.Color.teal(),
            )
            await self.channel.send(embed=turn_e)

            msg = await self.listen_for_answer(
                check=lambda m, p=current, l=letter: (
                    m.channel == self.channel
                    and m.author == p
                    and m.content.strip().upper().startswith(l)
                    and m.content.strip().lower() not in used
                ),
                timeout=15.0,
            )

            if msg:
                word = msg.content.strip()
                used.add(word.lower())
                await self.channel.send(f"✅ **{word}** ✓")
                letter_idx += 1
                turn_idx += 1
            else:
                alive.remove(current)
                await self.channel.send(
                    embed=discord.Embed(
                        title="❌ Eliminated!",
                        description=f"**{current.display_name}** couldn't name a **{category}** starting with **{letter}**!\n"
                                    f"Remaining: {len(alive)} players",
                        color=discord.Color.red(),
                    )
                )
                if current in alive:
                    turn_idx += 1

            if await self.wait_or_stop(1):
                return

        if self.is_stopped():
            return

        winner = alive[0] if len(alive) == 1 else None
        result = discord.Embed(title="🔤 Alphabet Chain — Game Over!", color=discord.Color.gold())
        if winner:
            result.add_field(name="🏆 Winner!", value=f"**{winner.display_name}** — Alphabet Champion!")
        else:
            result.add_field(name="Survivors", value=", ".join(p.display_name for p in alive) or "Nobody")
        result.add_field(name="Letters Completed", value=f"{letter_idx} / 26")
        await self.channel.send(embed=result)


# ── Group Hangman ──────────────────────────────────────────────────────────────

class GroupHangman(BaseGame):
    GAME_INFO = {
        "name": "Hangman",
        "description": "Classic hangman! One player thinks of a word, others guess letters together. Save the stick figure before it's too late!",
        "min_players": 2,
        "max_players": 20,
        "emoji": "🎯",
        "duration": "5–10 min",
        "category": "Word & Puzzle",
    }

    async def run(self):
        # Word chooser picks from known list (or they can type a word)
        word_chooser = random.choice(self.players)
        guessers = [p for p in self.players if p != word_chooser]

        raw = await self.request_secret_input(
            target=word_chooser,
            prompt=(
                f"**{word_chooser.mention}** — click the button below to privately set the Hangman word!\n"
                "Type any word (letters only), or type `random` for a surprise. **35 seconds.**"
            ),
            modal_title="Set the Hangman Word",
            field_label="Your secret word (or type 'random')",
            placeholder="e.g. elephant  — or type: random",
            button_label="🎯 Set My Word",
            timeout=35.0,
        )

        if raw and raw.strip().lower() != "random":
            cleaned = "".join(c for c in raw.strip().upper() if c.isalpha())
            secret_word = cleaned if cleaned else random.choice(HANGMAN_WORDS).upper()
        else:
            secret_word = random.choice(HANGMAN_WORDS).upper()

        guessed_letters: Set[str] = set()
        wrong_letters: Set[str] = set()
        max_wrong = len(HANGMAN_STAGES) - 1

        def display_word():
            return " ".join(c if c in guessed_letters else "\_" for c in secret_word)

        def is_won():
            return all(c in guessed_letters for c in secret_word)

        game_msg = None
        while len(wrong_letters) < max_wrong and not is_won():
            if self.is_stopped():
                return

            stage_idx = len(wrong_letters)
            embed = discord.Embed(
                title="🎯 Hangman",
                color=discord.Color.blurple(),
            )
            embed.add_field(name="", value=HANGMAN_STAGES[stage_idx], inline=False)
            embed.add_field(name="Word", value=f"`{display_word()}`", inline=False)
            embed.add_field(name="Wrong Letters", value=" ".join(sorted(wrong_letters)) or "*none yet*", inline=True)
            embed.add_field(name="Correct Letters", value=" ".join(sorted(guessed_letters)) or "*none yet*", inline=True)
            embed.add_field(name=f"Lives Left", value=f"{'❤️' * (max_wrong - len(wrong_letters))}{'🖤' * len(wrong_letters)}", inline=False)
            embed.set_footer(text="Type a letter to guess! Any player can guess.")

            if game_msg:
                try:
                    await game_msg.edit(embed=embed)
                except Exception:
                    game_msg = await self.channel.send(embed=embed)
            else:
                game_msg = await self.channel.send(embed=embed)

            msg = await self.listen_for_answer(
                check=lambda m: (
                    m.channel == self.channel
                    and m.author in guessers
                    and len(m.content.strip()) == 1
                    and m.content.strip().isalpha()
                    and m.content.strip().upper() not in guessed_letters
                    and m.content.strip().upper() not in wrong_letters
                ),
                timeout=60.0,
            )

            if not msg:
                await self.channel.send("⏱️ No guess received — game over!")
                break

            letter = msg.content.strip().upper()
            if letter in secret_word:
                guessed_letters.add(letter)
                await self.channel.send(f"✅ **{letter}** is in the word!")
            else:
                wrong_letters.add(letter)
                await self.channel.send(f"❌ **{letter}** is not in the word!")

        if self.is_stopped():
            return

        if is_won():
            result = discord.Embed(
                title="🎯 Hangman — You Win!",
                description=f"🎉 The word was: **{secret_word}**\n\nThe stick figure lives another day!",
                color=discord.Color.green(),
            )
        else:
            result = discord.Embed(
                title="🎯 Hangman — Game Over!",
                description=f"💀 The stick figure didn't make it.\n\nThe word was: **{secret_word}**",
                color=discord.Color.red(),
            )
            result.add_field(name="", value=HANGMAN_STAGES[-1])
        await self.channel.send(embed=result)


# ── Escape Room Race ───────────────────────────────────────────────────────────

class EscapeRoomRace(BaseGame):
    GAME_INFO = {
        "name": "Escape Room",
        "description": "Race through a series of puzzles! First to type the correct answer to each puzzle earns a point. Highest score at the end escapes first!",
        "min_players": 2,
        "max_players": 30,
        "emoji": "🔐",
        "duration": "5–20 min",
        "category": "Word & Puzzle",
    }

    async def run(self):
        puzzles = random.sample(ESCAPE_ROOM_PUZZLES, min(5, len(ESCAPE_ROOM_PUZZLES)))
        scores: Dict[discord.Member, int] = {p: 0 for p in self.players}

        intro = discord.Embed(
            title="🔐 Escape Room Race — The Clock Starts Now!",
            description=f"**{len(puzzles)} puzzles** stand between you and freedom!\n\n"
                        "For each puzzle:\n"
                        "• First to type the correct answer earns **2 points**\n"
                        "• Second gets **1 point**\n"
                        "• **60 seconds** per puzzle\n\n"
                        "The clock is ticking... can you escape?",
            color=discord.Color.dark_green(),
        )
        await self.channel.send(embed=intro)
        if await self.wait_or_stop(5):
            return

        for puzzle_num, puzzle in enumerate(puzzles, 1):
            if self.is_stopped():
                return

            puzzle_e = discord.Embed(
                title=f"{puzzle['title']} ({puzzle_num}/{len(puzzles)})",
                description=f"{puzzle['description']}\n\n"
                            f"💡 **Hint:** {puzzle['hint']}\n\n"
                            "Type your answer in the channel! **60 seconds.**",
                color=discord.Color.dark_green(),
            )
            await self.channel.send(embed=puzzle_e)

            correct_answer = puzzle["answer"].lower()
            answerers = []
            end_time = asyncio.get_event_loop().time() + 60

            while asyncio.get_event_loop().time() < end_time and len(answerers) < 2:
                if self.is_stopped():
                    return
                remaining = end_time - asyncio.get_event_loop().time()
                msg = await self.listen_for_answer(
                    check=lambda m: m.channel == self.channel and m.author in self.players
                                   and m.author not in answerers
                                   and correct_answer in m.content.lower().strip(),
                    timeout=min(remaining, 5.0),
                )
                if msg:
                    answerers.append(msg.author)
                    pts = 2 if len(answerers) == 1 else 1
                    scores[msg.author] += pts
                    await self.channel.send(f"{'🥇' if len(answerers)==1 else '🥈'} **{msg.author.display_name}** got it! (+{pts} pts)")

            if not answerers:
                await self.channel.send(f"⏱️ Time's up! The answer was: **{puzzle['answer']}**")
            
            if await self.wait_or_stop(2):
                return

        if self.is_stopped():
            return

        ranking = sorted(scores.items(), key=lambda x: -x[1])
        result = discord.Embed(title="🔐 Escape Room — You're Free!", color=discord.Color.green())
        result.add_field(
            name="🏆 Final Leaderboard",
            value="\n".join(f"{'🥇' if i==0 else '🥈' if i==1 else '🥉' if i==2 else '▪️'} {p.display_name}: {s} pts" for i, (p, s) in enumerate(ranking)),
        )
        await self.channel.send(embed=result)


# ── Twenty Questions ───────────────────────────────────────────────────────────

class TwentyQuestions(BaseGame):
    GAME_INFO = {
        "name": "20 Questions",
        "description": "One player thinks of something (person, place, or thing). Others ask yes/no questions to guess it. 20 questions — can you figure it out?",
        "min_players": 2,
        "max_players": 20,
        "emoji": "❓",
        "duration": "5–15 min",
        "category": "Word & Puzzle",
    }

    async def run(self):
        thinker = random.choice(self.players)
        questioners = [p for p in self.players if p != thinker]

        raw = await self.request_secret_input(
            target=thinker,
            prompt=(
                f"**{thinker.mention}** — click the button below to privately set what you're thinking of!\n"
                "Think of a **person, place, or thing**. Others will ask yes/no questions to guess it. **35 seconds.**"
            ),
            modal_title="What Are You Thinking Of?",
            field_label="Person, place, or thing",
            placeholder="e.g. Mount Everest, Albert Einstein, Pizza…",
            button_label="❓ Set My Secret",
            timeout=35.0,
        )

        secret = raw if raw else random.choice(["Mount Everest", "Albert Einstein", "The Eiffel Tower", "Pizza", "The Moon"])

        game_e = discord.Embed(
            title=f"❓ 20 Questions — {thinker.display_name} is thinking of something…",
            description=f"Category hint: It is a **{'person' if random.random() > 0.7 else 'place or thing'}**.\n\n"
                        f"Ask **yes/no questions** in the channel!\n"
                        f"**{thinker.display_name}** replies `yes` or `no`.\n"
                        "Guess by saying exactly what it is!\n\n"
                        "20 questions total.",
            color=discord.Color.teal(),
        )
        await self.channel.send(embed=game_e)
        if await self.wait_or_stop(3):
            return

        questions_asked = 0
        guessed = False

        while questions_asked < 20 and not guessed:
            if self.is_stopped():
                return

            status_e = discord.Embed(
                title=f"❓ Question {questions_asked + 1} / 20",
                description=f"Ask your question! **{thinker.mention}** will answer yes or no. **30 seconds.**",
                color=discord.Color.teal(),
            )
            await self.channel.send(embed=status_e)

            q_msg = await self.listen_for_answer(
                check=lambda m: m.channel == self.channel and m.author in questioners and len(m.content) > 2,
                timeout=30.0,
            )

            if not q_msg:
                await self.channel.send("⏱️ No question asked — skipping.")
                questions_asked += 1
                continue

            questions_asked += 1
            q_text = q_msg.content

            # Check if it's a guess
            is_guess = (
                secret.lower() in q_text.lower()
                or any(word in secret.lower() for word in q_text.lower().split() if len(word) > 3)
            )

            if is_guess:
                await self.channel.send(
                    embed=discord.Embed(
                        title=f"🎉 Correct! {q_msg.author.display_name} guessed it!",
                        description=f"The answer was: **{secret}**\nGuessed in **{questions_asked}** questions!",
                        color=discord.Color.green(),
                    )
                )
                guessed = True
            else:
                # Thinker answers
                await self.channel.send(
                    embed=discord.Embed(
                        title=f"❓ {thinker.display_name} — Answer the question!",
                        description=f"*\"{q_text}\"*\n\nType **yes**, **no**, or **sometimes**. **15 seconds.**",
                        color=discord.Color.orange(),
                    ),
                    content=thinker.mention,
                )
                ans = await self.listen_for_answer(
                    check=lambda m: m.channel == self.channel and m.author == thinker and len(m.content) < 20,
                    timeout=15.0,
                )
                if not ans:
                    await self.channel.send("*(No answer — moving on)*")

        if self.is_stopped():
            return

        if not guessed:
            await self.channel.send(
                embed=discord.Embed(
                    title="❓ 20 Questions — Nobody Guessed!",
                    description=f"**{thinker.display_name}** stumped everyone!\n\nThe answer was: **{secret}**",
                    color=discord.Color.red(),
                )
            )


# ── Wavelength ─────────────────────────────────────────────────────────────────

class Wavelength(BaseGame):
    GAME_INFO = {
        "name": "Wavelength",
        "description": "A spectrum is shown (e.g. Cold ↔ Hot). One player gives a one-word clue. Team guesses where on the 1-10 scale the clue lands. Score based on accuracy!",
        "min_players": 2,
        "max_players": 20,
        "emoji": "〰️",
        "duration": "10–20 min",
        "category": "Word & Puzzle",
    }

    async def run(self):
        scores: Dict[discord.Member, int] = {p: 0 for p in self.players}
        rounds = min(len(self.players), 5)

        intro = discord.Embed(
            title="〰️ Wavelength — Tune Your Mind!",
            description="Each round, a spectrum is shown (e.g. **Cold ↔️ Hot**).\n\n"
                        "The clue-giver secretly picks a position **(1–10)** on the spectrum.\n"
                        "They give one-word clue that represents that position.\n"
                        "Everyone else guesses the number. Closest = most points!\n\n"
                        f"**{rounds} rounds.**",
            color=discord.Color.blurple(),
        )
        await self.channel.send(embed=intro)
        if await self.wait_or_stop(5):
            return

        used_spectrums = []
        for round_num in range(1, rounds + 1):
            if self.is_stopped():
                return

            clue_giver = self.players[(round_num - 1) % len(self.players)]
            guessers = [p for p in self.players if p != clue_giver]

            available = [s for s in WAVELENGTH_SPECTRUMS if s not in used_spectrums]
            if not available:
                available = WAVELENGTH_SPECTRUMS
            spectrum = random.choice(available)
            used_spectrums.append(spectrum)
            left, right = spectrum

            target = random.randint(1, 10)
            pos_embed = discord.Embed(
                title="〰️ Your Secret Position",
                description=f"**Spectrum:** {left} ↔️ {right}\n\n"
                            f"**Your position:** {target} / 10\n"
                            f"*(1 = fully {left}, 10 = fully {right})*\n\n"
                            "Give a one-word clue in the channel that best represents this position!",
                color=discord.Color.teal(),
            )
            await self.reveal_roles(
                {clue_giver: pos_embed},
                title="〰️ Wavelength — Your Secret Position",
                description=f"**{clue_giver.mention}** — click to privately see your target position on the spectrum!",
                button_label="〰️ View My Position",
            )

            round_e = discord.Embed(
                title=f"〰️ Round {round_num} — {clue_giver.display_name} is the Clue-Giver",
                description=f"**Spectrum:** `{left}` ↔️ `{right}`\n\n"
                            f"**{clue_giver.mention}** — give your one-word clue in the channel! **30 seconds.**",
                color=discord.Color.blurple(),
            )
            await self.channel.send(embed=round_e)

            clue_msg = await self.listen_for_answer(
                check=lambda m, p=clue_giver: m.channel == self.channel and m.author == p and len(m.content.split()) <= 2,
                timeout=30.0,
            )
            clue = clue_msg.content.strip() if clue_msg else "(no clue)"

            if self.is_stopped():
                return

            guess_e = discord.Embed(
                title=f"〰️ Clue: **{clue}**",
                description=f"**Spectrum:** `{left} (1)` ↔️ `{right} (10)`\n\n"
                            "Type a number **1–10** in the channel! **20 seconds.**\n"
                            "Closest to the target earns the most points!",
                color=discord.Color.teal(),
            )
            await self.channel.send(embed=guess_e)

            guesses: Dict[discord.Member, int] = {}
            end_time = asyncio.get_event_loop().time() + 20

            while asyncio.get_event_loop().time() < end_time:
                if self.is_stopped():
                    return
                remaining = end_time - asyncio.get_event_loop().time()
                msg = await self.listen_for_answer(
                    check=lambda m: (
                        m.channel == self.channel
                        and m.author in guessers
                        and m.author not in guesses
                        and m.content.strip().isdigit()
                        and 1 <= int(m.content.strip()) <= 10
                    ),
                    timeout=min(remaining, 5.0),
                )
                if msg:
                    guesses[msg.author] = int(msg.content.strip())
                if len(guesses) >= len(guessers):
                    break

            if self.is_stopped():
                return

            result_lines = [f"🎯 Target was: **{target}** on `{left} ↔️ {right}`\n"]
            for p, g in guesses.items():
                diff = abs(g - target)
                pts = max(0, 5 - diff)
                scores[p] += pts
                result_lines.append(f"• {p.display_name} guessed **{g}** — diff: {diff} → +{pts} pts")

            result = discord.Embed(
                title=f"〰️ Round {round_num} Results",
                description="\n".join(result_lines),
                color=discord.Color.gold(),
            )
            await self.channel.send(embed=result)
            if await self.wait_or_stop(3):
                return

        if self.is_stopped():
            return

        ranking = sorted(scores.items(), key=lambda x: -x[1])
        final = discord.Embed(title="〰️ Wavelength — Final Scores!", color=discord.Color.gold())
        final.add_field(
            name="Leaderboard",
            value="\n".join(f"{'🥇' if i==0 else '▪️'} {p.display_name}: {s} pts" for i, (p, s) in enumerate(ranking)),
        )
        await self.channel.send(embed=final)


# ── Taboo ─────────────────────────────────────────────────────────────────────

class Taboo(BaseGame):
    GAME_INFO = {
        "name": "Taboo",
        "description": "Describe a word to your team WITHOUT using the 5 forbidden words! Each successful guess = 1 point. 60 seconds per turn.",
        "min_players": 4,
        "max_players": 20,
        "emoji": "🚫",
        "duration": "10–25 min",
        "category": "Word & Puzzle",
    }

    async def run(self):
        scores: Dict[discord.Member, int] = {p: 0 for p in self.players}
        cards = random.sample(TABOO_CARDS, min(len(self.players), len(TABOO_CARDS)))

        intro = discord.Embed(
            title="🚫 Taboo — Say Anything… Except That!",
            description="Each round, one player describes a secret word to the group.\n"
                        "**5 forbidden words** that can't be used!\n"
                        "Team guesses the word in **60 seconds**.\n\n"
                        "Each correct guess = **+1 point** for the describer.",
            color=discord.Color.red(),
        )
        await self.channel.send(embed=intro)
        if await self.wait_or_stop(5):
            return

        for i, player in enumerate(self.players):
            if self.is_stopped():
                return
            if i >= len(cards):
                break

            card = cards[i]
            word = card["word"]
            forbidden = card["forbidden"]

            card_embed = discord.Embed(title="🚫 Your Taboo Card!", color=discord.Color.red())
            card_embed.add_field(name="Word to Describe", value=f"**{word}**", inline=False)
            card_embed.add_field(name="🚫 FORBIDDEN Words", value=", ".join(f"~~{w}~~" for w in forbidden), inline=False)
            card_embed.set_footer(text="Describe it without using these words! You have 60 seconds in the channel.")
            await self.reveal_roles(
                {player: card_embed},
                title=f"🚫 {player.display_name}'s Secret Card",
                description=f"**{player.mention}** — click to privately view your Taboo card before describing!",
                button_label="🚫 View My Card",
            )

            round_e = discord.Embed(
                title=f"🚫 Taboo — {player.display_name}'s Turn!",
                description=f"**{player.mention}** is describing!\n\n"
                            f"🚫 Forbidden words: `{', '.join(forbidden)}`\n\n"
                            "**Team:** type your guesses! **60 seconds.**",
                color=discord.Color.orange(),
            )
            await self.channel.send(embed=round_e)

            guessed = False
            end_time = asyncio.get_event_loop().time() + 60

            while asyncio.get_event_loop().time() < end_time and not guessed:
                if self.is_stopped():
                    return
                remaining = end_time - asyncio.get_event_loop().time()
                msg = await self.listen_for_answer(
                    check=lambda m: m.channel == self.channel and m.author != player and m.author in self.players,
                    timeout=min(remaining, 5.0),
                )
                if msg:
                    if word.lower() in msg.content.lower():
                        guessed = True
                        scores[player] += 1
                        await self.channel.send(f"✅ **{msg.author.display_name}** got it! The word was **{word}**! +1 for {player.display_name}!")
                    # Check if forbidden word used
                    content_lower = msg.content.lower()
                    if msg.author == player:
                        for fw in forbidden:
                            if fw.lower() in content_lower:
                                await self.channel.send(f"🚨 **{player.display_name}** said a forbidden word: **{fw}**! -1 point!")
                                scores[player] = max(0, scores[player] - 1)
                                break

            if not guessed:
                await self.channel.send(f"⏱️ Time's up! The word was **{word}**.")

            if await self.wait_or_stop(2):
                return

        if self.is_stopped():
            return

        ranking = sorted(scores.items(), key=lambda x: -x[1])
        result = discord.Embed(title="🚫 Taboo — Final Scores!", color=discord.Color.gold())
        result.add_field(
            name="Leaderboard",
            value="\n".join(f"{'🥇' if i==0 else '▪️'} {p.display_name}: {s} pts" for i, (p, s) in enumerate(ranking)),
        )
        await self.channel.send(embed=result)


# ── Codenames ──────────────────────────────────────────────────────────────────

class Codenames(BaseGame):
    GAME_INFO = {
        "name": "Codenames",
        "description": "Two teams compete! Spymasters give one-word clues + a number. Teams guess their colored words. Hit the assassin word = instant loss!",
        "min_players": 4,
        "max_players": 20,
        "emoji": "🔑",
        "duration": "10–25 min",
        "category": "Word & Puzzle",
    }

    async def run(self):
        n = len(self.players)
        mid = n // 2
        random.shuffle(self.players)
        team_a = self.players[:mid]
        team_b = self.players[mid:]

        # Pick 25 words
        words = random.sample(CODENAMES_WORDS, 25)
        # Assign colors
        a_count, b_count = 9, 8
        assassin_count = 1
        bystander_count = 25 - a_count - b_count - assassin_count

        word_colors = (
            ["A"] * a_count
            + ["B"] * b_count
            + ["X"] * assassin_count
            + ["N"] * bystander_count
        )
        random.shuffle(word_colors)
        word_map = {words[i]: word_colors[i] for i in range(25)}

        # Pick spymasters
        spymaster_a = random.choice(team_a)
        spymaster_b = random.choice(team_b)
        ops_a = [p for p in team_a if p != spymaster_a]
        ops_b = [p for p in team_b if p != spymaster_b]

        # Send key to spymasters via ephemeral button
        def make_key_text():
            lines = []
            for i, w in enumerate(words):
                color = word_map[w]
                symbol = "🔵" if color == "A" else "🔴" if color == "B" else "💀" if color == "X" else "⬜"
                lines.append(f"{symbol} {w}")
            return "\n".join(lines)

        key_text = make_key_text()
        key_embeds: Dict[discord.Member, discord.Embed] = {}
        for sm in [spymaster_a, spymaster_b]:
            sm_color = "🔵 BLUE (A)" if sm == spymaster_a else "🔴 RED (B)"
            e = discord.Embed(title="🔑 Codenames — Spymaster Key", color=discord.Color.gold())
            e.description = f"You are the **{sm_color} Spymaster**!\n\n```\n{key_text}\n```\n\nGive clues as: `ClueWord 3` in the channel."
            key_embeds[sm] = e

        await self.reveal_roles(
            key_embeds,
            title="🔑 Codenames — Spymaster Keys Ready!",
            description="Spymasters: click the button to secretly view your color key — **only you** will see it.",
            button_label="🔑 View My Spymaster Key",
        )

        def make_board_display(revealed: set):
            lines = []
            for i in range(5):
                row = []
                for j in range(5):
                    idx = i * 5 + j
                    w = words[idx]
                    if w in revealed:
                        color = word_map[w]
                        sym = "🔵" if color == "A" else "🔴" if color == "B" else "💀" if color == "X" else "⬜"
                        row.append(f"{sym}{w[:6]}")
                    else:
                        row.append(f"❓{w[:6]}")
                lines.append(" | ".join(row))
            return "\n".join(lines)

        a_remaining = [w for w, c in word_map.items() if c == "A"]
        b_remaining = [w for w, c in word_map.items() if c == "B"]
        revealed: Set[str] = set()

        intro = discord.Embed(
            title="🔑 Codenames — Game Start!",
            description=f"🔵 **Team A:** {', '.join(p.display_name for p in team_a)}\n"
                        f"🔴 **Team B:** {', '.join(p.display_name for p in team_b)}\n\n"
                        f"🔵 Spymaster A: {spymaster_a.display_name}\n"
                        f"🔴 Spymaster B: {spymaster_b.display_name}\n\n"
                        f"🔵 Blue needs **{a_count}** words | 🔴 Red needs **{b_count}** words | 💀 Avoid the **assassin**!\n\n"
                        "Spymasters: click the button above to secretly view your color key!",
            color=discord.Color.blurple(),
        )
        await self.channel.send(embed=intro)
        if await self.wait_or_stop(5):
            return

        current_team = "A"
        winner = None

        for _ in range(20):
            if self.is_stopped():
                return
            if not a_remaining or not b_remaining:
                winner = "A" if not a_remaining else "B"
                break

            sm = spymaster_a if current_team == "A" else spymaster_b
            ops = ops_a if current_team == "A" else ops_b
            team_name = "🔵 Blue" if current_team == "A" else "🔴 Red"
            remaining = a_remaining if current_team == "A" else b_remaining

            board_text = make_board_display(revealed)
            board_e = discord.Embed(
                title=f"🔑 Codenames Board — {team_name}'s Turn",
                description=f"```\n{board_text}\n```\n"
                            f"**{team_name} Spymaster ({sm.display_name})** — give your clue!\n"
                            "Format: `Word Number` (e.g. `OCEAN 3`). **30 seconds.**",
                color=discord.Color.blue() if current_team == "A" else discord.Color.red(),
            )
            board_e.add_field(name="🔵 Remaining", value=str(len(a_remaining)), inline=True)
            board_e.add_field(name="🔴 Remaining", value=str(len(b_remaining)), inline=True)
            await self.channel.send(embed=board_e, content=sm.mention)

            clue_msg = await self.listen_for_answer(
                check=lambda m, p=sm: m.channel == self.channel and m.author == p,
                timeout=30.0,
            )

            if not clue_msg:
                await self.channel.send(f"⏱️ No clue from {sm.display_name}. Skipping.")
                current_team = "B" if current_team == "A" else "A"
                continue

            clue_parts = clue_msg.content.strip().split()
            try:
                clue_num = int(clue_parts[-1])
                clue_word = " ".join(clue_parts[:-1])
            except (ValueError, IndexError):
                clue_word = clue_msg.content.strip()
                clue_num = 1

            await self.channel.send(
                embed=discord.Embed(
                    title=f"🔑 Clue: **{clue_word}** ({clue_num})",
                    description=f"{team_name} operatives — type a word from the board to guess! {clue_num} guess(es).\n**15 seconds per guess.**",
                    color=discord.Color.gold(),
                )
            )

            guesses_made = 0
            keep_guessing = True
            while guesses_made < clue_num + 1 and keep_guessing:
                if self.is_stopped():
                    return

                guess_msg = await self.listen_for_answer(
                    check=lambda m: m.channel == self.channel and m.author in ops
                                   and m.content.strip().upper() in [w.upper() for w in words]
                                   and m.content.strip().upper() not in [r.upper() for r in revealed],
                    timeout=15.0,
                )

                if not guess_msg:
                    await self.channel.send("⏱️ No guess — ending turn.")
                    keep_guessing = False
                    break

                guessed_word = next((w for w in words if w.upper() == guess_msg.content.strip().upper()), None)
                if not guessed_word:
                    continue

                revealed.add(guessed_word)
                color = word_map[guessed_word]

                if color == "X":
                    await self.channel.send(
                        embed=discord.Embed(
                            title="💀 ASSASSIN WORD!",
                            description=f"**{guess_msg.author.display_name}** hit the assassin word **{guessed_word}**!\n{team_name} **LOSES**!",
                            color=discord.Color.dark_red(),
                        )
                    )
                    winner = "B" if current_team == "A" else "A"
                    keep_guessing = False
                    break
                elif (current_team == "A" and color == "A") or (current_team == "B" and color == "B"):
                    if guessed_word in a_remaining:
                        a_remaining.remove(guessed_word)
                    elif guessed_word in b_remaining:
                        b_remaining.remove(guessed_word)
                    await self.channel.send(f"✅ **{guessed_word}** — {team_name}'s word!")
                    guesses_made += 1
                    if not a_remaining or not b_remaining:
                        keep_guessing = False
                        break
                else:
                    opp_team = "🔵 Blue" if color == "A" else "🔴 Red" if color == "B" else "Bystander ⬜"
                    await self.channel.send(f"❌ **{guessed_word}** — {opp_team}! Turn ends.")
                    if guessed_word in a_remaining:
                        a_remaining.remove(guessed_word)
                    elif guessed_word in b_remaining:
                        b_remaining.remove(guessed_word)
                    keep_guessing = False

            if winner:
                break
            current_team = "B" if current_team == "A" else "A"

        if self.is_stopped():
            return

        if not winner:
            winner = "A" if not a_remaining else "B" if not b_remaining else "draw"

        team_name = "🔵 Blue Team" if winner == "A" else "🔴 Red Team" if winner == "B" else "Nobody"
        members = team_a if winner == "A" else team_b if winner == "B" else self.players
        result = discord.Embed(
            title=f"🔑 Codenames — {team_name} Wins!",
            description=f"**Winners:** {', '.join(p.display_name for p in members)}\n\n"
                        f"Final board:\n```\n{make_board_display(set(words))}\n```",
            color=discord.Color.blue() if winner == "A" else discord.Color.red(),
        )
        await self.channel.send(embed=result)
