"""odds.py — Enhanced odds engine: real team stats, power ratings, vig variation,
ML-from-spread derivation, back-to-back detection, form weighting, line movement."""
from __future__ import annotations

import asyncio
import re
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
ESPN_TEAM_ROSTER    = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}/roster"
ESPN_TEAM_SCHEDULE  = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}/schedule"
ESPN_NEWS           = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/news"
ESPN_PROPS_BASE     = (
    "https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba"
    "/events/{eid}/competitions/{eid}/odds/100/propBets"
)

# ── Prop-type name → internal stat key ───────────────────────────────────────
_PROP_TYPE_MAP: Dict[str, str] = {
    # Core stats
    "Total Points":                        "pts",
    "Total Rebounds":                      "reb",
    "Total Assists":                       "ast",
    # Combo stats
    "Total Points, Rebounds, and Assists": "pra",
    "Total Points and Rebounds":           "pr",
    "Total Points and Assists":            "pa",
    "Total Assists and Rebounds":          "ar",
    # Counting stats
    "Total 3-Point Field Goals":           "threes",
    "Total Steals":                        "stl",
    "Total Blocks":                        "blk",
}

# ── Pre-compiled regex for ESPN athlete IDs in $ref URLs ─────────────────────
_AID_RE = re.compile(r"/athletes/(\d+)")

# ── Cache TTLs (seconds) ──────────────────────────────────────────────────────
GAMES_TTL             = 120     # 2 min
INJURIES_TTL          = 300     # 5 min
LEADERS_TTL           = 3600    # 1 hr
TEAM_STATS_TTL        = 21600   # 6 hrs  — scoring avgs barely shift day-to-day
YESTERDAY_TTL         = 3600    # 1 hr   — who played yesterday
RECENT_COMPLETED_TTL  = 3600    # 1 hr   — list of recent completed games
LAST5_TTL             = 7200    # 2 hrs  — per-team last-5 player averages

# ── ESPN numeric team IDs (permanent, never change) ──────────────────────────
TEAM_IDS: Dict[str, int] = {
    "ATL": 1,  "BOS": 2,  "NOP": 3,  "NO": 3,   "CHI": 4,  "CLE": 5,
    "DAL": 6,  "DEN": 7,  "DET": 8,  "GSW": 9,  "GS": 9,   "HOU": 10,
    "IND": 11, "LAC": 12, "LAL": 13, "MIA": 14, "MIL": 15,
    "MIN": 16, "BKN": 17, "BK": 17,  "NYK": 18, "NY": 18,  "ORL": 19, "PHI": 20,
    "PHX": 21, "PHO": 21, "POR": 22, "SAC": 23, "SAS": 24, "SA": 24,  "OKC": 25,
    "UTA": 26, "UT": 26,  "WAS": 27, "WSH": 27, "TOR": 28, "MEM": 29, "CHA": 30,
}

# Canonical 3-letter abbreviations (normalises 2-letter ESPN variants)
_ABBR_CANON: Dict[str, str] = {
    "NO": "NOP", "GS": "GSW", "BK": "BKN", "NY": "NYK",
    "SA": "SAS", "PHO": "PHX", "UT": "UTA", "WSH": "WAS",
}


def _canon_abbr(abbr: str) -> str:
    """Return the canonical 3-letter abbreviation for a team."""
    a = abbr.upper()
    return _ABBR_CANON.get(a, a)


