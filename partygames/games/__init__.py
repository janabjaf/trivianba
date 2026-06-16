from .social import (
    IdentityTheft, Alibi, Werewolf, Spyfall, FakeArtist,
    MurderMystery, AuctionHeist, Kingmaker, Assassin,
)
from .creative import (
    MoviePitch, ChainReaction, TimeTraveler, HotTake,
    EmojiStory, StoryTime, DebateClub, Quiplash, PersonalitySwap,
)
from .word import (
    WordBomb, AlphabetChain, GroupHangman, EscapeRoomRace,
    TwentyQuestions, Wavelength, Taboo, Codenames,
)
from .competition import (
    TriviaClash, WouldYouRather, PriceIsRight, HotSeat,
    GladiatorDraft, MathDuel, Bingo, TwoTruthsAndALie,
    GladiatorTournament,
)

GAME_REGISTRY = {
    # ── Social Deduction ──────────────────────────────────────────────────────
    "🎭 Identity Theft":   IdentityTheft,
    "🕵️ Alibi":           Alibi,
    "🐺 Werewolf":         Werewolf,
    "🌍 Spyfall":          Spyfall,
    "🎨 Fake Artist":      FakeArtist,
    "🔍 Murder Mystery":   MurderMystery,
    "🏺 Auction Heist":    AuctionHeist,
    "👑 Kingmaker":        Kingmaker,
    "🗡️ Assassin":        Assassin,
    # ── Creative ──────────────────────────────────────────────────────────────
    "🎬 Movie Pitch":      MoviePitch,
    "🔗 Chain Reaction":   ChainReaction,
    "🌌 Time Traveler":    TimeTraveler,
    "🔥 Hot Take":         HotTake,
    "😂 Emoji Story":      EmojiStory,
    "📖 Story Time":       StoryTime,
    "⚖️ Debate Club":     DebateClub,
    "😄 Quiplash":         Quiplash,
    "🤹 Personality Swap": PersonalitySwap,
    # ── Word & Puzzle ─────────────────────────────────────────────────────────
    "💣 Word Bomb":        WordBomb,
    "🔤 Alphabet Chain":   AlphabetChain,
    "🎯 Hangman":          GroupHangman,
    "🔐 Escape Room":      EscapeRoomRace,
    "❓ 20 Questions":     TwentyQuestions,
    "〰️ Wavelength":      Wavelength,
    "🚫 Taboo":            Taboo,
    "🔑 Codenames":        Codenames,
    # ── Competition ───────────────────────────────────────────────────────────
    "🎓 Trivia Clash":          TriviaClash,
    "🤔 Would You Rather":      WouldYouRather,
    "💰 Price Is Right":        PriceIsRight,
    "🔥 Hot Seat":              HotSeat,
    "⚔️ Gladiator Draft":      GladiatorDraft,
    "🧮 Math Duel":             MathDuel,
    "🎱 Bingo":                 Bingo,
    "🤥 Two Truths and a Lie":  TwoTruthsAndALie,
    "🏆 Gladiator Tournament":  GladiatorTournament,
}

GAME_NAMES = list(GAME_REGISTRY.keys())
