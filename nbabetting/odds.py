"""odds.py — Enhanced odds engine: real team stats, power ratings, vig variation,
ML-from-spread derivation, back-to-back detection, form weighting, line movement."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import aiohttp

# ── ESPN endpoints ────────────────────────────────────────────────────────────
ESPN_SCOREBOARD  = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
ESPN_INJURIES    = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
ESPN_SUMMARY     = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary"
ESPN_LEADERS     = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/leaders"
ESPN_TEAM_STATS    = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}/statistics"
ESPN_TEAM_LEADERS  = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}/leaders"

# ── Cache TTLs (seconds) ──────────────────────────────────────────────────────
GAMES_TTL        = 120     # 2 min
INJURIES_TTL     = 300     # 5 min
LEADERS_TTL      = 3600    # 1 hr
TEAM_STATS_TTL   = 21600   # 6 hrs  — scoring avgs barely shift day-to-day
YESTERDAY_TTL    = 3600    # 1 hr   — who played yesterday

# ── ESPN numeric team IDs (permanent, never change) ──────────────────────────
TEAM_IDS: Dict[str, int] = {
    "ATL": 1,  "BOS": 2,  "NOP": 3,  "CHI": 4,  "CLE": 5,
    "DAL": 6,  "DEN": 7,  "DET": 8,  "GSW": 9,  "HOU": 10,
    "IND": 11, "LAC": 12, "LAL": 13, "MIA": 14, "MIL": 15,
    "MIN": 16, "BKN": 17, "NYK": 18, "ORL": 19, "PHI": 20,
    "PHX": 21, "POR": 22, "SAC": 23, "SAS": 24, "OKC": 25,
    "UTA": 26, "WAS": 27, "TOR": 28, "MEM": 29, "CHA": 30,
}

# ── Moneyline lookup table derived from spread (NBA-calibrated) ───────────────
# (max_spread, fav_ml, dog_ml)  — nearest row for any spread value
_ML_TABLE: List[Tuple[float, int, int]] = [
    (0.5,  -115, +100),
    (1.0,  -120, +100),
    (1.5,  -130, +110),
    (2.0,  -140, +120),
    (2.5,  -150, +130),
    (3.0,  -165, +140),
    (3.5,  -180, +155),
    (4.0,  -195, +168),
    (4.5,  -210, +180),
    (5.0,  -225, +192),
    (5.5,  -240, +205),
    (6.0,  -258, +220),
    (6.5,  -275, +235),
    (7.0,  -295, +252),
    (7.5,  -318, +270),
    (8.0,  -342, +290),
    (8.5,  -368, +310),
    (9.0,  -395, +330),
    (9.5,  -425, +355),
    (10.0, -460, +380),
    (11.0, -520, +430),
    (12.0, -600, +480),
]

HOME_COURT_ADV = 2.0   # pts — modern NBA, down from historical 3


# ══════════════════════════════════════════════════════════════════════════════
# Small helpers
# ══════════════════════════════════════════════════════════════════════════════

def _parse_record(summary: str) -> Tuple[int, int]:
    try:
        w, l = summary.split("-")
        return int(w), int(l)
    except Exception:
        return 0, 0


def _win_pct(wins: int, losses: int) -> float:
    t = wins + losses
    return wins / t if t > 0 else 0.5


def _first(d: Dict, keys: List[str]) -> Optional[float]:
    for k in keys:
        v = d.get(k)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return None


def _ml_from_spread(spread_abs: float) -> Tuple[int, int]:
    """Return (favourite_ml, underdog_ml) for a given absolute spread."""
    for threshold, fav, dog in _ML_TABLE:
        if spread_abs <= threshold:
            return fav, dog
    # Extrapolate beyond 12 pts
    extra = spread_abs - 12.0
    fav = -600 - int(extra * 50)
    dog = +480 + int(extra * 40)
    return fav, dog


def _spread_vig(spread_abs: float) -> Tuple[int, int]:
    """Spread juice: (fav_price, dog_price). NBA spreads are usually close to -110/-110."""
    if spread_abs <= 3.0:   return -110, -110
    if spread_abs <= 6.0:   return -112, -108
    if spread_abs <= 9.0:   return -115, -105
    return -118, -102


# ══════════════════════════════════════════════════════════════════════════════
# Power rating
# ══════════════════════════════════════════════════════════════════════════════

def _power_rating(
    wins: int,
    losses: int,
    last10_wins: int,
    home_wins: int,
    home_losses: int,
    away_wins: int,
    away_losses: int,
    is_home: bool,
) -> float:
    """
    Weighted composite win probability:
      50% season record + 30% last-10 form + 20% home/away venue record.
    Returns a value in [0.05, 0.95].
    """
    season_pct = _win_pct(wins, losses)
    last10_pct = last10_wins / 10.0

    if is_home:
        venue_pct = (
            _win_pct(home_wins, home_losses)
            if (home_wins + home_losses) >= 5
            else season_pct
        )
    else:
        venue_pct = (
            _win_pct(away_wins, away_losses)
            if (away_wins + away_losses) >= 5
            else season_pct
        )

    rating = season_pct * 0.50 + last10_pct * 0.30 + venue_pct * 0.20
    return max(0.05, min(0.95, rating))


# ══════════════════════════════════════════════════════════════════════════════
# Injury impact
# ══════════════════════════════════════════════════════════════════════════════

_OUT_IMPACT         = {1: 3.5,  2: 1.5,  3: 0.5}
_DOUBTFUL_IMPACT    = {1: 2.0,  2: 0.75, 3: 0.25}
_QUESTIONABLE_IMPACT= {1: 0.75, 2: 0.25, 3: 0.0}
_IMPACTFUL_STATUSES = {"out", "doubtful", "questionable"}


def _player_tier(pts_avg: float) -> int:
    if pts_avg >= 20: return 1
    if pts_avg >= 12: return 2
    return 3


def _injury_shift(
    abbr: str,
    injuries: Dict[str, List[Dict]],
    stat_leaders: Dict[str, Dict],
) -> Tuple[float, List[str]]:
    """Return (pts_to_shift, [display_notes])."""
    team_injuries = injuries.get(abbr, [])
    if not team_injuries:
        return 0.0, []

    team_pts: Dict[str, float] = {
        name.lower(): info["pts"]
        for name, info in stat_leaders.items()
        if info.get("team_abbr") == abbr
    }

    shift = 0.0
    notes: List[str] = []
    emoji_map = {"out": "🚫", "doubtful": "⚠️", "questionable": "❓"}

    for inj in team_injuries:
        status = inj.get("status", "").lower()
        if status not in _IMPACTFUL_STATUSES:
            continue
        name = inj.get("name", "")
        pts  = team_pts.get(name.lower(), 0.0)
        if pts == 0.0:
            continue
        tier = _player_tier(pts)
        if status == "out":
            shift += _OUT_IMPACT.get(tier, 0.5)
        elif status == "doubtful":
            shift += _DOUBTFUL_IMPACT.get(tier, 0.25)
        else:
            shift += _QUESTIONABLE_IMPACT.get(tier, 0.0)
        notes.append(f"{emoji_map[status]} **{name}** ({abbr}) — {inj['status']}")

    return shift, notes


# ══════════════════════════════════════════════════════════════════════════════
# Line movement from bet distribution
# ══════════════════════════════════════════════════════════════════════════════

def _line_movement(
    home_team: str,
    away_team: str,
    bet_dist: Dict[str, float],
) -> Tuple[float, float]:
    """
    Given the total money wagered on each side (from the server's bets),
    return (spread_shift, total_shift).

    spread_shift > 0  → home getting heavier action → shift line against home
                        (make home more expensive, reduce underdog price)
    total_shift  > 0  → Over getting heavier action → bump total up
    """
    # ── Spread / moneyline side action ───────────────────────────────────────
    home_money = bet_dist.get(home_team, 0.0)
    away_money = bet_dist.get(away_team, 0.0)
    h2h_total  = home_money + away_money

    spread_shift = 0.0
    if h2h_total >= 100:   # need meaningful volume
        home_pct = home_money / h2h_total
        if home_pct >= 0.80:
            spread_shift = 1.5
        elif home_pct >= 0.70:
            spread_shift = 1.0
        elif home_pct >= 0.60:
            spread_shift = 0.5
        elif home_pct <= 0.20:
            spread_shift = -1.5
        elif home_pct <= 0.30:
            spread_shift = -1.0
        elif home_pct <= 0.40:
            spread_shift = -0.5

    # ── Totals side action ────────────────────────────────────────────────────
    over_money  = bet_dist.get("Over",  0.0)
    under_money = bet_dist.get("Under", 0.0)
    ou_total    = over_money + under_money

    total_shift = 0.0
    if ou_total >= 100:
        over_pct = over_money / ou_total
        if over_pct >= 0.80:
            total_shift = 1.0
        elif over_pct >= 0.70:
            total_shift = 0.5
        elif over_pct <= 0.20:
            total_shift = -1.0
        elif over_pct <= 0.30:
            total_shift = -0.5

    return spread_shift, total_shift


# ══════════════════════════════════════════════════════════════════════════════
# Core odds generation
# ══════════════════════════════════════════════════════════════════════════════

def generate_odds_for_game(
    game: Dict,
    injuries:       Optional[Dict[str, List[Dict]]] = None,
    stat_leaders:   Optional[Dict[str, Dict]]       = None,
    home_ts:        Optional[Dict]                  = None,
    away_ts:        Optional[Dict]                  = None,
    bet_dist:       Optional[Dict[str, float]]      = None,
) -> Dict[str, Any]:
    """
    Produce h2h / spreads / totals with:
     - Real team ppg/papg from ESPN stats (if available)
     - Power rating (season + last-10 + venue record)
     - Back-to-back penalty
     - Injury adjustment
     - Line movement from server bet volume
     - Spread-derived moneyline (not flat win%)
     - Spread-appropriate vig
    """
    injuries     = injuries     or {}
    stat_leaders = stat_leaders or {}
    home_ts      = home_ts      or {}
    away_ts      = away_ts      or {}
    bet_dist     = bet_dist     or {}

    home_team  = game["home_team"]
    away_team  = game["away_team"]
    home_abbr  = game.get("home_abbr", "")
    away_abbr  = game.get("away_abbr", "")

    # ── Parse records from game ───────────────────────────────────────────────
    hw,  hl  = _parse_record(game.get("home_record",       "0-0"))
    aw,  al  = _parse_record(game.get("away_record",       "0-0"))
    hh_w, hh_l = _parse_record(game.get("home_home_record","0-0"))
    ar_w, ar_l = _parse_record(game.get("away_road_record","0-0"))
    h_l10w = game.get("home_last10_wins", 5)
    a_l10w = game.get("away_last10_wins", 5)

    # ── Power ratings ─────────────────────────────────────────────────────────
    h_power = _power_rating(hw, hl, h_l10w, hh_w, hh_l, 0, 0, is_home=True)
    a_power = _power_rating(aw, al, a_l10w, 0, 0, ar_w, ar_l, is_home=False)

    # ── Spread from real scoring data (preferred) or power rating (fallback) ──
    h_ppg  = home_ts.get("ppg")
    h_papg = home_ts.get("papg")
    a_ppg  = away_ts.get("ppg")
    a_papg = away_ts.get("papg")

    if h_ppg and h_papg and a_ppg and a_papg:
        # Vegas-style power rating: avg of team's offence vs opponent's defence
        h_expected = (h_ppg + a_papg) / 2
        a_expected = (a_ppg + h_papg) / 2
        raw_spread = h_expected - a_expected + HOME_COURT_ADV
    else:
        # Fallback: pure win-percentage spread (~4% win-pct gap per point)
        raw_spread = (h_power - a_power) * 25 + HOME_COURT_ADV

    # ── Back-to-back penalty (-2.5 pts for team on B2B) ──────────────────────
    if home_ts.get("is_back_to_back"):
        raw_spread -= 2.5
    if away_ts.get("is_back_to_back"):
        raw_spread += 2.5

    # ── Injury adjustment ─────────────────────────────────────────────────────
    h_inj_shift, h_notes = _injury_shift(home_abbr, injuries, stat_leaders)
    a_inj_shift, a_notes = _injury_shift(away_abbr, injuries, stat_leaders)
    injury_notes = h_notes + a_notes
    raw_spread  -= h_inj_shift
    raw_spread  += a_inj_shift

    # ── Line movement ─────────────────────────────────────────────────────────
    spread_mv, total_mv = _line_movement(home_team, away_team, bet_dist)
    raw_spread += spread_mv   # positive = home favoured more → home side more expensive

    # ── Round to nearest 0.5, clamp ──────────────────────────────────────────
    spread = round(raw_spread * 2) / 2
    spread = max(-24.0, min(24.0, spread))

    # ── Moneyline derived from spread ─────────────────────────────────────────
    spread_abs = abs(spread)
    fav_ml, dog_ml = _ml_from_spread(spread_abs)

    if spread >= 0:   # home is favourite (or PK)
        h_ml, a_ml = fav_ml, dog_ml
    else:             # away is favourite
        h_ml, a_ml = dog_ml, fav_ml

    if spread_abs < 0.5:  # pick'em
        h_ml = a_ml = -110

    # ── Total ─────────────────────────────────────────────────────────────────
    if h_ppg and h_papg and a_ppg and a_papg:
        h_expected = (h_ppg + a_papg) / 2
        a_expected = (a_ppg + h_papg) / 2
        base_total = h_expected + a_expected
    else:
        base_total = 225.0 + (h_power + a_power - 1.0) * 10

    # Back-to-back teams score fewer points
    if home_ts.get("is_back_to_back"):
        base_total -= 2.0
    if away_ts.get("is_back_to_back"):
        base_total -= 2.0

    # Injury total impact
    base_total -= (h_inj_shift + a_inj_shift) * 2.5

    # Line movement
    base_total += total_mv

    total = round(base_total * 2) / 2

    # ── Spread vig ────────────────────────────────────────────────────────────
    fav_price, dog_price = _spread_vig(spread_abs)
    if spread >= 0:
        h_spread_price, a_spread_price = fav_price, dog_price
    else:
        h_spread_price, a_spread_price = dog_price, fav_price

    # ── Line movement note ────────────────────────────────────────────────────
    if abs(spread_mv) >= 0.5 or abs(total_mv) >= 0.5:
        injury_notes.append("📊 Line has moved due to betting action on this server.")

    return {
        "h2h": {
            home_team: h_ml,
            away_team: a_ml,
        },
        "spreads": {
            home_team: {"price": h_spread_price, "point": -spread},
            away_team: {"price": a_spread_price, "point":  spread},
        },
        "totals": {
            "Over":  {"price": -110, "point": total},
            "Under": {"price": -110, "point": total},
        },
        "injury_notes": injury_notes,
        "_meta": {
            "spread":           spread,
            "total":            total,
            "h_power":          round(h_power, 3),
            "a_power":          round(a_power, 3),
            "h_back_to_back":   home_ts.get("is_back_to_back", False),
            "a_back_to_back":   away_ts.get("is_back_to_back", False),
            "spread_moved":     spread_mv,
            "total_moved":      total_mv,
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# Player props
# ══════════════════════════════════════════════════════════════════════════════

def generate_player_props_for_game(
    game: Dict,
    stat_leaders: Dict[str, Dict],
) -> Dict[str, Any]:
    """Build player prop lines from live ESPN season-leader data."""
    props: Dict[str, Any] = {}
    home_abbr = game.get("home_abbr", "")
    away_abbr = game.get("away_abbr", "")

    for pname, pdata in stat_leaders.items():
        if pdata.get("team_abbr") not in (home_abbr, away_abbr):
            continue

        pts = pdata.get("pts", 0.0)
        reb = pdata.get("reb", 0.0)
        ast = pdata.get("ast", 0.0)
        pra = pts + reb + ast
        tier = _player_tier(pts)

        def _line(val: float, offset: float = -0.5) -> float:
            return round((val + offset) * 2) / 2

        props[pname] = {
            "pts":       _line(pts),
            "reb":       _line(reb),
            "ast":       _line(ast),
            "pra":       _line(pra, -1.0),
            "team_abbr": pdata["team_abbr"],
            "tier":      tier,
        }

    return props


# ══════════════════════════════════════════════════════════════════════════════
# ESPN event parser (updated: home/away/last-10 records)
# ══════════════════════════════════════════════════════════════════════════════

def _parse_record_by_type(records: List[Dict], *type_names: str) -> str:
    for r in records:
        if r.get("type") in type_names or r.get("name", "").lower() in type_names:
            return r.get("summary", "0-0")
    return "0-0"


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

        h_records = home.get("records", [])
        a_records = away.get("records", [])

        # Overall record
        home_record = _parse_record_by_type(h_records, "total", "overall")
        away_record = _parse_record_by_type(a_records, "total", "overall")

        # Home/away venue records
        home_home_record = _parse_record_by_type(h_records, "home")
        away_road_record = _parse_record_by_type(a_records, "road", "away")

        # Last-10 records
        h_last10 = _parse_record_by_type(h_records, "lastTen", "last-10", "l10")
        a_last10 = _parse_record_by_type(a_records, "lastTen", "last-10", "l10")
        h_l10_wins, _ = _parse_record(h_last10)
        a_l10_wins, _ = _parse_record(a_last10)

        return {
            "event_id":            event["id"],
            "name":                event.get("name", ""),
            "short_name":          event.get("shortName", ""),
            "commence_time":       event.get("date", ""),
            "home_team":           home["team"]["displayName"],
            "away_team":           away["team"]["displayName"],
            "home_abbr":           home["team"].get("abbreviation", "").upper(),
            "away_abbr":           away["team"].get("abbreviation", "").upper(),
            "home_record":         home_record,
            "away_record":         away_record,
            "home_home_record":    home_home_record,
            "away_road_record":    away_road_record,
            "home_last10_wins":    h_l10_wins,
            "away_last10_wins":    a_l10_wins,
            "completed":           completed,
            "state":               state,
            "home_score":          home_score,
            "away_score":          away_score,
        }
    except (KeyError, IndexError, StopIteration, TypeError):
        return None


# ══════════════════════════════════════════════════════════════════════════════
# ESPN Fetcher
# ══════════════════════════════════════════════════════════════════════════════

class OddsFetcher:
    def __init__(self) -> None:
        self._session: Optional[aiohttp.ClientSession] = None

        self._games_cache:      List[Dict] = []
        self._games_ts:         float = 0.0

        self._injuries_cache:   Dict[str, List[Dict]] = {}
        self._injuries_ts:      float = 0.0

        self._leaders_cache:    Dict[str, Dict] = {}
        self._leaders_ts:       float = 0.0

        # Per-team scoring stats cache: {abbr: {ppg, papg, ...}}
        self._team_stats_cache: Dict[str, Dict] = {}
        self._team_stats_ts:    Dict[str, float] = {}

        # Per-team player leaders cache: {abbr: {player_name: {pts, reb, ast, ...}}}
        self._team_leaders_cache: Dict[str, Dict] = {}
        self._team_leaders_ts:    Dict[str, float] = {}

        # Set of team abbrs that played yesterday (for B2B detection)
        self._played_yesterday: Set[str] = set()
        self._played_yesterday_ts: float = 0.0

    # ── Session ───────────────────────────────────────────────────────────────

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    # ── Team stats ────────────────────────────────────────────────────────────

    async def get_team_stats(self, abbr: str) -> Dict:
        """
        Fetch season averages for a team from ESPN.
        Returns {ppg, papg, off_rtg, def_rtg, is_back_to_back}.
        Falls back to empty dict on failure — caller uses win-pct path.
        """
        now = time.monotonic()
        if (
            abbr in self._team_stats_cache
            and now - self._team_stats_ts.get(abbr, 0) < TEAM_STATS_TTL
        ):
            ts = self._team_stats_cache[abbr]
            # B2B is time-sensitive — refresh regardless of TTL
            ts["is_back_to_back"] = abbr in await self._get_played_yesterday()
            return ts

        team_id = TEAM_IDS.get(abbr)
        if not team_id:
            return {}

        session = await self._get_session()
        stats: Dict = {}
        try:
            url = ESPN_TEAM_STATS.format(team_id=team_id)
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return {}
                data = await resp.json(content_type=None)

            # Try multiple response shapes ESPN uses
            raw: List[Dict] = []

            # Shape 1: data["results"]["stats"]["categories"][n]["stats"]
            cats = (
                data.get("results", {})
                    .get("stats", {})
                    .get("categories", [])
            )
            for cat in cats:
                raw.extend(cat.get("stats", []))

            # Shape 2: data["statistics"]["categories"][n]["stats"]
            if not raw:
                cats2 = data.get("statistics", {}).get("categories", [])
                for cat in cats2:
                    raw.extend(cat.get("stats", []))

            # Shape 3: flat data["statistics"] list
            if not raw:
                flat = data.get("statistics", [])
                if isinstance(flat, list):
                    raw = flat

            stat_map: Dict[str, float] = {}
            for item in raw:
                name = (item.get("name") or "").lower()
                try:
                    val = float(item.get("value", 0))
                except (TypeError, ValueError):
                    continue
                stat_map[name] = val

            ppg  = _first(stat_map, ["avgpoints",  "pointspergame",      "points"])
            papg = _first(stat_map, ["avgpointsallowed", "pointsallowedpergame"])
            offr = _first(stat_map, ["offensiverating", "offrtg", "offeff"])
            defr = _first(stat_map, ["defensiverating", "defrtg", "defeff"])

            if ppg is not None:
                stats["ppg"]  = ppg
            if papg is not None:
                stats["papg"] = papg
            if offr is not None:
                stats["off_rtg"] = offr
            if defr is not None:
                stats["def_rtg"] = defr

        except Exception:
            pass

        stats["is_back_to_back"] = abbr in await self._get_played_yesterday()
        self._team_stats_cache[abbr] = stats
        self._team_stats_ts[abbr]    = now
        return stats

    # ── Back-to-back detection ────────────────────────────────────────────────

    async def _get_played_yesterday(self) -> Set[str]:
        """Return set of team abbrs that had a game yesterday."""
        now = time.monotonic()
        if self._played_yesterday and now - self._played_yesterday_ts < YESTERDAY_TTL:
            return self._played_yesterday

        yesterday = (
            datetime.now(timezone.utc) - timedelta(days=1)
        ).strftime("%Y%m%d")
        session = await self._get_session()
        played: Set[str] = set()

        try:
            async with session.get(
                ESPN_SCOREBOARD,
                params={"dates": yesterday, "limit": 20},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    for event in data.get("events", []):
                        g = _parse_espn_event(event)
                        if g:
                            played.add(g["home_abbr"])
                            played.add(g["away_abbr"])
        except Exception:
            pass

        self._played_yesterday    = played
        self._played_yesterday_ts = now
        return played

    # ── Per-team player leaders (for props) ───────────────────────────────────

    async def get_team_player_leaders(self, abbr: str) -> Dict[str, Dict]:
        """
        Fetch the top scorers/rebounders/assisters for a specific team from ESPN.
        Returns {player_name: {pts, reb, ast, pra, team_abbr, tier}}.
        Falls back to empty dict on failure; merged with global leaders in caller.
        """
        now = time.monotonic()
        if (
            abbr in self._team_leaders_cache
            and now - self._team_leaders_ts.get(abbr, 0) < LEADERS_TTL
        ):
            return self._team_leaders_cache[abbr]

        team_id = TEAM_IDS.get(abbr)
        if not team_id:
            return {}

        session = await self._get_session()
        result: Dict[str, Dict] = {}

        try:
            url = ESPN_TEAM_LEADERS.format(team_id=team_id)
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return {}
                data = await resp.json(content_type=None)

            # ESPN team leaders: data["leaders"] is a list of stat categories
            # Each category has "leaders" list with athlete + value
            stat_name_map = {
                "points":   "pts",
                "avgpoints": "pts",
                "rebounds":  "reb",
                "avgrebounds": "reb",
                "assists":   "ast",
                "avgassists": "ast",
            }

            for category in data.get("leaders", []):
                cat_name = category.get("name", "").lower().replace(" ", "")
                stat_key = stat_name_map.get(cat_name)
                if not stat_key:
                    # Try abbreviation field
                    abbrev_map = {"pts": "pts", "reb": "reb", "ast": "ast",
                                  "rpg": "reb", "apg": "ast", "ppg": "pts"}
                    stat_key = abbrev_map.get(
                        category.get("abbreviation", "").lower()
                    )
                if not stat_key:
                    continue

                for entry in category.get("leaders", [])[:5]:
                    athlete = entry.get("athlete", {})
                    pname   = athlete.get("displayName", "")
                    if not pname:
                        continue
                    try:
                        value = float(entry.get("value", 0))
                    except (TypeError, ValueError):
                        continue
                    if pname not in result:
                        result[pname] = {
                            "pts": 0.0, "reb": 0.0, "ast": 0.0,
                            "team_abbr": abbr,
                        }
                    result[pname][stat_key] = value

        except Exception:
            pass

        # Compute PRA and tier for each player
        for pname, d in result.items():
            d["pra"]  = d["pts"] + d["reb"] + d["ast"]
            d["tier"] = _player_tier(d["pts"])

        self._team_leaders_cache[abbr] = result
        self._team_leaders_ts[abbr]    = now
        return result

    # ── Season stat leaders ───────────────────────────────────────────────────

    async def get_stat_leaders(self, force: bool = False) -> Dict[str, Dict]:
        now = time.monotonic()
        if not force and self._leaders_cache and now - self._leaders_ts < LEADERS_TTL:
            return self._leaders_cache

        session = await self._get_session()
        merged: Dict[str, Dict] = {}
        category_key_map = {
            "pointsPerGame":   "pts",
            "reboundsPerGame": "reb",
            "assistsPerGame":  "ast",
        }

        try:
            async with session.get(
                ESPN_LEADERS,
                params={"limit": 50},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return self._leaders_cache
                data = await resp.json(content_type=None)

            for category in data.get("leaders", []):
                stat_key = category_key_map.get(category.get("name", ""))
                if not stat_key:
                    continue
                for entry in category.get("leaders", []):
                    try:
                        athlete   = entry["athlete"]
                        pname     = athlete["displayName"]
                        team_abbr = (
                            athlete.get("team", {}).get("abbreviation", "")
                            or athlete.get("teamAbbrev", "")
                        ).upper()
                        value = float(entry.get("value", 0))
                    except (KeyError, TypeError, ValueError):
                        continue
                    if pname not in merged:
                        merged[pname] = {"pts": 0.0, "reb": 0.0, "ast": 0.0, "team_abbr": team_abbr}
                    merged[pname][stat_key] = value
                    if team_abbr:
                        merged[pname]["team_abbr"] = team_abbr

            leaders: Dict[str, Dict] = {}
            for pname, d in merged.items():
                if d["pts"] == 0.0 and d["reb"] == 0.0 and d["ast"] == 0.0:
                    continue
                d["pra"] = d["pts"] + d["reb"] + d["ast"]
                leaders[pname] = d

            if leaders:
                self._leaders_cache = leaders
                self._leaders_ts    = now

        except Exception:
            pass

        return self._leaders_cache

    # ── Injury report ─────────────────────────────────────────────────────────

    async def get_injuries(self, force: bool = False) -> Dict[str, List[Dict]]:
        now = time.monotonic()
        if not force and self._injuries_cache and now - self._injuries_ts < INJURIES_TTL:
            return self._injuries_cache

        session = await self._get_session()
        result: Dict[str, List[Dict]] = {}

        try:
            async with session.get(
                ESPN_INJURIES,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return self._injuries_cache
                data = await resp.json(content_type=None)

            for team_entry in data.get("injuries", []):
                abbr    = team_entry.get("team", {}).get("abbreviation", "").upper()
                players = []
                for inj in team_entry.get("injuries", []):
                    athlete  = inj.get("athlete", {})
                    full_name = athlete.get("fullName", "")
                    status    = inj.get("status", "")
                    desc      = inj.get("longComment", inj.get("shortComment", ""))
                    if full_name and status:
                        players.append({"name": full_name, "status": status, "description": desc})
                if abbr and players:
                    result[abbr] = players

            self._injuries_cache = result
            self._injuries_ts    = now

        except Exception:
            pass

        return self._injuries_cache

    # ── Scoreboard ────────────────────────────────────────────────────────────

    async def get_games(self, force: bool = False) -> List[Dict]:
        now = time.monotonic()
        if not force and self._games_cache and now - self._games_ts < GAMES_TTL:
            return self._games_cache

        session = await self._get_session()
        games: List[Dict] = []
        seen: set = set()

        for delta in [0, 1]:
            date = (datetime.now(timezone.utc) + timedelta(days=delta)).strftime("%Y%m%d")
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
            self._games_ts    = now
        return self._games_cache

    async def get_completed_games(self, days_back: int = 2) -> List[Dict]:
        session = await self._get_session()
        games: List[Dict] = []
        seen: set = set()

        for delta in range(days_back + 1):
            date = (datetime.now(timezone.utc) - timedelta(days=delta)).strftime("%Y%m%d")
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

    # ── Full game + odds ──────────────────────────────────────────────────────

    async def get_game_with_odds(
        self,
        event_id: str,
        guild_id: Optional[int] = None,
        bets_manager=None,
    ) -> Optional[Dict]:
        """
        Return game data merged with fully enhanced odds:
         - Injury-adjusted, power-rated, back-to-back-aware
         - Line movement applied if guild_id + bets_manager provided
        """
        games = await self.get_games()
        game  = next((g for g in games if g["event_id"] == event_id), None)
        if not game:
            return None

        home_abbr = game.get("home_abbr", "")
        away_abbr = game.get("away_abbr", "")

        # Fetch all data in parallel
        (
            injuries, stat_leaders,
            home_ts, away_ts,
            home_team_leaders, away_team_leaders,
        ) = await asyncio.gather(
            self.get_injuries(),
            self.get_stat_leaders(),
            self.get_team_stats(home_abbr),
            self.get_team_stats(away_abbr),
            self.get_team_player_leaders(home_abbr),
            self.get_team_player_leaders(away_abbr),
        )

        # Merge team-specific leaders (guaranteed to have players from both teams)
        # into global leaders. Team leaders take precedence if both have the player.
        props_leaders: Dict[str, Dict] = {}
        for src in (stat_leaders, home_team_leaders, away_team_leaders):
            for pname, pdata in src.items():
                if pdata.get("team_abbr") in (home_abbr, away_abbr):
                    if pname not in props_leaders:
                        props_leaders[pname] = pdata
                    else:
                        # Merge: keep the higher stat values (team leaders are more accurate)
                        existing = props_leaders[pname]
                        for key in ("pts", "reb", "ast", "pra"):
                            if pdata.get(key, 0) > existing.get(key, 0):
                                existing[key] = pdata[key]

        # Line movement from server's bet volume (optional)
        bet_dist: Dict[str, float] = {}
        if guild_id is not None and bets_manager is not None:
            try:
                bet_dist = bets_manager.get_bet_distribution(guild_id, event_id)
            except Exception:
                pass

        odds  = generate_odds_for_game(game, injuries, stat_leaders, home_ts, away_ts, bet_dist)
        props = generate_player_props_for_game(game, props_leaders)

        return {**game, "odds": odds, "player_props": props}

    # ── Box score ─────────────────────────────────────────────────────────────

    async def get_game_box_score(self, event_id: str) -> Optional[Dict[str, Dict]]:
        session = await self._get_session()
        try:
            async with session.get(
                ESPN_SUMMARY,
                params={"event": event_id},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)

            stat_map: Dict[str, Dict] = {}
            for team_block in data.get("boxscore", {}).get("players", []):
                for stat_group in team_block.get("statistics", []):
                    keys = stat_group.get("keys", [])
                    for athlete_entry in stat_group.get("athletes", []):
                        display_name = athlete_entry.get("athlete", {}).get("displayName", "")
                        raw_stats    = athlete_entry.get("stats", [])
                        if not display_name or not raw_stats:
                            continue
                        parsed: Dict[str, float] = {}
                        for key, val in zip(keys, raw_stats):
                            try:
                                parsed[key.lower()] = float(val)
                            except (ValueError, TypeError):
                                parsed[key.lower()] = 0.0
                        stat_map[display_name] = parsed

            return stat_map or None
        except Exception:
            return None


# ══════════════════════════════════════════════════════════════════════════════
# Utility functions
# ══════════════════════════════════════════════════════════════════════════════

def fmt_odds(american: int) -> str:
    return f"+{american}" if american > 0 else str(american)


def calc_profit(stake: float, american: int) -> float:
    if american > 0:
        return round(stake * (american / 100), 2)
    return round(stake * (100 / abs(american)), 2)


def implied_prob(american: int) -> float:
    if american > 0:
        return 100 / (american + 100)
    return abs(american) / (abs(american) + 100)


def fmt_prop_selection(selection: str) -> str:
    parts = selection.split("|")
    if len(parts) == 3:
        pname, stat, direction = parts
        stat_labels = {
            "pts": "Points", "reb": "Rebounds",
            "ast": "Assists", "pra": "Pts+Reb+Ast",
        }
        return f"{pname} — {stat_labels.get(stat, stat)} {direction}"
    return selection


def evaluate_bet(
    bet_type: str,
    selection: str,
    point: Optional[float],
    home_team: str,
    away_team: str,
    home_score: int,
    away_score: int,
    player_stats: Optional[Dict[str, Dict]] = None,
) -> str:
    """Return 'won', 'lost', or 'push'."""

    if bet_type == "h2h":
        if home_score == away_score:
            return "push"
        winner = home_team if home_score > away_score else away_team
        return "won" if selection == winner else "lost"

    elif bet_type == "spreads":
        if point is None:
            return "lost"
        margin = (
            home_score - away_score if selection == home_team
            else away_score - home_score
        )
        covered = margin + point
        if covered > 0:  return "won"
        if covered < 0:  return "lost"
        return "push"

    elif bet_type == "totals":
        if point is None:
            return "lost"
        total = home_score + away_score
        if selection == "Over":
            if total > point:  return "won"
            if total < point:  return "lost"
            return "push"
        else:
            if total < point:  return "won"
            if total > point:  return "lost"
            return "push"

    elif bet_type == "player_props":
        if point is None or player_stats is None:
            return "push"
        parts = selection.split("|")
        if len(parts) != 3:
            return "push"
        pname, stat, direction = parts[0], parts[1], parts[2]
        pstat = player_stats.get(pname) or {}
        if stat == "pts":
            actual = _first(pstat, ["points", "pts"])
        elif stat == "reb":
            actual = _first(pstat, ["rebounds", "totalrebounds", "reb"])
        elif stat == "ast":
            actual = _first(pstat, ["assists", "ast"])
        elif stat == "pra":
            pts = _first(pstat, ["points",   "pts"])  or 0.0
            reb = _first(pstat, ["rebounds", "reb"])  or 0.0
            ast = _first(pstat, ["assists",  "ast"])  or 0.0
            actual = pts + reb + ast
        else:
            return "push"
        if actual is None:
            return "push"
        if direction == "Over":
            if actual > point:  return "won"
            if actual < point:  return "lost"
            return "push"
        else:
            if actual < point:  return "won"
            if actual > point:  return "lost"
            return "push"

    return "lost"