# Reverse map: ESPN numeric team ID (string) → canonical abbreviation.
# Kept separate from TEAM_IDS so the canonical form is unambiguous even
# though TEAM_IDS contains duplicate values for 2-letter aliases.
_TEAM_ID_TO_ABBR: Dict[str, str] = {
    "1": "ATL", "2": "BOS",  "3": "NOP",  "4": "CHI",  "5": "CLE",
    "6": "DAL", "7": "DEN",  "8": "DET",  "9": "GSW",  "10": "HOU",
    "11": "IND","12": "LAC", "13": "LAL", "14": "MIA", "15": "MIL",
    "16": "MIN","17": "BKN", "18": "NYK", "19": "ORL", "20": "PHI",
    "21": "PHX","22": "POR", "23": "SAC", "24": "SAS", "25": "OKC",
    "26": "UTA","27": "WAS", "28": "TOR", "29": "MEM", "30": "CHA",
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

# ── Per-game stat sanity caps ─────────────────────────────────────────────────
# No NBA player has EVER averaged more than these values in a single season.
# Any parsed value above these thresholds is a season TOTAL, not a per-game
# average, and must be rejected to prevent "850 assists" style line inflation.
_PER_GAME_MAX: Dict[str, float] = {"pts": 55.0, "reb": 28.0, "ast": 17.0}


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
    """Spread juice: FanDuel runs -110/-110 on all NBA point spreads, regardless of size."""
    return -110, -110


# ── Opening line tracking (in-memory, never overwritten after first set) ──────

_opening_lines: Dict[str, Dict[str, float]] = {}


def record_opening_line(event_id: str, spread: float, total: float) -> None:
    """Record the first computed spread/total for an event. Never updates after set."""
    if event_id not in _opening_lines:
        _opening_lines[event_id] = {"spread": spread, "total": total}


def get_opening_line(event_id: str) -> Optional[Dict[str, float]]:
    """Return the opening spread/total dict if we have seen this event before."""
    return _opening_lines.get(event_id)


# ── Parlay odds combiner ───────────────────────────────────────────────────────

def calc_parlay_odds(prices: List[int]) -> int:
    """
    Convert a list of American odds into combined parlay odds.
    Each price is converted to a decimal multiplier, multiplied together,
    then converted back to American.

    Examples:
        [-110, -110]        → +264  (2-team parlay, standard juice)
        [-110, -110, -110]  → +596  (3-team parlay)
        [-150, +130, -110]  → approximately +350
    """
    if not prices:
        return -110
    if len(prices) == 1:
        return prices[0]
    decimal = 1.0
    for p in prices:
        if p >= 0:
            decimal *= (p / 100.0) + 1.0
        else:
            decimal *= (100.0 / abs(p)) + 1.0
    if decimal >= 2.0:
        return int(round((decimal - 1.0) * 100))
    return int(round(-100.0 / (decimal - 1.0)))


# ── Prop juice engine ─────────────────────────────────────────────────────────

def _prop_juice(tier: int, is_questionable: bool = False) -> Tuple[int, int]:
    """
    Return (over_price, under_price) for a player prop.

    Calibrated to FanDuel-style pricing:
    - Stars (tier 1): slight over lean (-115/-105) — public hammers star overs
    - Rotation (tier 2): mild over lean (-115/-105)
    - Bench (tier 3): neutral (-110/-110)
    - Questionable: favour the under (-108/-112) — limited minutes risk
    The under is NEVER priced at even money (+100); book always holds vig on both sides.
    """
    if is_questionable:
        if tier == 1:
            return (-108, -112)   # star questionable: injury limits minutes → under edge
        return (-105, -115)       # role player questionable: under is the sharper side
    if tier == 1:
        return (-115, -105)       # star: slight over lean, both sides properly juiced
    if tier == 2:
        return (-115, -105)       # rotation: same mild over lean as FanDuel standard
    return (-110, -110)           # bench: flat standard juice


# ── Public-action vig boost ───────────────────────────────────────────────────

def _public_vig_boost(pct_on_popular_side: float) -> int:
    """
    Extra juice (pts magnitude) charged to the popular side.
    When 65%+ of server money is on one side, the book shades the price.
    Returns a non-negative int to ADD to the popular side's juice magnitude.
    """
    if pct_on_popular_side >= 0.82:
        return 12
    if pct_on_popular_side >= 0.74:
        return 8
    if pct_on_popular_side >= 0.65:
        return 4
    return 0


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

    # Build a name-keyed pts lookup for this team's injured players.
    # We include any leader whose team_abbr matches OR whose team_abbr is blank
    # (ESPN frequently omits team_abbr from the leaders endpoint).
    # The injury list itself is already scoped to this team, so false positives
    # from players with the same name on another team are essentially impossible.
    team_pts: Dict[str, float] = {
        name.lower(): info["pts"]
        for name, info in stat_leaders.items()
        if info.get("team_abbr", "") in (abbr, "")
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

def _parse_pickcenter(pc: Dict) -> Optional[Dict]:
    """Parse an ESPN/DraftKings pickcenter object into our internal real_odds dict.

    ESPN spread sign convention: negative value = home team is favoured
      e.g. spread=-4.5 means home gives 4.5 pts (home favoured).
    Our spread sign convention: positive = home favoured.
    Therefore: our_spread = -(espn_spread).
    """
    try:
        espn_spread = pc.get("spread")
        total       = pc.get("overUnder")
        if espn_spread is None or total is None:
            return None

        home_obj = pc.get("homeTeamOdds") or {}
        away_obj = pc.get("awayTeamOdds") or {}

        our_spread = -float(espn_spread)   # flip sign: positive = home favoured

        home_ml = home_obj.get("moneyLine")
        away_ml = away_obj.get("moneyLine")

        h_spread_odds = home_obj.get("spreadOdds", -110)
        a_spread_odds = away_obj.get("spreadOdds", -110)

        over_odds  = pc.get("overOdds",  -110)
        under_odds = pc.get("underOdds", -110)

        # Opening lines from the structured pointSpread/moneyline sub-objects
        ps     = pc.get("pointSpread") or {}
        ml_obj = pc.get("moneyline") or {}

        open_h_spread_str = (ps.get("home") or {}).get("open", {}).get("line")   # e.g. "-3.5"
        open_h_ml_str     = (ml_obj.get("home") or {}).get("open", {}).get("odds")  # e.g. "-162"
        open_a_ml_str     = (ml_obj.get("away") or {}).get("open", {}).get("odds")  # e.g. "+136"

        opening_spread: Optional[float] = None
        if open_h_spread_str is not None:
            try:
                opening_spread = -float(str(open_h_spread_str))  # flip sign
            except (ValueError, TypeError):
                pass

        open_h_ml: Optional[int] = None
        open_a_ml: Optional[int] = None
        try:
            if open_h_ml_str is not None:
                open_h_ml = int(open_h_ml_str)
            if open_a_ml_str is not None:
                open_a_ml = int(open_a_ml_str)
        except (ValueError, TypeError):
            pass

        return {
            "spread":           our_spread,
            "total":            float(total),
            "home_ml":          int(home_ml)        if home_ml        is not None else None,
            "away_ml":          int(away_ml)        if away_ml        is not None else None,
            "home_spread_odds": int(h_spread_odds)  if h_spread_odds  is not None else -110,
            "away_spread_odds": int(a_spread_odds)  if a_spread_odds  is not None else -110,
            "over_odds":        int(over_odds)       if over_odds      is not None else -110,
            "under_odds":       int(under_odds)      if under_odds     is not None else -110,
            "opening_spread":   opening_spread,
            "open_home_ml":     open_h_ml,
            "open_away_ml":     open_a_ml,
        }
    except (TypeError, ValueError, AttributeError):
        return None


def generate_odds_for_game(
    game: Dict,
    injuries:       Optional[Dict[str, List[Dict]]] = None,
    stat_leaders:   Optional[Dict[str, Dict]]       = None,
    home_ts:        Optional[Dict]                  = None,
    away_ts:        Optional[Dict]                  = None,
    bet_dist:       Optional[Dict[str, float]]      = None,
    real_odds:      Optional[Dict]                  = None,
) -> Dict[str, Any]:
    """
    Produce h2h / spreads / totals.

    When ``real_odds`` is provided (parsed from ESPN's DraftKings pickcenter):
     - Real DK spread, total, moneylines, and vig are used directly as the base.
     - Only server-bet line movement is layered on top (our unique feature).
     - Injury notes are still shown for informational display.
     - Synthetic power-rating calculation is skipped entirely.

    When ``real_odds`` is None (synthetic fallback):
     - Full calculation: team ppg/papg, power ratings, B2B, injury adjustments.
     - Used when ESPN hasn't posted DK odds yet (pre-season, very early lines, etc.).
    """
    injuries     = injuries     or {}
    stat_leaders = stat_leaders or {}
    home_ts      = home_ts      or {}
    away_ts      = away_ts      or {}
    bet_dist     = bet_dist     or {}

    home_team = game["home_team"]
    away_team = game["away_team"]
    home_abbr = game.get("home_abbr", "")
    away_abbr = game.get("away_abbr", "")

    # ── Injury analysis (always run — needed for display notes) ───────────────
    h_inj_shift, h_notes = _injury_shift(home_abbr, injuries, stat_leaders)
    a_inj_shift, a_notes = _injury_shift(away_abbr, injuries, stat_leaders)
    injury_notes = h_notes + a_notes

    # B2B flags — for display in both paths
    h_back_to_back = home_ts.get("is_back_to_back", False)
    a_back_to_back = away_ts.get("is_back_to_back", False)

    spread_mv = total_mv = 0.0

    if real_odds:
        # ── REAL ODDS PATH (DraftKings lines via ESPN) ────────────────────────
        # DK already prices in injuries, B2B, power ratings, public action, etc.
        # We only layer our server-bet line movement feature on top.
        raw_spread = real_odds["spread"]   # positive = home favoured (our convention)
        base_total = real_odds["total"]

        spread_mv, total_mv = _line_movement(home_team, away_team, bet_dist)
        raw_spread += spread_mv
        base_total += total_mv

        spread = round(raw_spread * 2) / 2
        spread = max(-24.0, min(24.0, spread))
        total  = round(base_total * 2) / 2

        # Use real DK moneylines; derive from spread only if ESPN omits them
        h_ml = real_odds.get("home_ml")
        a_ml = real_odds.get("away_ml")
        if h_ml is None or a_ml is None:
            spread_abs     = abs(spread)
            fav_ml, dog_ml = _ml_from_spread(spread_abs)
            h_ml, a_ml     = (fav_ml, dog_ml) if spread >= 0 else (dog_ml, fav_ml)
            if spread_abs < 0.5:
                h_ml = a_ml = -110

        # Real DK spread vig (e.g. -102/-118 instead of flat -110/-110)
        h_spread_price = real_odds.get("home_spread_odds", -110) or -110
        a_spread_price = real_odds.get("away_spread_odds", -110) or -110

        # Real DK totals vig
        over_price  = real_odds.get("over_odds",  -110) or -110
        under_price = real_odds.get("under_odds", -110) or -110

        h_power = a_power = 0.5   # not computed in real-odds path

        # Opening line: seed from DK's real opening spread when available so
        # line-movement display is relative to the actual book open, not our
        # first computed value.
        real_open = real_odds.get("opening_spread")
        if real_open is not None and game["event_id"] not in _opening_lines:
            _opening_lines[game["event_id"]] = {
                "spread": real_open,
                "total":  real_odds["total"],
            }

        record_opening_line(game["event_id"], spread, total)
        opening        = get_opening_line(game["event_id"]) or {}
        opening_spread = opening.get("spread", spread)
        opening_total  = opening.get("total",  total)

        # Public-action vig boost on top of real ML
        h2h_money = bet_dist.get(home_team, 0.0) + bet_dist.get(away_team, 0.0)
        if h2h_money >= 50:
            home_pct = bet_dist.get(home_team, 0.0) / h2h_money
            away_pct = 1.0 - home_pct
            if home_pct >= 0.65:
                h_ml -= _public_vig_boost(home_pct)
            elif away_pct >= 0.65:
                a_ml -= _public_vig_boost(away_pct)

        # Totals public-action vig boost
        ou_money = bet_dist.get("Over", 0.0) + bet_dist.get("Under", 0.0)
        if ou_money >= 50:
            over_pct  = bet_dist.get("Over",  0.0) / ou_money
            under_pct = 1.0 - over_pct
            if over_pct >= 0.65:
                boost       = _public_vig_boost(over_pct)
                over_price  -= boost
                under_price  = min(under_price + boost - 2, -102)
            elif under_pct >= 0.65:
                boost       = _public_vig_boost(under_pct)
                under_price -= boost
                over_price   = min(over_price + boost - 2, -102)

        if abs(spread_mv) >= 0.5 or abs(total_mv) >= 0.5:
            injury_notes.append("📊 Line has moved due to betting action on this server.")

        return {
            "h2h": {home_team: h_ml, away_team: a_ml},
            "spreads": {
                home_team: {"price": h_spread_price, "point": -spread},
                away_team: {"price": a_spread_price, "point":  spread},
            },
            "totals": {
                "Over":  {"price": over_price,  "point": total},
                "Under": {"price": under_price, "point": total},
            },
            "injury_notes": injury_notes,
            "_meta": {
                "spread":           spread,
                "total":            total,
                "opening_spread":   opening_spread,
                "opening_total":    opening_total,
                "spread_move":      round(spread - opening_spread, 1),
                "total_move":       round(total  - opening_total,  1),
                "h_power":          0.5,
                "a_power":          0.5,
                "h_back_to_back":   h_back_to_back,
                "a_back_to_back":   a_back_to_back,
                "spread_moved":     spread_mv,
                "total_moved":      total_mv,
                "real_odds":        True,
            },
        }

    # ── SYNTHETIC FALLBACK PATH ───────────────────────────────────────────────
    # Used when ESPN hasn't posted DraftKings odds yet.

    # ── Parse records from game ───────────────────────────────────────────────
    hw,  hl    = _parse_record(game.get("home_record",        "0-0"))
    aw,  al    = _parse_record(game.get("away_record",        "0-0"))
    hh_w, hh_l = _parse_record(game.get("home_home_record",  "0-0"))
    ar_w, ar_l = _parse_record(game.get("away_road_record",  "0-0"))
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
        h_expected = (h_ppg + a_papg) / 2
        a_expected = (a_ppg + h_papg) / 2
        raw_spread = h_expected - a_expected + HOME_COURT_ADV
    else:
        raw_spread = (h_power - a_power) * 25 + HOME_COURT_ADV

    # ── Back-to-back penalty (-2.5 pts for team on B2B) ──────────────────────
    if h_back_to_back:
        raw_spread -= 2.5
    if a_back_to_back:
        raw_spread += 2.5

    # ── Injury line adjustment (synthetic only — real books do this already) ──
    raw_spread -= h_inj_shift
    raw_spread += a_inj_shift

    # ── Line movement ─────────────────────────────────────────────────────────
    spread_mv, total_mv = _line_movement(home_team, away_team, bet_dist)
    raw_spread += spread_mv

    # ── Round to nearest 0.5, clamp ──────────────────────────────────────────
    spread = round(raw_spread * 2) / 2
    spread = max(-24.0, min(24.0, spread))

    # ── Moneyline derived from spread ─────────────────────────────────────────
    spread_abs = abs(spread)
    fav_ml, dog_ml = _ml_from_spread(spread_abs)

    if spread >= 0:
        h_ml, a_ml = fav_ml, dog_ml
    else:
        h_ml, a_ml = dog_ml, fav_ml

    if spread_abs < 0.5:
        h_ml = a_ml = -110

    # ── Public action vig boost ───────────────────────────────────────────────
    h2h_money = bet_dist.get(home_team, 0.0) + bet_dist.get(away_team, 0.0)
    if h2h_money >= 50:
        home_pct = bet_dist.get(home_team, 0.0) / h2h_money
        away_pct = 1.0 - home_pct
        if home_pct >= 0.65:
            h_ml -= _public_vig_boost(home_pct)
        elif away_pct >= 0.65:
            a_ml -= _public_vig_boost(away_pct)

    # ── Total ─────────────────────────────────────────────────────────────────
    if h_ppg and h_papg and a_ppg and a_papg:
        h_expected = (h_ppg + a_papg) / 2
        a_expected = (a_ppg + h_papg) / 2
        base_total = h_expected + a_expected
    else:
        base_total = 225.0 + (h_power + a_power - 1.0) * 10

    if h_back_to_back:
        base_total -= 2.0
    if a_back_to_back:
        base_total -= 2.0

    base_total -= (h_inj_shift + a_inj_shift) * 2.5
    base_total += total_mv

    total = round(base_total * 2) / 2

    # ── Spread vig ────────────────────────────────────────────────────────────
    fav_price, dog_price = _spread_vig(spread_abs)
    if spread >= 0:
        h_spread_price, a_spread_price = fav_price, dog_price
    else:
        h_spread_price, a_spread_price = dog_price, fav_price

    # ── Totals juice (varies with public action) ──────────────────────────────
    over_price  = -110
    under_price = -110
    ou_money = bet_dist.get("Over", 0.0) + bet_dist.get("Under", 0.0)
    if ou_money >= 50:
        over_pct  = bet_dist.get("Over",  0.0) / ou_money
        under_pct = 1.0 - over_pct
        if over_pct >= 0.65:
            boost       = _public_vig_boost(over_pct)
            over_price  -= boost
            under_price  = min(under_price + boost - 2, -102)
        elif under_pct >= 0.65:
            boost       = _public_vig_boost(under_pct)
            under_price -= boost
            over_price   = min(over_price + boost - 2, -102)

    # ── Record opening line & compute movement ────────────────────────────────
    record_opening_line(game["event_id"], spread, total)
    opening        = get_opening_line(game["event_id"]) or {}
    opening_spread = opening.get("spread", spread)
    opening_total  = opening.get("total",  total)

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
            "Over":  {"price": over_price,  "point": total},
            "Under": {"price": under_price, "point": total},
        },
        "injury_notes": injury_notes,
        "_meta": {
            "spread":           spread,
            "total":            total,
            "opening_spread":   opening_spread,
            "opening_total":    opening_total,
            "spread_move":      round(spread - opening_spread, 1),
            "total_move":       round(total  - opening_total,  1),
            "h_power":          round(h_power, 3),
            "a_power":          round(a_power, 3),
            "h_back_to_back":   h_back_to_back,
            "a_back_to_back":   a_back_to_back,
            "spread_moved":     spread_mv,
            "total_moved":      total_mv,
            "real_odds":        False,
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# Player props
# ══════════════════════════════════════════════════════════════════════════════

def generate_player_props_for_game(
    game: Dict,
    props_pool: Dict[str, Dict],
    questionable_players: Optional[Set[str]] = None,
    injury_map: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Build player prop over/under lines for every available player.

    props_pool keys: {player_name: {pts, reb, ast, pra, tier, team_abbr}}
    injury_map keys: {player_name_lower: status_lower}

    Line logic (FanDuel-accurate):
    - Lines are set AT the player's actual season/recent average, rounded to the
      nearest 0.5. No artificial discounts or floors — this mirrors how FanDuel
      prices every player from stars to deep bench.
    - Health/quality adjustments are applied BEFORE rounding: a doubtful player's
      line is reduced proportionally to their reduced expected output. This is how
      real books handle it — the LINE moves, not just the juice.
    - Players with ALL zero stats are skipped — they have no ESPN data and
      creating fake lines would make one side near-guaranteed.
    - OUT players are skipped entirely — no point offering props for DNPs.
    - A stat is only offered if its line is >= 0.5 (i.e., the player actually
      averages enough of that stat to make betting meaningful).
    - Juice is calibrated to FanDuel norms per tier and injury status.
    """
    props: Dict[str, Any] = {}
    home_abbr = game.get("home_abbr", "")
    away_abbr = game.get("away_abbr", "")
    _imap     = {k.lower(): v for k, v in (injury_map or {}).items()}

    # Health factors: how much of their normal output to expect on game night.
    # doubtful      → ~78% output (limited minutes, managed load)
    # questionable/
    #   day-to-day  → ~88% output (likely plays but not 100%)
    # healthy       → 100%
    # out           → skip (DNP; line would be meaningless)
    _HEALTH_FACTOR = {
        "doubtful":    0.78,
        "questionable":0.88,
        "day-to-day":  0.88,
        "dtd":         0.88,
    }

    def _line(val: float) -> float:
        """Round to nearest 0.5 — FanDuel sets lines at the player's actual average."""
        return round(val * 2) / 2

    for pname, pdata in props_pool.items():
        if pdata.get("team_abbr", "") not in (home_abbr, away_abbr):
            continue

        pts  = float(pdata.get("pts", 0.0))
        reb  = float(pdata.get("reb", 0.0))
        ast  = float(pdata.get("ast", 0.0))

        # ── Final sanity gate (last line of defence against data bugs) ────────
        # If any stat still exceeds a realistic per-game maximum after all the
        # upstream fixes, clamp it hard rather than generating a nonsense line.
        # These caps (55 PPG / 28 RPG / 17 APG) are above every NBA record, so
        # a real superstar's line is NEVER touched; only corrupted data is caught.
        pts = min(pts, _PER_GAME_MAX["pts"])
        reb = min(reb, _PER_GAME_MAX["reb"])
        ast = min(ast, _PER_GAME_MAX["ast"])

        tier = _player_tier(pts)

        # Skip players with no statistical data at all — they are two-way /
        # G-League call-ups or players ESPN has no averages for.  Generating
        # fake lines for them creates near-guaranteed winners and is the main
        # source of the "100% win" bug.
        if pts == 0.0 and reb == 0.0 and ast == 0.0:
            continue

        # ── Health / injury status ────────────────────────────────────────────
        inj_status = _imap.get(pname.lower(), "active")

        # OUT players will definitely not play — skip them entirely.
        if inj_status == "out":
            continue

        # Apply line reduction factor based on health.  This moves the actual
        # LINE down (not just the juice) when a player is compromised.
        line_factor = _HEALTH_FACTOR.get(inj_status, 1.0)
        if line_factor < 1.0:
            pts = round(pts * line_factor, 1)
            reb = round(reb * line_factor, 1)
            ast = round(ast * line_factor, 1)

        pra  = pts + reb + ast

        is_questionable = pname in (questionable_players or set())

        # ── Compute lines at actual average (FanDuel style) ───────────────────
        pts_line = _line(pts)
        reb_line = _line(reb)
        ast_line = _line(ast)
        pra_line = _line(pra)

        # ── FanDuel-calibrated per-stat juice ─────────────────────────────────
        # Points: public hammers overs — slight over premium for stars & rotation
        pts_over_p, pts_under_p = _prop_juice(tier, is_questionable)

        # Rebounds: neutral market — FanDuel standard -110/-110 for all tiers
        if is_questionable:
            reb_over_p, reb_under_p = (-105, -115)
        else:
            reb_over_p, reb_under_p = (-110, -110)

        # Assists: neutral; -110/-110 across the board (lowest public interest)
        if is_questionable:
            ast_over_p, ast_under_p = (-105, -115)
        else:
            ast_over_p, ast_under_p = (-110, -110)

        # PRA: combined stat — slight over lean for stars/rotation
        if is_questionable:
            pra_over_p, pra_under_p = (-108, -112)
        elif tier in (1, 2):
            pra_over_p, pra_under_p = (-115, -105)
        else:
            pra_over_p, pra_under_p = (-110, -110)

        # ── Build the prop entry — only include stats with a playable line ─────
        # A line of 0.0 or 0.5 on a minor stat means the player essentially never
        # records it; skip those to avoid near-guaranteed wins in one direction.
        entry: Dict[str, Any] = {
            "team_abbr": pdata.get("team_abbr", ""),
            "tier":      tier,
            "status":    inj_status if inj_status != "active" else "active",
        }

        if pts_line >= 0.5:
            entry["pts"]       = pts_line
            entry["pts_over"]  = pts_over_p
            entry["pts_under"] = pts_under_p

        if reb_line >= 0.5:
            entry["reb"]       = reb_line
            entry["reb_over"]  = reb_over_p
            entry["reb_under"] = reb_under_p

        if ast_line >= 0.5:
            entry["ast"]       = ast_line
            entry["ast_over"]  = ast_over_p
            entry["ast_under"] = ast_under_p

        # PRA only offered when all three components are meaningful
        if pra_line >= 2.5 and pts_line >= 0.5 and reb_line >= 0.5:
            entry["pra"]       = pra_line
            entry["pra_over"]  = pra_over_p
            entry["pra_under"] = pra_under_p

        # Only add the player if at least one stat line is available
        if any(k in entry for k in ("pts", "reb", "ast", "pra")):
            props[pname] = entry

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

        home_abbr_raw = _canon_abbr(home["team"].get("abbreviation", "").upper())
        away_abbr_raw = _canon_abbr(away["team"].get("abbreviation", "").upper())

        # Team logos — use ESPN's own CDN URL from the response when available,
        # falling back to the standard abbreviated path which is always valid.
        def _team_logo(team_block: Dict, abbr: str) -> str:
            url = team_block["team"].get("logo") or ""
            if url and url.startswith("http"):
                return url
            return f"https://a.espncdn.com/i/teamlogos/nba/500/{abbr.lower()}.png"

        return {
            "event_id":            event["id"],
            "name":                event.get("name", ""),
            "short_name":          event.get("shortName", ""),
            "commence_time":       event.get("date", ""),
            "home_team":           home["team"]["displayName"],
            "away_team":           away["team"]["displayName"],
            "home_abbr":           home_abbr_raw,
            "away_abbr":           away_abbr_raw,
            "home_logo":           _team_logo(home, home_abbr_raw),
            "away_logo":           _team_logo(away, away_abbr_raw),
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

        # Per-team roster cache: {abbr: {player_name: status_str}}
        self._team_roster_cache: Dict[str, Dict] = {}
        self._team_roster_ts:    Dict[str, float] = {}

        # Per-team player pool (leaders + roster stats): {abbr: {player_name: {pts,...}}}
        self._team_player_pool_cache: Dict[str, Dict] = {}
        self._team_player_pool_ts:    Dict[str, float] = {}

        # Per-game summary roster cache: {event_id: {player_name: {pts,reb,ast,pra,team_abbr,available}}}
        self._summary_roster_cache: Dict[str, Dict] = {}
        self._summary_roster_ts:    Dict[str, float] = {}

        # Set of team abbrs that played yesterday (for B2B detection)
        self._played_yesterday: Set[str] = set()
        self._played_yesterday_ts: float = 0.0

        # Recent completed games list (shared across teams, 1-hr TTL)
        self._recent_completed_cache: List[Dict] = []
        self._recent_completed_ts: float = 0.0

        # Per-team last-5-game player averages: {abbr: {player_name: {pts,reb,ast}}}
        self._last5_cache: Dict[str, Dict] = {}
        self._last5_ts:    Dict[str, float] = {}

        # Completed game box scores (never expire — completed game stats don't change)
        self._boxscore_cache: Dict[str, Dict] = {}

        # Per-game DraftKings pickcenter (real game odds from ESPN): {event_id: parsed_dict}
        self._pickcenter_cache: Dict[str, Dict] = {}
        self._pickcenter_ts:    Dict[str, float] = {}

        # Per-game DraftKings player props (real prop lines from ESPN propBets endpoint)
        self._props_dk_cache: Dict[str, Dict] = {}
        self._props_dk_ts:    Dict[str, float] = {}

        # Season-long ESPN athlete ID → display name (never expires within a session)
        self._athlete_cache: Dict[str, str] = {}

    # ── Session ───────────────────────────────────────────────────────────────

    async def _get_pickcenter(self, event_id: str) -> Optional[Dict]:
        """Fetch real DraftKings odds from ESPN game summary's pickcenter section.

        Uses a 2-minute TTL so lines stay fresh during active betting windows.
        Returns a parsed real_odds dict (same shape as _parse_pickcenter output)
        or None if the game hasn't had lines posted yet.
        """
        now = time.monotonic()
        cached_ts = self._pickcenter_ts.get(event_id, 0.0)
        if event_id in self._pickcenter_cache and now - cached_ts < GAMES_TTL:
            return self._pickcenter_cache[event_id]

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

            pc_list = data.get("pickcenter") or []
            if not pc_list:
                return None

            # Prefer DraftKings provider; fall back to first available
            pc: Optional[Dict] = None
            for p in pc_list:
                pname = (p.get("provider", {}).get("name") or "").lower()
                if "draft" in pname or pc is None:
                    pc = p
                    if "draft" in pname:
                        break

            if not pc:
                return None

            result = _parse_pickcenter(pc)
            if result:
                self._pickcenter_cache[event_id] = result
                self._pickcenter_ts[event_id]    = now
            return result
        except Exception:
            return None

    async def _get_player_props_dk(self, event_id: str) -> Optional[Dict[str, Dict]]:
        """Fetch real DraftKings player prop lines from ESPN's propBets endpoint.

        Returns {player_name: {pts, pts_over, pts_under, reb, reb_over, reb_under,
                               ast, ast_over, ast_under, pra, pra_over, pra_under}}
        or None when the endpoint is unavailable.

        team_abbr, tier, and status are injected by get_game_with_odds using the
        roster and injury data already fetched in that call.
        """
        now = time.monotonic()
        if (
            event_id in self._props_dk_cache
            and now - self._props_dk_ts.get(event_id, 0.0) < GAMES_TTL
        ):
            return self._props_dk_cache[event_id]

        session = await self._get_session()
        try:
            url = ESPN_PROPS_BASE.format(eid=event_id)
            async with session.get(
                url,
                params={"lang": "en", "region": "us", "limit": 600},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)

            items: List[Dict] = data.get("items") or []
            if not items:
                return None

            # ── Collect unique athlete $ref URLs ──────────────────────────────
            athlete_refs: Dict[str, str] = {}   # aid → base URL (no query string)
            for item in items:
                ref = (item.get("athlete") or {}).get("$ref", "")
                m = _AID_RE.search(ref)
                if m:
                    aid = m.group(1)
                    if aid not in athlete_refs:
                        athlete_refs[aid] = ref.split("?")[0]

            # ── Resolve uncached athlete IDs → display names in parallel ──────
            uncached = [aid for aid in athlete_refs if aid not in self._athlete_cache]
            if uncached:
                async def _fetch_name(aid: str, ref_url: str) -> None:
                    try:
                        async with session.get(
                            ref_url,
                            params={"lang": "en", "region": "us"},
                            timeout=aiohttp.ClientTimeout(total=8),
                        ) as r:
                            if r.status == 200:
                                ad = await r.json(content_type=None)
                                name = (
                                    ad.get("displayName")
                                    or ad.get("fullName")
                                    or ad.get("shortName")
                                    or ""
                                )
                                if name:
                                    self._athlete_cache[aid] = name
                    except Exception:
                        pass

                await asyncio.gather(
                    *[_fetch_name(a, athlete_refs[a]) for a in uncached]
                )

            # ── Build name → ESPN athlete ID map (for headshot URLs) ─────────
            # Only include athletes that actually appear in this event's prop items.
            name_to_aid: Dict[str, str] = {
                self._athlete_cache[aid]: aid
                for aid in athlete_refs
                if aid in self._athlete_cache
            }

            # ── Group items by (player_name, stat_key) ────────────────────────
            # ESPN returns items in order: for each (athlete, type) pair there are
            # exactly 2 entries — first is the OVER, second is the UNDER.
            grouped: Dict[str, Dict[str, List[Dict]]] = {}
            for item in items:
                ref = (item.get("athlete") or {}).get("$ref", "")
                m = _AID_RE.search(ref)
                if not m:
                    continue
                name = self._athlete_cache.get(m.group(1))
                if not name:
                    continue
                type_name = (item.get("type") or {}).get("name", "")
                stat_key  = _PROP_TYPE_MAP.get(type_name)
                if not stat_key:
                    continue
                grouped.setdefault(name, {}).setdefault(stat_key, []).append(item)

            # ── Build prop entries ─────────────────────────────────────────────
            def _parse_dk_odds(item: Dict) -> int:
                raw = (item.get("odds") or {}).get("american", {}).get("value", "-110")
                try:
                    return int(str(raw).replace("+", ""))
                except (ValueError, TypeError):
                    return -110

            props: Dict[str, Dict] = {}
            for player_name, stat_map in grouped.items():  # noqa: E501
                entry: Dict[str, Any] = {}
                for stat_key, sitems in stat_map.items():
                    if not sitems:
                        continue
                    over_item  = sitems[0]
                    under_item = sitems[1] if len(sitems) > 1 else sitems[0]

                    # Line from the current target; fall back to odds.total field
                    line_raw = (
                        (over_item.get("current") or {}).get("target", {}).get("value")
                        or (over_item.get("odds")   or {}).get("total",  {}).get("value")
                    )
                    if line_raw is None:
                        continue
                    line = float(line_raw)
                    if line < 0.5:
                        continue

                    entry[stat_key]            = line
                    entry[f"{stat_key}_over"]  = _parse_dk_odds(over_item)
                    entry[f"{stat_key}_under"] = _parse_dk_odds(under_item)

                if any(k in entry for k in _PROP_TYPE_MAP.values()):
                    # Store ESPN athlete ID so callers can build headshot URLs:
                    # https://a.espncdn.com/i/headshots/nba/players/full/{athlete_id}.png
                    entry["athlete_id"] = name_to_aid.get(player_name, "")
                    props[player_name] = entry

            if props:
                self._props_dk_cache[event_id] = props
                self._props_dk_ts[event_id]    = now
            return props or None
        except Exception:
            return None

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

    # ── Per-team roster (availability) ───────────────────────────────────────

    async def get_team_roster(self, abbr: str) -> Dict[str, str]:
        """
        Fetch the full active roster for a team from ESPN.
        Returns {player_name: status} where status is lowercase e.g. "active", "out",
        "questionable", "doubtful", "day-to-day", "inactive".
        Used to know every player on the team and filter unavailable ones.
        """
        now = time.monotonic()
        if (
            abbr in self._team_roster_cache
            and now - self._team_roster_ts.get(abbr, 0) < LEADERS_TTL
        ):
            return self._team_roster_cache[abbr]

        team_id = TEAM_IDS.get(abbr)
        if not team_id:
            return {}

        session  = await self._get_session()
        result: Dict[str, str] = {}

        try:
            url = ESPN_TEAM_ROSTER.format(team_id=team_id)
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return {}
                data = await resp.json(content_type=None)

            # ESPN roster: top-level "athletes" can be:
            #   (a) flat list of athlete dicts, OR
            #   (b) list of position-group dicts each with "items" list
            raw_athletes: List[Dict] = []
            for item in data.get("athletes", []):
                if "items" in item:
                    raw_athletes.extend(item["items"])
                elif "displayName" in item or "fullName" in item:
                    raw_athletes.append(item)

            for athlete in raw_athletes:
                pname = athlete.get("displayName") or athlete.get("fullName", "")
                if not pname:
                    continue

                # Determine availability status
                # injuries is a list; if empty or first entry is "Active" → active
                injuries = athlete.get("injuries", [])
                if not injuries:
                    status = "active"
                else:
                    raw_status = (injuries[0].get("status", "") or "").lower()
                    # Normalise ESPN status strings
                    if raw_status in ("", "active"):
                        status = "active"
                    elif "out" in raw_status:
                        status = "out"
                    elif "questionable" in raw_status:
                        status = "questionable"
                    elif "doubtful" in raw_status:
                        status = "doubtful"
                    elif "day" in raw_status:
                        status = "day-to-day"
                    elif "inactive" in raw_status or "suspension" in raw_status:
                        status = "inactive"
                    else:
                        status = "active"

                result[pname] = status

        except Exception:
            pass

        if result:
            self._team_roster_cache[abbr] = result
            self._team_roster_ts[abbr]    = now
        return result

    # ── Per-game summary roster (player stats from ESPN pre-game data) ─────────

    async def _parse_summary_roster(
        self, event_id: str, home_abbr: str, away_abbr: str
    ) -> Dict[str, Dict]:
        """
        Parse the ESPN game summary's 'rosters' section.
        Returns {player_name: {pts, reb, ast, pra, tier, team_abbr, available}}.
        ESPN pre-game summaries include every expected player with season averages
        and their game-day availability status.
        Falls back to empty dict if the section is missing or the call fails.
        """
        now = time.monotonic()
        if (
            event_id in self._summary_roster_cache
            and now - self._summary_roster_ts.get(event_id, 0) < LEADERS_TTL
        ):
            return self._summary_roster_cache[event_id]

        session = await self._get_session()
        result: Dict[str, Dict] = {}
        valid_abbrs = {home_abbr, away_abbr}
        # Use dedicated canonical ID→abbr map (not reversed from TEAM_IDS which has
        # duplicate values from 2-letter aliases).
        _id_to_abbr: Dict[str, str] = _TEAM_ID_TO_ABBR

        # ESPN stat name → our internal key
        stat_name_map: Dict[str, str] = {
            # ESPN category names (actual "name" field values)
            "scoring":      "pts",
            "rebounding":   "reb",
            "assists":      "ast",
            # Standard per-game names
            "avgpoints":    "pts", "points":    "pts", "pointspergame":    "pts",
            "avgrebounds":  "reb", "rebounds":  "reb", "reboundspergame":  "reb",
            "avgassists":   "ast", "assistspergame":   "ast",
            # Short abbreviations
            "ppg": "pts", "rpg": "reb", "apg": "ast",
            "pts": "pts", "reb": "reb", "ast": "ast",
        }

        def _extract_stats(athlete: Dict) -> Dict[str, float]:
            """Walk every statistics tree shape ESPN uses."""
            out: Dict[str, float] = {"pts": 0.0, "reb": 0.0, "ast": 0.0}

            def _apply(name: str, value) -> None:
                sname = name.lower().replace(" ", "").replace("_", "")
                skey  = stat_name_map.get(sname)
                if skey and value is not None:
                    try:
                        v = float(value)
                        # Reject season totals masquerading as per-game averages.
                        # No player averages 55+ PPG, 28+ RPG, or 17+ APG per game.
                        if v > _PER_GAME_MAX.get(skey, 9999.0):
                            return
                        # Only keep the highest VALID per-game value seen across
                        # multiple ESPN stat shapes for the same player.
                        if v > out.get(skey, 0.0):
                            out[skey] = v
                    except (TypeError, ValueError):
                        pass

            stats_obj = athlete.get("statistics") or {}

            # Shape A: statistics.splits.categories[].stats[]
            splits     = stats_obj.get("splits") or {}
            categories = splits.get("categories") or []
            for cat in categories:
                for s in cat.get("stats") or []:
                    _apply(s.get("name") or "", s.get("value"))

            # Shape B: statistics.categories[].stats[] (no "splits" wrapper)
            for cat in stats_obj.get("categories") or []:
                for s in cat.get("stats") or []:
                    _apply(s.get("name") or "", s.get("value"))

            # Shape C: flat statistics.stats[] list
            for s in stats_obj.get("stats") or []:
                _apply(s.get("name") or "", s.get("value"))

            # Shape D: athlete has top-level avgPoints / avgRebounds / avgAssists
            for raw_name in ("avgPoints", "avgRebounds", "avgAssists", "avgPointsPerGame",
                             "points", "rebounds", "assists", "ppg", "rpg", "apg"):
                val = athlete.get(raw_name)
                if val is not None:
                    _apply(raw_name, val)

            return out

        def _idx_for(labels: List[str], candidates: List[str]) -> int:
            """Return first matching column index from a labels list, or -1."""
            for c in candidates:
                try:
                    return labels.index(c)
                except ValueError:
                    pass
            return -1

        def _stat_from_row(row: List[str], idx: int) -> float:
            """Extract a float from a stats row at index idx.
            Handles fractions like '7-18' (takes the first part) and plain ints/floats."""
            if idx < 0 or idx >= len(row):
                return 0.0
            raw = str(row[idx]).split("-")[0].split("/")[0].strip()
            try:
                return float(raw)
            except (TypeError, ValueError):
                return 0.0

        try:
            async with session.get(
                ESPN_SUMMARY,
                params={"event": event_id},
                timeout=aiohttp.ClientTimeout(total=12),
            ) as resp:
                if resp.status != 200:
                    return {}
                data = await resp.json(content_type=None)

            # ── Primary: ESPN boxscore.players (live/completed games) ──────────
            # Structure: boxscore.players[i].team.abbreviation
            #            boxscore.players[i].statistics[0].labels  → column names
            #            boxscore.players[i].statistics[0].athletes[j].athlete.displayName
            #            boxscore.players[i].statistics[0].athletes[j].stats  → list of strings
            boxscore   = data.get("boxscore") or {}
            bp_entries = boxscore.get("players") or []
            for team_block in bp_entries:
                t_obj     = team_block.get("team") or {}
                team_abbr = _canon_abbr(
                    (t_obj.get("abbreviation") or t_obj.get("abbrev") or "").upper()
                )
                if team_abbr not in valid_abbrs:
                    team_id_str = str(t_obj.get("id", ""))
                    team_abbr   = _id_to_abbr.get(team_id_str, team_abbr)
                if team_abbr not in valid_abbrs:
                    continue

                for stats_group in team_block.get("statistics") or []:
                    raw_labels = stats_group.get("labels") or stats_group.get("names") or []
                    labels     = [str(l).upper() for l in raw_labels]

                    pts_idx = _idx_for(labels, ["PTS", "POINTS"])
                    reb_idx = _idx_for(labels, ["REB", "REBOUNDS", "DREB"])
                    ast_idx = _idx_for(labels, ["AST", "ASSISTS"])

                    for athlete_entry in stats_group.get("athletes") or []:
                        athlete      = athlete_entry.get("athlete") or {}
                        pname        = athlete.get("displayName") or athlete.get("fullName", "")
                        if not pname:
                            continue
                        did_not_play = athlete_entry.get("didNotPlay", False)
                        active       = athlete_entry.get("active", True)
                        available    = active and not did_not_play

                        raw_stats = athlete_entry.get("stats") or []
                        pts = min(_stat_from_row(raw_stats, pts_idx), _PER_GAME_MAX["pts"])
                        reb = min(_stat_from_row(raw_stats, reb_idx), _PER_GAME_MAX["reb"])
                        ast = min(_stat_from_row(raw_stats, ast_idx), _PER_GAME_MAX["ast"])
                        pra = pts + reb + ast
                        tier = _player_tier(pts)

                        if pname not in result or (pts + reb + ast) > (
                            result[pname]["pts"] + result[pname]["reb"] + result[pname]["ast"]
                        ):
                            result[pname] = {
                                "pts":       pts,
                                "reb":       reb,
                                "ast":       ast,
                                "pra":       pra,
                                "tier":      tier,
                                "team_abbr": team_abbr,
                                "available": available,
                            }

            # ── Fallback: legacy ESPN "rosters" structure (pre-game summaries) ──
            # Some game previews expose per-player season averages here.
            for team_block in data.get("rosters") or []:
                t_obj     = team_block.get("team") or {}
                team_abbr = _canon_abbr(
                    (t_obj.get("abbreviation") or t_obj.get("abbrev") or "").upper()
                )
                if team_abbr not in valid_abbrs:
                    team_id_str = str(t_obj.get("id", ""))
                    team_abbr   = _id_to_abbr.get(team_id_str, team_abbr)
                if team_abbr not in valid_abbrs:
                    continue

                for entry in team_block.get("roster") or []:
                    athlete = entry.get("athlete") or {}
                    pname   = athlete.get("displayName") or athlete.get("fullName", "")
                    if not pname or pname in result:
                        continue

                    did_not_play = entry.get("didNotPlay", False)
                    status_name  = (
                        (entry.get("status") or {}).get("type", {}).get("name", "")
                    ).lower()
                    available = (
                        not did_not_play
                        and status_name not in ("inactive", "out", "suspended")
                    )

                    stats = _extract_stats(athlete)
                    pts, reb, ast = stats["pts"], stats["reb"], stats["ast"]
                    pra  = pts + reb + ast
                    tier = _player_tier(pts)

                    result[pname] = {
                        "pts":       pts,
                        "reb":       reb,
                        "ast":       ast,
                        "pra":       pra,
                        "tier":      tier,
                        "team_abbr": team_abbr,
                        "available": available,
                    }

        except Exception:
            pass

        if result:
            self._summary_roster_cache[event_id] = result
            self._summary_roster_ts[event_id]    = now
        return result

    # ── Per-team player pool (leaders + roster) ───────────────────────────────

    async def get_team_player_pool(self, abbr: str) -> Dict[str, Dict]:
        """
        Return {player_name: {pts, reb, ast, pra, tier, team_abbr}} for every
        player on the team, by combining two ESPN sources:

        1. ESPN_TEAM_LEADERS — top stat leaders already scoped to this team,
           so team attribution is guaranteed (no abbr-guessing needed).
        2. ESPN_TEAM_ROSTER  — full player list; stats extracted from the
           nested `statistics` object when ESPN includes them.

        Cached per team for 6 hours (same TTL as team stats).
        """
        now = time.monotonic()
        if (
            abbr in self._team_player_pool_cache
            and now - self._team_player_pool_ts.get(abbr, 0) < TEAM_STATS_TTL
        ):
            return self._team_player_pool_cache[abbr]

        team_id = TEAM_IDS.get(abbr)
        if not team_id:
            return {}

        session = await self._get_session()

        _stat_key_map: Dict[str, str] = {
            # ESPN team leaders category names (what the "name" field actually returns)
            "scoring":         "pts",   # ESPN uses "Scoring" as the category name
            "rebounding":      "reb",   # ESPN uses "Rebounding"
            "assists":         "ast",   # ESPN uses "Assists"
            # Standard per-game stat names
            "pointspergame":   "pts", "avgpoints":   "pts", "points":   "pts",
            "reboundspergame": "reb", "avgrebounds": "reb", "rebounds": "reb",
            "assistspergame":  "ast", "avgassists":  "ast",
            # Short abbreviations ESPN uses in the "abbreviation" field
            "ppg": "pts", "rpg": "reb", "apg": "ast",
            "pts": "pts", "reb": "reb", "ast": "ast",
        }

        player_stats: Dict[str, Dict] = {}

        def _update(pname: str, key: str, val: float) -> None:
            if pname not in player_stats:
                player_stats[pname] = {"pts": 0.0, "reb": 0.0, "ast": 0.0, "team_abbr": abbr}
            # Hard-reject season totals: no player averages 55+ PPG / 28+ RPG / 17+ APG.
            if val > _PER_GAME_MAX.get(key, 9999.0):
                return
            if val > player_stats[pname].get(key, 0.0):
                player_stats[pname][key] = val

        def _resolve_cat(cat: Dict) -> Optional[str]:
            """Try category name first, then abbreviation, to handle ESPN's varying schemas."""
            for field in ("name", "abbreviation", "displayName"):
                raw = (cat.get(field) or "").lower().replace(" ", "").replace("_", "")
                if raw and raw in _stat_key_map:
                    return _stat_key_map[raw]
            return None

        # ── Source 1: team leaders (top scorers/rebounders/assisters for this team) ──
        try:
            url = ESPN_TEAM_LEADERS.format(team_id=team_id)
            async with session.get(
                url,
                params={"limit": 50},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    # ESPN wraps leaders under "leaders" or "categories"
                    leaders_data = data.get("leaders") or data.get("categories") or []
                    for cat in leaders_data:
                        stat_key = _resolve_cat(cat)
                        if not stat_key:
                            continue
                        # Entries can be under "leaders" or "athletes"
                        entries = cat.get("leaders") or cat.get("athletes") or []
                        for entry in entries:
                            # Athlete nested under "athlete" key OR entry is the athlete
                            athlete = entry.get("athlete") or entry
                            pname   = (
                                athlete.get("displayName")
                                or athlete.get("fullName")
                                or entry.get("displayName")
                                or entry.get("fullName", "")
                            )
                            if not pname:
                                continue
                            val_raw = (
                                entry.get("value")
                                or entry.get("average")
                                or entry.get("perGameValue")
                            )
                            try:
                                _update(pname, stat_key, float(val_raw or 0))
                            except (TypeError, ValueError):
                                pass
        except Exception:
            pass

        # ── Source 2: team roster (full list; request stats alongside the roster) ──
        try:
            url = ESPN_TEAM_ROSTER.format(team_id=team_id)
            async with session.get(
                url,
                params={"enable": "stats", "seasontype": "2"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json(content_type=None) if resp.status == 200 else {}

            raw_athletes: List[Dict] = []
            for item in data.get("athletes", []):
                if "items" in item:
                    raw_athletes.extend(item["items"])
                elif "displayName" in item or "fullName" in item:
                    raw_athletes.append(item)

            for athlete in raw_athletes:
                pname = athlete.get("displayName") or athlete.get("fullName", "")
                if not pname:
                    continue
                # Ensure the player appears even with zero stats
                if pname not in player_stats:
                    player_stats[pname] = {"pts": 0.0, "reb": 0.0, "ast": 0.0, "team_abbr": abbr}

                def _try_stat(raw_name: str, raw_val) -> None:
                    sname = raw_name.lower().replace(" ", "").replace("_", "")
                    sk    = _stat_key_map.get(sname)
                    if sk and raw_val is not None:
                        try:
                            _update(pname, sk, float(raw_val))
                        except (TypeError, ValueError):
                            pass

                stats_obj = athlete.get("statistics") or {}
                # Shape A: statistics.splits.categories[].stats[]
                splits = stats_obj.get("splits") or {}
                for cat in splits.get("categories") or []:
                    for s in cat.get("stats") or []:
                        _try_stat(s.get("name") or "", s.get("value"))
                # Shape B: statistics.categories[].stats[]
                for cat in stats_obj.get("categories") or []:
                    for s in cat.get("stats") or []:
                        _try_stat(s.get("name") or "", s.get("value"))
                # Shape C: flat statistics.stats[]
                for s in stats_obj.get("stats") or []:
                    _try_stat(s.get("name") or "", s.get("value"))
                # Shape D: top-level athlete keys
                for raw_name in ("avgPoints", "avgRebounds", "avgAssists",
                                 "points", "rebounds", "assists", "ppg", "rpg", "apg"):
                    if athlete.get(raw_name) is not None:
                        _try_stat(raw_name, athlete[raw_name])
        except Exception:
            pass

        # Compute pra + tier for everything collected
        result: Dict[str, Dict] = {}
        for pname, d in player_stats.items():
            d["pra"]  = d["pts"] + d["reb"] + d["ast"]
            d["tier"] = _player_tier(d["pts"])
            result[pname] = d

        if result:
            self._team_player_pool_cache[abbr] = result
            self._team_player_pool_ts[abbr]    = now
        return result

    # ── Season stat leaders ───────────────────────────────────────────────────

    async def get_stat_leaders(self, force: bool = False) -> Dict[str, Dict]:
        """
        Fetch season stat leaders from ESPN with a high limit (500).
        Tries multiple paths to extract team abbreviation from each athlete entry.
        """
        now = time.monotonic()
        if not force and self._leaders_cache and now - self._leaders_ts < LEADERS_TTL:
            return self._leaders_cache

        session = await self._get_session()
        merged: Dict[str, Dict] = {}

        # ESPN uses different category names depending on endpoint version
        category_key_map = {
            # Actual display names ESPN uses (lowercased)
            "scoring":         "pts",
            "rebounding":      "reb",
            "assists":         "ast",
            # Standard names
            "pointspergame":   "pts",
            "reboundspergame": "reb",
            "assistspergame":  "ast",
            "points":          "pts",
            "rebounds":        "reb",
            # Short abbreviations
            "ppg":             "pts",
            "rpg":             "reb",
            "apg":             "ast",
            "pts":             "pts",
            "reb":             "reb",
            "ast":             "ast",
        }

        def _abbr_from_athlete(athlete: Dict) -> str:
            """Try every known path ESPN uses to store team abbreviation."""
            checks = [
                lambda a: a.get("team", {}).get("abbreviation", ""),
                lambda a: a.get("teamAbbrev", ""),
                lambda a: a.get("team", {}).get("abbrev", ""),
                lambda a: (a.get("team") or {}).get("shortDisplayName", ""),
                lambda a: a.get("teamShortName", ""),
                lambda a: _TEAM_ID_TO_ABBR.get(str((a.get("team") or {}).get("id", "")), ""),
            ]
            for fn in checks:
                try:
                    v = fn(athlete)
                    if v and len(v) <= 4:
                        return _canon_abbr(v.upper())
                except Exception:
                    pass
            return ""

        try:
            async with session.get(
                ESPN_LEADERS,
                params={"limit": 500},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return self._leaders_cache
                data = await resp.json(content_type=None)

            # ESPN wraps the list under "leaders" or "categories"
            categories_list = data.get("leaders") or data.get("categories") or []
            for category in categories_list:
                # Try every label field ESPN uses — stop at first match.
                # Using "name or abbreviation" in one expression silently drops
                # the abbreviation when name exists but isn't in the map.
                stat_key = None
                for _field in ("name", "abbreviation", "displayName"):
                    _raw = (category.get(_field) or "").lower().replace(" ", "").replace("_", "")
                    if _raw and _raw in category_key_map:
                        stat_key = category_key_map[_raw]
                        break
                if not stat_key:
                    continue
                # ESPN uses "leaders" or "athletes" for the entry list
                entry_list = category.get("leaders") or category.get("athletes") or []
                for entry in entry_list:
                    try:
                        # Athlete can be nested under "athlete" key or entry is the athlete
                        athlete = entry.get("athlete") or entry
                        pname   = (
                            athlete.get("displayName", "")
                            or athlete.get("fullName", "")
                            or entry.get("displayName", "")
                            or entry.get("fullName", "")
                        )
                        if not pname:
                            continue
                        team_abbr = _abbr_from_athlete(athlete)
                        value     = float(entry.get("value", 0))
                    except (KeyError, TypeError, ValueError):
                        continue
                    if pname not in merged:
                        merged[pname] = {"pts": 0.0, "reb": 0.0, "ast": 0.0, "team_abbr": ""}
                    merged[pname][stat_key] = value
                    if team_abbr:
                        merged[pname]["team_abbr"] = team_abbr

            leaders: Dict[str, Dict] = {}
            for pname, d in merged.items():
                if d["pts"] == 0.0 and d["reb"] == 0.0 and d["ast"] == 0.0:
                    continue
                d["pra"]  = d["pts"] + d["reb"] + d["ast"]
                d["tier"] = _player_tier(d["pts"])
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
                raw_abbr = team_entry.get("team", {}).get("abbreviation", "").upper()
                abbr     = _canon_abbr(raw_abbr)
                players  = []
                for inj in team_entry.get("injuries", []):
                    athlete  = inj.get("athlete", {})
                    full_name = (
                        athlete.get("fullName", "")
                        or athlete.get("displayName", "")
                    )
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

        # Fetch all data sources in parallel (including last-5 game averages)
        (
            injuries, stat_leaders,
            home_ts, away_ts,
            home_roster, away_roster,
            summary_roster,
            home_last5, away_last5,
            home_player_pool, away_player_pool,
            real_odds,
            dk_props_raw,
        ) = await asyncio.gather(
            self.get_injuries(),
            self.get_stat_leaders(),
            self.get_team_stats(home_abbr),
            self.get_team_stats(away_abbr),
            self.get_team_roster(home_abbr),
            self.get_team_roster(away_abbr),
            self._parse_summary_roster(event_id, home_abbr, away_abbr),
            self.get_player_last5(home_abbr),
            self.get_player_last5(away_abbr),
            self.get_team_player_pool(home_abbr),
            self.get_team_player_pool(away_abbr),
            self._get_pickcenter(event_id),
            self._get_player_props_dk(event_id),
        )

        # ── Build props player pool ────────────────────────────────────────────
        #
        # Priority (highest → lowest):
        #   0. Per-team player pools (ESPN_TEAM_LEADERS + ESPN_TEAM_ROSTER per team)
        #      — guaranteed correct team attribution for BOTH teams
        #   1. Global stat leaders   — supplements with wider season-avg coverage
        #   2. ESPN game summary rosters — game-specific availability + avgs
        #   3. Team roster names     — guarantees every remaining player appears
        #
        # Availability filter:
        #   - Players marked "out" or "inactive" in team roster are excluded.
        #   - Players marked unavailable in the game summary are also excluded.
        #   - Injured players from the injuries endpoint (status "out") are excluded.
        # ──────────────────────────────────────────────────────────────────────

        # Collect unavailable player names from the injuries report.
        # "out", "inactive", and "suspension"/"suspended" are all non-playing
        # statuses; doubtful is NOT excluded here (still listed on FanDuel).
        injury_out: set = set()
        _UNAVAILABLE_STATUSES = {"out", "inactive", "suspension", "suspended"}
        for team_abbr_key in (home_abbr, away_abbr):
            for inj in injuries.get(team_abbr_key, []):
                if inj.get("status", "").lower() in _UNAVAILABLE_STATUSES:
                    injury_out.add(inj["name"])

        # Merge availability from team rosters
        combined_roster: Dict[str, str] = {}
        for pname, status in home_roster.items():
            combined_roster[pname] = status
        for pname, status in away_roster.items():
            combined_roster[pname] = status

        # Supplement combined_roster with player pool names as a fallback.
        # When the team-roster API call fails (returns {}), global stat leaders
        # can't be matched to the game via `in_game_by_roster` — this ensures
        # that players already confirmed by the team player pool are still
        # eligible to receive stat overlays from the global leaders endpoint.
        for pname in home_player_pool:
            if pname not in combined_roster:
                combined_roster[pname] = "active"
        for pname in away_player_pool:
            if pname not in combined_roster:
                combined_roster[pname] = "active"

        def _is_available(pname: str, summary_entry: Optional[Dict] = None) -> bool:
            if pname in injury_out:
                return False
            if summary_entry is not None and not summary_entry.get("available", True):
                return False
            roster_status = combined_roster.get(pname, "active")
            return roster_status not in ("out", "inactive")

        # ── Seed props_pool from per-team player pools (highest-confidence source) ──
        # get_team_player_pool() fetches ESPN_TEAM_LEADERS (players already scoped
        # to this specific team — no team-abbr guessing needed) and ESPN_TEAM_ROSTER
        # (complete player list).  Seeding from these first guarantees BOTH teams
        # always have players in the pool before we even look at the global leaders.
        #
        # IMPORTANT: process each team separately so team_abbr is always correct.
        # Merging dicts ({**home, **away}) can overwrite team_abbr for same-named
        # players, so we do two explicit passes instead.
        props_pool: Dict[str, Dict] = {}

        for pname, pdata in home_player_pool.items():
            if not _is_available(pname):
                continue
            entry = dict(pdata)
            entry["team_abbr"] = home_abbr   # always authoritative
            props_pool[pname] = entry

        for pname, pdata in away_player_pool.items():
            if not _is_available(pname):
                continue
            if pname in props_pool:
                # Player appears in both rosters (very rare — traded player edge
                # case). Keep the entry but don't overwrite team_abbr.
                continue
            entry = dict(pdata)
            entry["team_abbr"] = away_abbr   # always authoritative
            props_pool[pname] = entry

        # Supplement with global stat leaders — wider coverage of season averages.
        # ESPN's leaders endpoint often omits team_abbr, so we also accept any
        # player found in combined_roster and infer their team from it.
        for pname, pdata in stat_leaders.items():
            t = pdata.get("team_abbr", "")
            in_game_by_abbr   = t in (home_abbr, away_abbr)
            in_game_by_roster = pname in combined_roster

            if not (in_game_by_abbr or in_game_by_roster):
                continue
            if not _is_available(pname):
                continue

            if pname in props_pool:
                # Already seeded from team player pool (the most accurate source).
                # Only fill in stats that are still zero — never overwrite non-zero
                # values, because the team-specific leaders endpoint is authoritative
                # and the global leaders endpoint can contain stale/wrong splits.
                ex = props_pool[pname]
                for key in ("pts", "reb", "ast"):
                    ex_val  = float(ex.get(key, 0.0) or 0.0)
                    new_val = float(pdata.get(key, 0.0) or 0.0)
                    if ex_val == 0.0 and new_val > 0.0 and new_val <= _PER_GAME_MAX.get(key, 9999.0):
                        ex[key] = new_val
                ex["pra"]  = ex.get("pts", 0.0) + ex.get("reb", 0.0) + ex.get("ast", 0.0)
                ex["tier"] = _player_tier(ex.get("pts", 0))
            else:
                # Player not yet in pool — add them with correct team attribution.
                entry = dict(pdata)
                if pname in home_roster:
                    entry["team_abbr"] = home_abbr
                elif pname in away_roster:
                    entry["team_abbr"] = away_abbr
                elif in_game_by_abbr:
                    entry["team_abbr"] = t   # trust ESPN if it's one of our two teams
                else:
                    continue   # can't determine team — skip
                props_pool[pname] = entry

        # Overlay/add from game summary (authoritative for game-day availability)
        for pname, sdata in summary_roster.items():
            if not _is_available(pname, sdata):
                continue
            if pname in props_pool:
                # Summary roster is used for AVAILABILITY only.
                # Only fill zero-stat gaps — never overwrite the team-player-pool
                # season averages, which are more authoritative than game-summary data.
                # NEVER overwrite team_abbr — we set it authoritatively above.
                ex = props_pool[pname]
                for key in ("pts", "reb", "ast"):
                    ex_val  = float(ex.get(key, 0.0) or 0.0)
                    new_val = float(sdata.get(key, 0.0) or 0.0)
                    if ex_val == 0.0 and new_val > 0.0 and new_val <= _PER_GAME_MAX.get(key, 9999.0):
                        ex[key] = new_val
                ex["pra"]  = ex.get("pts", 0.0) + ex.get("reb", 0.0) + ex.get("ast", 0.0)
                ex["tier"] = _player_tier(ex["pts"])
            else:
                entry = dict(sdata)
                # Infer correct team_abbr from roster membership if not already set
                if entry.get("team_abbr", "") not in (home_abbr, away_abbr):
                    if pname in home_roster:
                        entry["team_abbr"] = home_abbr
                    elif pname in away_roster:
                        entry["team_abbr"] = away_abbr
                    else:
                        continue  # unknown team — skip
                props_pool[pname] = entry

        # Fill in any roster player not yet in the pool with zero-stats placeholder.
        # IMPORTANT: iterate home_roster and away_roster SEPARATELY rather than
        # combined_roster so that team_abbr is always correct even when one of the
        # two roster fetches failed (empty dict).  Using a combined dict + a
        # "pname in home_roster" check breaks when home_roster is empty because
        # every player then falls through to away_abbr.
        _UNAVAIL = {"out", "inactive"}
        for pname, status in home_roster.items():
            if status in _UNAVAIL or pname in injury_out or pname in props_pool:
                continue
            props_pool[pname] = {
                "pts": 0.0, "reb": 0.0, "ast": 0.0, "pra": 0.0,
                "tier": 3, "team_abbr": home_abbr,
            }
        for pname, status in away_roster.items():
            if status in _UNAVAIL or pname in injury_out or pname in props_pool:
                continue
            props_pool[pname] = {
                "pts": 0.0, "reb": 0.0, "ast": 0.0, "pra": 0.0,
                "tier": 3, "team_abbr": away_abbr,
            }

        # ── Populate props_pool stats from last-5-game averages ──────────────────
        # Blend season average with recent form.
        #
        # Weights: 90% season average + 10% last-5 average.
        # Season average is the dominant signal — it's what FanDuel and all major
        # books use as their baseline.  Recent form gets only a 10% nudge so that
        # a 3-game hot streak or cold slump doesn't meaningfully inflate/deflate
        # the line away from a player's true season average.
        #
        # When we have no season data at all, use last-5 directly (it's all we have).
        # When we have no last-5 data, the season average stands unchanged.
        last5_lookup: Dict[str, Dict] = {**home_last5, **away_last5}
        for pname, pdata in props_pool.items():
            l5 = last5_lookup.get(pname)
            if not l5:
                continue
            updated = False
            for stat in ("pts", "reb", "ast"):
                l5_val     = float(l5.get(stat, 0.0) or 0.0)
                season_val = float(pdata.get(stat, 0.0) or 0.0)
                # Sanity-check last-5 values too — a 60-point game in box score
                # is real but season-total data must not sneak through here.
                if l5_val <= 0 or l5_val > _PER_GAME_MAX.get(stat, 9999.0):
                    continue
                if season_val == 0.0:
                    # No season data at all — use last-5 directly
                    pdata[stat] = l5_val
                else:
                    # 90% season + 10% recent form: season average dominates.
                    pdata[stat] = round(0.90 * season_val + 0.10 * l5_val, 1)
                updated = True
            if updated:
                pdata["pra"]  = round(
                    pdata.get("pts", 0.0) + pdata.get("reb", 0.0) + pdata.get("ast", 0.0), 1
                )
                pdata["tier"] = _player_tier(pdata["pts"])

        # Line movement from server's bet volume (optional)
        bet_dist: Dict[str, float] = {}
        if guild_id is not None and bets_manager is not None:
            try:
                bet_dist = bets_manager.get_bet_distribution(guild_id, event_id)
            except Exception:
                pass

        # Build injury map: {player_name: status} for all injured players on both teams.
        # Used to both shade juice (questionable_players set) and shift the actual
        # prop LINE down proportionally for compromised players.
        questionable_players: Set[str] = set()
        injury_map: Dict[str, str] = {}
        for team_abbr_key in (home_abbr, away_abbr):
            for inj in injuries.get(team_abbr_key, []):
                raw_status = inj.get("status", "").lower()
                pname_inj  = inj.get("name", "")
                if not pname_inj:
                    continue
                injury_map[pname_inj] = raw_status
                if raw_status in ("questionable", "doubtful", "day-to-day", "dtd"):
                    questionable_players.add(pname_inj)

        odds  = generate_odds_for_game(game, injuries, stat_leaders, home_ts, away_ts, bet_dist, real_odds=real_odds)

        # ── Real DraftKings props (from ESPN propBets endpoint) ────────────────
        if dk_props_raw:
            # ── Team attribution: use already-fetched rosters (keyed by ESPN displayName,
            # the exact same name source as the propBets athlete endpoint).
            # This is far more reliable than props_pool cross-reference which can fail on
            # minor name differences like "P.J. Washington" vs "PJ Washington".
            roster_team_map: Dict[str, str] = {}
            for pname_r in (home_roster or {}):
                roster_team_map[pname_r.lower()] = home_abbr
            for pname_r in (away_roster or {}):
                roster_team_map[pname_r.lower()] = away_abbr

            # Fallback indexes for players missing from the ESPN team roster endpoint
            pool_lower: Dict[str, str] = {k.lower(): k for k in props_pool}
            sr_lower: Dict[str, str]   = {k.lower(): k for k in (summary_roster or {})}
            inj_lower: Dict[str, str]  = {k.lower(): v for k, v in injury_map.items()}

            real_props: Dict[str, Any] = {}
            for pname, pentry in dk_props_raw.items():
                pname_lc   = pname.lower()
                inj_status = inj_lower.get(pname_lc, "active")
                if inj_status == "out":
                    continue  # DNP — omit entirely

                # Priority 1: direct roster match (most reliable)
                team_abbr_val = roster_team_map.get(pname_lc, "")
                # Priority 2: props_pool (season stats data, different name normalisation)
                if not team_abbr_val:
                    pool_key = pool_lower.get(pname_lc)
                    if pool_key:
                        team_abbr_val = props_pool[pool_key].get("team_abbr", "")
                # Priority 3: summary_roster (ESPN boxscore participants)
                if not team_abbr_val:
                    sr_key = sr_lower.get(pname_lc)
                    if sr_key:
                        team_abbr_val = (summary_roster or {})[sr_key].get("team_abbr", "")

                # Tier from real DK pts line (more accurate than season average)
                dk_pts = pentry.get("pts")
                tier   = _player_tier(dk_pts) if dk_pts is not None else 3

                real_props[pname] = {
                    **pentry,
                    "team_abbr": team_abbr_val,
                    "tier":      tier,
                    "status":    inj_status,
                }
            props: Dict[str, Any] = real_props
        else:
            # Fallback: synthetic props from season-average pool
            props = generate_player_props_for_game(game, props_pool, questionable_players, injury_map)

        # Build public betting action percentages for UI display
        h2h_money = bet_dist.get(game["home_team"], 0.0) + bet_dist.get(game["away_team"], 0.0)
        ou_money  = bet_dist.get("Over", 0.0) + bet_dist.get("Under", 0.0)
        public_action = {
            "h2h_total": int(h2h_money),
            "ou_total":  int(ou_money),
            "home_pct":  round(bet_dist.get(game["home_team"], 0.0) / h2h_money, 3) if h2h_money > 0 else 0.5,
            "away_pct":  round(bet_dist.get(game["away_team"], 0.0) / h2h_money, 3) if h2h_money > 0 else 0.5,
            "over_pct":  round(bet_dist.get("Over",  0.0) / ou_money, 3) if ou_money > 0 else 0.5,
            "under_pct": round(bet_dist.get("Under", 0.0) / ou_money, 3) if ou_money > 0 else 0.5,
        }

        return {**game, "odds": odds, "player_props": props, "public_action": public_action}

    # ── Recent completed games (shared cache, feeds last-5 logic) ─────────────

    async def get_recent_completed(self, days_back: int = 7) -> List[Dict]:
        """Return completed games from the last `days_back` days, cached 1 hr."""
        now = time.monotonic()
        if now - self._recent_completed_ts < RECENT_COMPLETED_TTL and self._recent_completed_cache:
            return self._recent_completed_cache
        games = await self.get_completed_games(days_back=days_back)
        self._recent_completed_cache = games
        self._recent_completed_ts    = now
        return games

    # ── Per-team last-5-game averages ─────────────────────────────────────────

    async def get_player_last5(self, abbr: str) -> Dict[str, Dict]:
        """
        Return {player_name: {pts, reb, ast}} averaged over the team's last
        5 completed games.  Uses the ESPN team schedule endpoint directly
        (playoffs first, then regular season) so it works even when the global
        recent-completed-games window is empty.  Cached per team for 2 hours.
        """
        now = time.monotonic()
        if abbr in self._last5_cache and now - self._last5_ts.get(abbr, 0) < LAST5_TTL:
            return self._last5_cache[abbr]

        team_id = TEAM_IDS.get(abbr)
        if not team_id:
            return {}

        session    = await self._get_session()
        event_ids: List[str] = []

        # Collect up to 5 most-recent completed game IDs.
        # Check playoff schedule first (seasontype=3), then regular season (2).
        for season_type in ("3", "2"):
            if len(event_ids) >= 5:
                break
            try:
                url = ESPN_TEAM_SCHEDULE.format(team_id=team_id)
                async with session.get(
                    url,
                    params={"season": "2026", "seasontype": season_type},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json(content_type=None)

                for ev in reversed(data.get("events", [])):
                    if len(event_ids) >= 5:
                        break
                    comp = (ev.get("competitions") or [{}])[0]
                    if comp.get("status", {}).get("type", {}).get("completed", False):
                        event_ids.append(ev["id"])
            except Exception:
                pass

        if not event_ids:
            return {}

        box_scores = await asyncio.gather(
            *[self.get_game_box_score(eid) for eid in event_ids],
            return_exceptions=True,
        )

        totals: Dict[str, Dict[str, float]] = {}
        counts: Dict[str, int] = {}
        for bs in box_scores:
            if not isinstance(bs, dict) or not bs:
                continue
            for pname, pstats in bs.items():
                pts = float(pstats.get("pts", 0) or 0)
                reb = float(pstats.get("reb", 0) or 0)
                ast = float(pstats.get("ast", 0) or 0)
                if pts + reb + ast == 0:
                    continue
                if pname not in totals:
                    totals[pname] = {"pts": 0.0, "reb": 0.0, "ast": 0.0}
                    counts[pname] = 0
                totals[pname]["pts"] += pts
                totals[pname]["reb"] += reb
                totals[pname]["ast"] += ast
                counts[pname] += 1

        result: Dict[str, Dict] = {
            pname: {
                "pts": round(totals[pname]["pts"] / counts[pname], 1),
                "reb": round(totals[pname]["reb"] / counts[pname], 1),
                "ast": round(totals[pname]["ast"] / counts[pname], 1),
            }
            for pname in totals
            if counts[pname] >= 1
        }

        if result:
            self._last5_cache[abbr] = result
            self._last5_ts[abbr]    = now
        return result

    # ── ESPN news ─────────────────────────────────────────────────────────────

    async def get_news(self, limit: int = 8) -> List[Dict]:
        """Fetch the latest NBA news headlines from ESPN.

        Returns a list of dicts with keys:
          id, headline, description, published, url, image_url
        """
        session = await self._get_session()
        try:
            async with session.get(
                ESPN_NEWS,
                params={"limit": limit},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json(content_type=None)

            articles: List[Dict] = []
            for item in data.get("articles", [])[:limit]:
                # Prefer dataSourceIdentifier as stable ID, fall back to id field
                article_id = (
                    str(item.get("dataSourceIdentifier") or item.get("id") or "")
                )
                headline    = item.get("headline", "")
                description = item.get("description", "")
                published   = item.get("published", "")

                # Extract web URL from links
                url = ""
                links = item.get("links", {})
                web   = links.get("web", {})
                if isinstance(web, dict):
                    url = web.get("href", "")
                elif isinstance(links, dict):
                    url = links.get("mobile", {}).get("href", "") or url

                # Extract thumbnail
                image_url = ""
                images = item.get("images", [])
                if images and isinstance(images[0], dict):
                    image_url = images[0].get("url", "")

                if not headline:
                    continue  # skip empty/malformed articles

                articles.append({
                    "id":          article_id,
                    "headline":    headline,
                    "description": description,
                    "published":   published,
                    "url":         url,
                    "image_url":   image_url,
                })
            return articles
        except Exception:
            return []

    # ── Box score ─────────────────────────────────────────────────────────────

    async def get_game_box_score(self, event_id: str) -> Optional[Dict[str, Dict]]:
        """Parse a completed game's box score into {player_name: {pts, reb, ast, played}}.

        `played` is True if the player logged any minutes.  A player who DNP'd
        due to a late scratch will either be absent from the stat_map entirely
        (ESPN omits them) or present with MIN == 0 / "--".  Either way the
        `played` flag lets evaluate_bet return "no_action" so the stake is
        refunded — matching how FanDuel / DraftKings grade late scratches.

        Completed game stats never change — cached indefinitely per session.
        Uses ESPN's 'labels' column headers (not 'keys') to locate columns.
        """
        if event_id in self._boxscore_cache:
            return self._boxscore_cache[event_id]

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
            for team_block in (data.get("boxscore") or {}).get("players") or []:
                for stat_group in team_block.get("statistics") or []:
                    # ESPN sends both "labels" (display: "PTS") and "keys" (machine:
                    # "points", "fieldGoalsMade-fieldGoalsAttempted").  Always use
                    # labels for index lookup — keys contain compound strings like
                    # "fieldGoalsMade-fieldGoalsAttempted" that can't be floated.
                    raw_labels = stat_group.get("labels") or stat_group.get("names") or []
                    labels     = [str(l).upper() for l in raw_labels]
                    pts_idx    = next((i for i, l in enumerate(labels) if l == "PTS"),  -1)
                    reb_idx    = next((i for i, l in enumerate(labels) if l == "REB"),  -1)
                    ast_idx    = next((i for i, l in enumerate(labels) if l == "AST"),  -1)
                    min_idx    = next((i for i, l in enumerate(labels) if l == "MIN"),  -1)
                    threes_idx = next((i for i, l in enumerate(labels) if l == "3PM"),  -1)
                    stl_idx    = next((i for i, l in enumerate(labels) if l == "STL"),  -1)
                    blk_idx    = next((i for i, l in enumerate(labels) if l == "BLK"),  -1)

                    for athlete_entry in stat_group.get("athletes") or []:
                        pname     = (athlete_entry.get("athlete") or {}).get("displayName", "")
                        raw_stats = athlete_entry.get("stats") or []
                        if not pname or not raw_stats:
                            continue

                        def _gs(idx: int) -> float:
                            if idx < 0 or idx >= len(raw_stats):
                                return 0.0
                            try:
                                return float(str(raw_stats[idx]).split("-")[0].split("/")[0])
                            except (TypeError, ValueError):
                                return 0.0

                        def _parse_min(idx: int) -> float:
                            """Return minutes played as a float (0 = DNP)."""
                            if idx < 0 or idx >= len(raw_stats):
                                return 0.0
                            s = str(raw_stats[idx]).strip()
                            if not s or s in ("--", "0", "0:00", "DNP"):
                                return 0.0
                            try:
                                if ":" in s:
                                    m, sec = s.split(":", 1)
                                    return float(m) + float(sec) / 60
                                return float(s)
                            except (TypeError, ValueError):
                                return 0.0

                        pts     = _gs(pts_idx)
                        reb     = _gs(reb_idx)
                        ast     = _gs(ast_idx)
                        threes  = _gs(threes_idx)
                        stl     = _gs(stl_idx)
                        blk     = _gs(blk_idx)
                        minutes = _parse_min(min_idx)
                        played  = minutes > 0 or (
                            min_idx < 0 and (pts + reb + ast + threes + stl + blk) > 0
                        )
                        stat_map[pname] = {
                            "pts":    pts,
                            "reb":    reb,
                            "ast":    ast,
                            "threes": threes,
                            "stl":    stl,
                            "blk":    blk,
                            "played": played,
                        }

            if stat_map:
                self._boxscore_cache[event_id] = stat_map
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
            "pts":    "Points",
            "reb":    "Rebounds",
            "ast":    "Assists",
            "pra":    "Pts+Reb+Ast",
            "pr":     "Pts+Reb",
            "pa":     "Pts+Ast",
            "ar":     "Ast+Reb",
            "threes": "3-Pointers Made",
            "stl":    "Steals",
            "blk":    "Blocks",
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
    """Return 'won', 'lost', 'push', or 'no_action' (player DNP late scratch)."""

    if bet_type == "h2h":
        if home_score == away_score:
            return "push"
        winner = home_team if home_score > away_score else away_team
        return "won" if selection == winner else "lost"

    elif bet_type == "spreads":
        if point is None:
            return "push"  # missing point data → refund rather than unfair loss
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
            return "push"  # missing line data → refund rather than unfair loss (matches spreads)
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
        # Exact match first; fall back to case-insensitive to handle minor
        # name formatting differences between bet placement and box score.
        pstat = player_stats.get(pname)
        if pstat is None:
            pname_lower = pname.lower()
            pstat = next(
                (v for k, v in player_stats.items() if k.lower() == pname_lower),
                None,
            )

        # ── Late-scratch / DNP detection ──────────────────────────────────────
        # If the player is completely absent from the box score they were a
        # late scratch that ESPN didn't even list.  If they ARE present but
        # played 0 minutes (MIN == 0 / "--") they were a game-time DNP.
        # Either way the bet grades "no_action" — stake is refunded, matching
        # FanDuel / DraftKings industry standard for player prop no-action rules.
        if pstat is None:
            return "no_action"
        # Secondary guard: if stats show any activity the player DID play,
        # regardless of what the played flag says (guards against MIN parse failures).
        actually_played = (
            pstat.get("played", True)
            or pstat.get("pts",    0.0) > 0
            or pstat.get("reb",    0.0) > 0
            or pstat.get("ast",    0.0) > 0
            or pstat.get("threes", 0.0) > 0
            or pstat.get("stl",    0.0) > 0
            or pstat.get("blk",    0.0) > 0
        )
        if not actually_played:
            return "no_action"

        if stat == "pts":
            actual = _first(pstat, ["points", "pts"])
        elif stat == "reb":
            actual = _first(pstat, ["rebounds", "totalrebounds", "reb"])
        elif stat == "ast":
            actual = _first(pstat, ["assists", "ast"])
        elif stat == "pra":
            pts = _first(pstat, ["points",   "pts"]) or 0.0
            reb = _first(pstat, ["rebounds", "reb"]) or 0.0
            ast = _first(pstat, ["assists",  "ast"]) or 0.0
            actual = pts + reb + ast
        elif stat == "pr":
            pts = _first(pstat, ["points",   "pts"]) or 0.0
            reb = _first(pstat, ["rebounds", "reb"]) or 0.0
            actual = pts + reb
        elif stat == "pa":
            pts = _first(pstat, ["points",  "pts"]) or 0.0
            ast = _first(pstat, ["assists", "ast"]) or 0.0
            actual = pts + ast
        elif stat == "ar":
            reb = _first(pstat, ["rebounds", "reb"]) or 0.0
            ast = _first(pstat, ["assists",  "ast"]) or 0.0
            actual = reb + ast
        elif stat == "threes":
            actual = _first(pstat, ["threes", "3pm", "threepointersmade"])
        elif stat == "stl":
            actual = _first(pstat, ["stl", "steals"])
        elif stat == "blk":
            actual = _first(pstat, ["blk", "blocks"])
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
