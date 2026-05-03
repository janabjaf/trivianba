"""odds.py – ESPN scoreboard (free, no key) + auto-generated betting lines."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import aiohttp

ESPN_SCOREBOARD = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
)

GAMES_TTL = 120   # 2 min cache – ESPN is free, refresh often


# ══════════════════════════════════════════════════════════════════════════════
# Odds generation from team records (no external API needed)
# ══════════════════════════════════════════════════════════════════════════════

def _parse_record(summary: str):
    """Parse '32-18' → (32, 18)."""
    try:
        w, l = summary.split("-")
        return int(w), int(l)
    except Exception:
        return 0, 0


def _win_pct(wins: int, losses: int) -> float:
    total = wins + losses
    return wins / total if total > 0 else 0.5


def _prob_to_ml(p: float) -> int:
    """Win probability → American moneyline, rounded to nearest 5."""
    p = max(0.05, min(0.95, p))
    if p >= 0.5:
        return -round(p / (1 - p) * 100 / 5) * 5
    else:
        return round((1 - p) / p * 100 / 5) * 5


def generate_odds_for_game(game: Dict) -> Dict[str, Any]:
    """
    Generate realistic NBA betting lines from ESPN team records.

    Returns a dict matching the same shape that views.py expects:
      h2h     → {team: ml_price}
      spreads → {team: {"price": int, "point": float}}
      totals  → {"Over": {"price": int, "point": float}, "Under": {...}}
    """
    hw, hl = _parse_record(game.get("home_record", ""))
    aw, al = _parse_record(game.get("away_record", ""))

    h_wpct = _win_pct(hw, hl)
    a_wpct = _win_pct(aw, al)

    # ── Spread ─────────────────────────────────────────────────────────────────
    # Home-court advantage ≈ 3 pts; each 4% win-pct gap ≈ 1 additional pt
    raw_spread = (h_wpct - a_wpct) * 25 + 3.0
    spread = round(raw_spread * 2) / 2          # round to nearest .5
    spread = max(-14.5, min(14.5, spread))      # cap at ±14.5

    # ── Moneyline from spread ──────────────────────────────────────────────────
    # Each point of spread ≈ 3.3% win probability
    h_win_prob = max(0.05, min(0.95, 0.5 + spread * 0.033))
    a_win_prob = 1.0 - h_win_prob

    home_ml = _prob_to_ml(h_win_prob)
    away_ml = _prob_to_ml(a_win_prob)

    # ── Total ──────────────────────────────────────────────────────────────────
    # NBA average ≈ 225 pts; better teams (higher combined win%) tend to go Over
    total = 225.0 + (h_wpct + a_wpct - 1.0) * 10
    total = round(total * 2) / 2

    home_team = game["home_team"]
    away_team = game["away_team"]

    return {
        "h2h": {
            home_team: home_ml,
            away_team: away_ml,
        },
        "spreads": {
            home_team: {"price": -110, "point": -spread},
            away_team: {"price": -110, "point":  spread},
        },
        "totals": {
            "Over":  {"price": -110, "point": total},
            "Under": {"price": -110, "point": total},
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# ESPN fetcher
# ══════════════════════════════════════════════════════════════════════════════

class OddsFetcher:
    def __init__(self) -> None:
        self._session: Optional[aiohttp.ClientSession] = None
        self._games_cache: List[Dict] = []
        self._games_ts: float = 0.0

    # ── HTTP session ──────────────────────────────────────────────────────────

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    # ── ESPN scoreboard ───────────────────────────────────────────────────────

    async def get_games(self, force: bool = False) -> List[Dict]:
        """Today + tomorrow NBA games from ESPN (no key required)."""
        now = time.monotonic()
        if not force and self._games_cache and now - self._games_ts < GAMES_TTL:
            return self._games_cache

        session = await self._get_session()
        games: List[Dict] = []
        seen: set = set()

        for delta in [0, 1]:
            date = (
                datetime.now(timezone.utc) + timedelta(days=delta)
            ).strftime("%Y%m%d")
            try:
                async with session.get(
                    ESPN_SCOREBOARD,
                    params={"dates": date, "limit": 20},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json(content_type=None)
                    for event in data.get("events", []):
                        g = _parse_espn_event(event)
                        if g and g["event_id"] not in seen:
                            seen.add(g["event_id"])
                            games.append(g)
            except Exception:
                pass

        if games:
            self._games_cache = games
            self._games_ts = now

        return self._games_cache

    async def get_completed_games(self, days_back: int = 2) -> List[Dict]:
        """Recently completed games for bet settlement."""
        session = await self._get_session()
        games: List[Dict] = []
        seen: set = set()

        for delta in range(days_back + 1):
            date = (
                datetime.now(timezone.utc) - timedelta(days=delta)
            ).strftime("%Y%m%d")
            try:
                async with session.get(
                    ESPN_SCOREBOARD,
                    params={"dates": date, "limit": 20},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json(content_type=None)
                    for event in data.get("events", []):
                        g = _parse_espn_event(event)
                        if g and g["event_id"] not in seen and g.get("completed"):
                            seen.add(g["event_id"])
                            games.append(g)
            except Exception:
                pass

        return games

    async def get_game_with_odds(self, event_id: str) -> Optional[Dict]:
        """Return ESPN game data merged with auto-generated odds."""
        games = await self.get_games()
        game  = next((g for g in games if g["event_id"] == event_id), None)
        if not game:
            return None
        odds = generate_odds_for_game(game)
        return {**game, "odds": odds}


# ── ESPN parsing ──────────────────────────────────────────────────────────────

def _parse_espn_event(event: Dict) -> Optional[Dict]:
    try:
        comp        = event["competitions"][0]
        competitors = comp["competitors"]
        home = next(c for c in competitors if c["homeAway"] == "home")
        away = next(c for c in competitors if c["homeAway"] == "away")

        status_obj = event["status"]["type"]
        completed  = status_obj.get("completed", False)
        state      = status_obj.get("name", "")

        home_score = away_score = None
        if completed or state == "STATUS_IN_PROGRESS":
            try:
                home_score = int(home.get("score") or 0)
                away_score = int(away.get("score") or 0)
            except (TypeError, ValueError):
                pass

        home_record = (
            home.get("records", [{}])[0].get("summary", "")
            if home.get("records") else ""
        )
        away_record = (
            away.get("records", [{}])[0].get("summary", "")
            if away.get("records") else ""
        )

        return {
            "event_id":      event["id"],
            "name":          event.get("name", ""),
            "short_name":    event.get("shortName", ""),
            "commence_time": event.get("date", ""),
            "home_team":     home["team"]["displayName"],
            "away_team":     away["team"]["displayName"],
            "home_abbr":     home["team"].get("abbreviation", ""),
            "away_abbr":     away["team"].get("abbreviation", ""),
            "home_record":   home_record,
            "away_record":   away_record,
            "completed":     completed,
            "state":         state,
            "home_score":    home_score,
            "away_score":    away_score,
        }
    except (KeyError, IndexError, StopIteration, TypeError):
        return None


# ══════════════════════════════════════════════════════════════════════════════
# Odds math utilities
# ══════════════════════════════════════════════════════════════════════════════

def fmt_odds(american: int) -> str:
    return f"+{american}" if american > 0 else str(american)


def calc_profit(stake: float, american: int) -> float:
    """Potential profit (not including stake return)."""
    if american > 0:
        return round(stake * (american / 100), 2)
    return round(stake * (100 / abs(american)), 2)


def implied_prob(american: int) -> float:
    if american > 0:
        return 100 / (american + 100)
    return abs(american) / (abs(american) + 100)


def evaluate_bet(
    bet_type: str,
    selection: str,
    point: Optional[float],
    home_team: str,
    away_team: str,
    home_score: int,
    away_score: int,
) -> str:
    """Return 'won', 'lost', or 'push'."""
    if bet_type == "h2h":
        winner = home_team if home_score > away_score else away_team
        return "won" if selection == winner else "lost"

    elif bet_type == "spreads":
        if point is None:
            return "lost"
        team_margin = (
            home_score - away_score if selection == home_team
            else away_score - home_score
        )
        covered = team_margin + point
        if covered > 0:
            return "won"
        elif covered < 0:
            return "lost"
        return "push"

    elif bet_type == "totals":
        if point is None:
            return "lost"
        total = home_score + away_score
        if selection == "Over":
            if total > point:   return "won"
            if total < point:   return "lost"
            return "push"
        else:  # Under
            if total < point:   return "won"
            if total > point:   return "lost"
            return "push"

    return "lost"
