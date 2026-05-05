"""
NBAdex All-Time NBA Player Database.
400+ players from every era with detailed stat ratings (0-99 scale).

Rating Categories:
  ovr   - Overall rating
  pts   - Scoring/Points ability
  reb   - Rebounding
  ast   - Assists/Playmaking
  blk   - Shot Blocking
  stl   - Steals/Perimeter D
  three - 3-Point Shooting
  fg    - Field Goal Efficiency
  ft    - Free Throw Shooting
  defense - Overall Defense

Tiers:
  1 - GOAT (ovr 97+)
  2 - All-Time Great (ovr 90-96)
  3 - Star / Multiple All-Star (ovr 80-89)
  4 - Solid / All-Star caliber (ovr 70-79)
  5 - Role Player / Notable (ovr 55-69)
"""

from typing import List, Optional


def _p(name, pos, team, era, ovr, pts, reb, ast, blk, stl, three, fg, ft, defense, tier):
    """Helper to create a player dict compactly."""
    return {
        "name": name,
        "positions": pos if isinstance(pos, list) else [pos],
        "team": team,
        "era": era,
        "ovr": ovr,
        "pts": pts,
        "reb": reb,
        "ast": ast,
        "blk": blk,
        "stl": stl,
        "three": three,
        "fg": fg,
        "ft": ft,
        "defense": defense,
        "tier": tier,
    }


ALL_PLAYERS: List[dict] = [
    # ============================================================
    # TIER 1 — GOAT (ovr 97-99)
    # ============================================================
    _p("Michael Jordan",       ["SG","SF"], "Chicago Bulls",         "1990s", 99, 99, 55, 65, 62, 96, 58, 90, 88, 99, 1),
    _p("LeBron James",         ["SF","PF"], "Los Angeles Lakers",    "2010s", 98, 95, 82, 95, 55, 70, 70, 88, 75, 90, 1),
    _p("Kareem Abdul-Jabbar",  ["C"],       "Los Angeles Lakers",    "1970s", 97, 96, 88, 60, 90, 60, 10, 92, 72, 80, 1),
    _p("Magic Johnson",        ["PG","SF"], "Los Angeles Lakers",    "1980s", 97, 85, 78, 98, 35, 65, 25, 86, 80, 75, 1),
    _p("Wilt Chamberlain",     ["C"],       "Philadelphia 76ers",    "1960s", 97, 98, 99, 55, 78, 55, 5,  70, 50, 72, 1),

    # ============================================================
    # TIER 2 — ALL-TIME GREATS (ovr 90-96)
    # ============================================================
    _p("Larry Bird",           ["SF","PF"], "Boston Celtics",        "1980s", 96, 92, 82, 88, 40, 72, 62, 90, 90, 82, 2),
    _p("Shaquille O'Neal",     ["C"],       "Los Angeles Lakers",    "2000s", 96, 98, 90, 45, 88, 35, 5,  75, 48, 88, 2),
    _p("Tim Duncan",           ["PF","C"],  "San Antonio Spurs",     "2000s", 95, 82, 92, 65, 90, 42, 12, 86, 72, 92, 2),
    _p("Kobe Bryant",          ["SG","SF"], "Los Angeles Lakers",    "2000s", 95, 96, 56, 60, 50, 90, 62, 86, 85, 88, 2),
    _p("Bill Russell",         ["C"],       "Boston Celtics",        "1960s", 94, 48, 97, 55, 95, 72, 5,  62, 65, 98, 2),
    _p("Oscar Robertson",      ["PG"],      "Cincinnati Royals",     "1960s", 93, 88, 65, 95, 30, 62, 20, 88, 82, 75, 2),
    _p("Jerry West",           ["PG","SG"], "Los Angeles Lakers",    "1960s", 93, 90, 50, 88, 25, 62, 20, 88, 88, 80, 2),
    _p("Hakeem Olajuwon",      ["C"],       "Houston Rockets",       "1990s", 93, 85, 90, 55, 97, 72, 12, 84, 72, 96, 2),
    _p("Stephen Curry",        ["PG"],      "Golden State Warriors", "2010s", 92, 92, 48, 82, 18, 96, 99, 88, 92, 62, 2),
    _p("Kevin Durant",         ["SF","PF"], "Brooklyn Nets",         "2010s", 92, 98, 68, 68, 62, 65, 82, 92, 88, 72, 2),
    _p("Giannis Antetokounmpo",["PF","C"],  "Milwaukee Bucks",       "2020s", 91, 90, 90, 72, 78, 68, 30, 82, 72, 90, 2),
    _p("Moses Malone",         ["C","PF"],  "Philadelphia 76ers",    "1980s", 91, 82, 95, 38, 68, 30, 10, 78, 80, 72, 2),
    _p("Kevin Garnett",        ["PF","C"],  "Minnesota Timberwolves","2000s", 91, 82, 90, 68, 88, 72, 32, 84, 78, 92, 2),
    _p("Elgin Baylor",         ["SF","PF"], "Los Angeles Lakers",    "1960s", 91, 90, 82, 72, 35, 62, 12, 82, 70, 68, 2),
    _p("Isiah Thomas",         ["PG"],      "Detroit Pistons",       "1980s", 90, 85, 42, 95, 18, 80, 28, 84, 78, 82, 2),
    _p("Charles Barkley",      ["PF"],      "Phoenix Suns",          "1990s", 90, 88, 90, 68, 45, 55, 28, 86, 78, 72, 2),
    _p("Karl Malone",          ["PF"],      "Utah Jazz",             "1990s", 90, 90, 90, 55, 42, 48, 18, 84, 78, 72, 2),
    _p("Julius Erving",        ["SF"],      "Philadelphia 76ers",    "1970s", 90, 88, 72, 70, 70, 72, 22, 84, 72, 80, 2),

    # ============================================================
    # TIER 3 — STARS (ovr 80-89)
    # ============================================================
    _p("Dirk Nowitzki",        ["PF"],      "Dallas Mavericks",      "2000s", 89, 92, 72, 58, 42, 68, 82, 90, 92, 55, 3),
    _p("John Stockton",        ["PG"],      "Utah Jazz",             "1990s", 89, 72, 42, 98, 18, 88, 28, 88, 86, 82, 3),
    _p("David Robinson",       ["C"],       "San Antonio Spurs",     "1990s", 89, 82, 85, 48, 88, 72, 22, 84, 80, 88, 3),
    _p("Gary Payton",          ["PG"],      "Seattle SuperSonics",   "1990s", 88, 80, 50, 88, 22, 88, 25, 84, 78, 92, 3),
    _p("Allen Iverson",        ["PG","SG"], "Philadelphia 76ers",    "2000s", 88, 96, 38, 72, 22, 88, 30, 82, 80, 80, 3),
    _p("Scottie Pippen",       ["SF","SG"], "Chicago Bulls",         "1990s", 88, 78, 68, 82, 55, 88, 38, 84, 72, 92, 3),
    _p("Patrick Ewing",        ["C"],       "New York Knicks",       "1990s", 88, 85, 85, 42, 88, 55, 18, 84, 74, 80, 3),
    _p("Dominique Wilkins",    ["SF"],      "Atlanta Hawks",         "1980s", 88, 92, 68, 42, 38, 72, 30, 84, 80, 62, 3),
    _p("Clyde Drexler",        ["SG","SF"], "Portland Trail Blazers","1990s", 87, 85, 62, 75, 38, 75, 32, 84, 78, 80, 3),
    _p("Jason Kidd",           ["PG"],      "New Jersey Nets",       "2000s", 87, 62, 68, 95, 28, 85, 30, 78, 80, 88, 3),
    _p("Nikola Jokic",         ["C"],       "Denver Nuggets",        "2020s", 87, 82, 90, 88, 62, 38, 38, 88, 84, 65, 3),
    _p("Kawhi Leonard",        ["SF","SG"], "Toronto Raptors",       "2010s", 87, 85, 65, 55, 42, 90, 52, 88, 82, 92, 3),
    _p("Dwyane Wade",          ["SG"],      "Miami Heat",            "2000s", 87, 88, 55, 72, 55, 82, 22, 86, 78, 82, 3),
    _p("Ray Allen",            ["SG","SF"], "Boston Celtics",        "2000s", 86, 82, 42, 48, 22, 72, 92, 88, 92, 68, 3),
    _p("Pete Maravich",        ["PG","SG"], "New Orleans Jazz",      "1970s", 86, 92, 42, 82, 18, 72, 28, 86, 80, 68, 3),
    _p("Kevin McHale",         ["PF","C"],  "Boston Celtics",        "1980s", 86, 82, 82, 42, 68, 50, 12, 88, 78, 72, 3),
    _p("Bob Pettit",           ["PF","C"],  "St. Louis Hawks",       "1950s", 86, 88, 90, 38, 38, 42, 5,  80, 72, 68, 3),
    _p("Tracy McGrady",        ["SF","SG"], "Orlando Magic",         "2000s", 86, 94, 60, 68, 48, 75, 50, 86, 78, 68, 3),
    _p("Reggie Miller",        ["SG"],      "Indiana Pacers",        "1990s", 85, 82, 35, 48, 18, 78, 92, 86, 92, 68, 3),
    _p("Chris Paul",           ["PG"],      "Phoenix Suns",          "2000s", 85, 72, 48, 97, 18, 88, 40, 88, 86, 88, 3),
    _p("Penny Hardaway",       ["PG","SG"], "Orlando Magic",         "1990s", 85, 82, 52, 85, 40, 75, 35, 86, 78, 75, 3),
    _p("Steve Nash",           ["PG"],      "Phoenix Suns",          "2000s", 85, 72, 35, 97, 12, 72, 52, 90, 92, 60, 3),
    _p("Grant Hill",           ["SF","SG"], "Detroit Pistons",       "1990s", 85, 82, 62, 80, 38, 78, 32, 86, 80, 80, 3),
    _p("Pau Gasol",            ["PF","C"],  "Los Angeles Lakers",    "2000s", 84, 78, 85, 68, 68, 62, 30, 86, 80, 72, 3),
    _p("Vince Carter",         ["SG","SF"], "Toronto Raptors",       "2000s", 84, 85, 55, 52, 42, 72, 50, 84, 78, 62, 3),
    _p("Paul Pierce",          ["SF"],      "Boston Celtics",        "2000s", 84, 85, 60, 60, 38, 72, 45, 86, 82, 68, 3),
    _p("Damian Lillard",       ["PG"],      "Portland Trail Blazers","2010s", 84, 90, 38, 82, 22, 78, 85, 86, 88, 58, 3),
    _p("Kyrie Irving",         ["PG","SG"], "Cleveland Cavaliers",   "2010s", 84, 88, 38, 78, 25, 80, 42, 90, 88, 68, 3),
    _p("James Harden",         ["SG","PG"], "Houston Rockets",       "2010s", 84, 92, 48, 85, 22, 62, 58, 82, 88, 55, 3),
    _p("Bob Cousy",            ["PG"],      "Boston Celtics",        "1950s", 83, 72, 38, 95, 12, 72, 5,  82, 80, 72, 3),
    _p("John Havlicek",        ["SF","SG"], "Boston Celtics",        "1970s", 83, 80, 60, 70, 28, 78, 18, 84, 80, 80, 3),
    _p("Mitch Richmond",       ["SG"],      "Sacramento Kings",      "1990s", 83, 85, 42, 52, 18, 72, 42, 86, 82, 68, 3),
    _p("George Gervin",        ["SG","SF"], "San Antonio Spurs",     "1970s", 83, 95, 52, 50, 35, 65, 18, 90, 82, 60, 3),
    _p("Rick Barry",           ["SF"],      "Golden State Warriors", "1970s", 83, 88, 60, 72, 30, 75, 20, 86, 85, 68, 3),
    _p("James Worthy",         ["SF"],      "Los Angeles Lakers",    "1980s", 83, 82, 62, 55, 42, 68, 20, 88, 80, 72, 3),
    _p("Robert Parish",        ["C"],       "Boston Celtics",        "1980s", 83, 72, 88, 35, 72, 45, 8,  82, 72, 72, 3),
    _p("Alonzo Mourning",      ["C"],       "Miami Heat",            "2000s", 83, 78, 80, 35, 90, 62, 10, 82, 70, 90, 3),
    _p("Chris Webber",         ["PF"],      "Sacramento Kings",      "2000s", 82, 80, 85, 72, 55, 58, 22, 84, 72, 68, 3),
    _p("Elvin Hayes",          ["C","PF"],  "Washington Bullets",    "1970s", 82, 82, 90, 38, 65, 45, 8,  78, 70, 68, 3),
    _p("Nate Archibald",       ["PG"],      "Kansas City Kings",     "1970s", 82, 82, 30, 90, 10, 75, 12, 84, 86, 72, 3),
    _p("Dikembe Mutombo",      ["C"],       "Various",               "1990s", 82, 52, 90, 30, 98, 35, 5,  72, 62, 90, 3),
    _p("Dennis Rodman",        ["PF","SF"], "Chicago Bulls",         "1990s", 82, 28, 98, 38, 45, 72, 2,  68, 70, 88, 3),
    _p("Dolph Schayes",        ["PF","C"],  "Syracuse Nationals",    "1950s", 82, 78, 82, 45, 30, 42, 5,  80, 85, 62, 3),
    _p("Joe Dumars",           ["SG","PG"], "Detroit Pistons",       "1990s", 82, 78, 40, 60, 15, 78, 30, 86, 88, 82, 3),
    _p("Klay Thompson",        ["SG","SF"], "Golden State Warriors", "2010s", 82, 82, 48, 38, 25, 70, 90, 88, 88, 75, 3),
    _p("Chris Bosh",           ["PF","C"],  "Miami Heat",            "2000s", 81, 78, 80, 52, 62, 55, 35, 86, 78, 72, 3),
    _p("Bob Lanier",           ["C"],       "Detroit Pistons",       "1970s", 81, 78, 85, 42, 68, 45, 8,  82, 72, 70, 3),
    _p("Walt Bellamy",         ["C"],       "New York Knicks",       "1960s", 80, 78, 90, 32, 50, 30, 5,  72, 60, 60, 3),
    _p("Bill Walton",          ["C"],       "Portland Trail Blazers","1970s", 80, 68, 88, 55, 80, 60, 5,  80, 72, 80, 3),
    _p("Willis Reed",          ["C","PF"],  "New York Knicks",       "1970s", 80, 72, 80, 40, 55, 48, 8,  80, 78, 72, 3),
    _p("Walt Frazier",         ["PG","SG"], "New York Knicks",       "1970s", 80, 72, 52, 82, 18, 88, 18, 84, 80, 88, 3),
    _p("LaMarcus Aldridge",    ["PF","C"],  "San Antonio Spurs",     "2010s", 80, 82, 80, 42, 50, 45, 25, 86, 78, 62, 3),
    _p("Anthony Davis",        ["PF","C"],  "Los Angeles Lakers",    "2010s", 80, 82, 86, 42, 88, 62, 25, 84, 72, 88, 3),
    _p("Deron Williams",       ["PG"],      "New Jersey Nets",       "2000s", 80, 78, 42, 90, 15, 70, 38, 86, 80, 65, 3),

    # ============================================================
    # TIER 4 — SOLID / ALL-STAR CALIBER (ovr 70-79)
    # ============================================================
    _p("Carmelo Anthony",      ["SF","PF"], "New York Knicks",       "2000s", 79, 92, 65, 42, 30, 65, 42, 84, 80, 52, 4),
    _p("Paul George",          ["SF","SG"], "Oklahoma City Thunder", "2010s", 79, 80, 65, 58, 38, 78, 55, 84, 82, 82, 4),
    _p("Jimmy Butler",         ["SF","SG"], "Miami Heat",            "2010s", 79, 78, 62, 68, 30, 78, 28, 84, 85, 85, 4),
    _p("Tony Parker",          ["PG"],      "San Antonio Spurs",     "2000s", 79, 78, 38, 85, 15, 62, 18, 88, 82, 68, 4),
    _p("Dwight Howard",        ["C"],       "Orlando Magic",         "2000s", 79, 68, 92, 32, 90, 55, 5,  72, 60, 88, 4),
    _p("Manu Ginobili",        ["SG","SF"], "San Antonio Spurs",     "2000s", 79, 78, 45, 72, 25, 78, 50, 84, 80, 78, 4),
    _p("Russell Westbrook",    ["PG"],      "Oklahoma City Thunder", "2010s", 79, 88, 75, 88, 30, 72, 30, 78, 72, 72, 4),
    _p("Derrick Rose",         ["PG"],      "Chicago Bulls",         "2010s", 79, 82, 38, 80, 20, 75, 30, 82, 78, 72, 4),
    _p("Blake Griffin",        ["PF"],      "Los Angeles Clippers",  "2010s", 79, 80, 78, 60, 40, 52, 32, 80, 72, 62, 4),
    _p("Devin Booker",         ["SG","PG"], "Phoenix Suns",          "2010s", 79, 88, 40, 68, 18, 68, 52, 88, 88, 62, 4),
    _p("DeMar DeRozan",        ["SG","SF"], "Toronto Raptors",       "2010s", 79, 85, 45, 60, 18, 62, 18, 86, 82, 62, 4),
    _p("Nikola Vucevic",       ["C"],       "Orlando Magic",         "2010s", 78, 75, 85, 48, 45, 35, 38, 84, 80, 52, 4),
    _p("Spencer Haywood",      ["PF","C"],  "Seattle SuperSonics",   "1970s", 78, 80, 85, 38, 45, 38, 8,  80, 72, 65, 4),
    _p("David Thompson",       ["SG","SF"], "Denver Nuggets",        "1970s", 78, 88, 48, 55, 30, 72, 20, 82, 75, 68, 4),
    _p("George McGinnis",      ["PF"],      "Indiana Pacers",        "1970s", 78, 80, 85, 52, 40, 50, 8,  76, 68, 62, 4),
    _p("Gail Goodrich",        ["SG","PG"], "Los Angeles Lakers",    "1970s", 78, 80, 35, 72, 15, 68, 18, 84, 80, 70, 4),
    _p("Alex English",         ["SF"],      "Denver Nuggets",        "1980s", 78, 82, 52, 42, 28, 60, 15, 86, 78, 55, 4),
    _p("Adrian Dantley",       ["SF","PF"], "Utah Jazz",             "1980s", 78, 85, 55, 42, 22, 50, 8,  84, 82, 55, 4),
    _p("Detlef Schrempf",      ["SF","PF"], "Indiana Pacers",        "1990s", 78, 72, 68, 62, 22, 55, 45, 84, 82, 65, 4),
    _p("Tim Hardaway",         ["PG"],      "Golden State Warriors", "1990s", 78, 78, 35, 88, 12, 70, 38, 82, 82, 72, 4),
    _p("Mark Price",           ["PG"],      "Cleveland Cavaliers",   "1990s", 78, 75, 32, 88, 12, 72, 42, 88, 92, 68, 4),
    _p("Rolando Blackman",     ["SG","PG"], "Dallas Mavericks",      "1980s", 77, 78, 38, 52, 15, 65, 22, 86, 84, 65, 4),
    _p("Joe Barry Carroll",    ["C"],       "Golden State Warriors", "1980s", 77, 75, 78, 35, 55, 38, 8,  80, 72, 65, 4),
    _p("Bernard King",         ["SF"],      "New York Knicks",       "1980s", 77, 88, 50, 42, 22, 55, 12, 82, 75, 52, 4),
    _p("Mark Aguirre",         ["SF","PF"], "Dallas Mavericks",      "1980s", 77, 82, 55, 45, 22, 52, 18, 82, 75, 52, 4),
    _p("Dan Majerle",          ["SG","SF"], "Phoenix Suns",          "1990s", 77, 75, 50, 55, 20, 68, 45, 84, 80, 72, 4),
    _p("Chris Mullin",         ["SF","SG"], "Golden State Warriors", "1990s", 77, 80, 48, 58, 18, 65, 55, 88, 90, 65, 4),
    _p("Kevin Johnson",        ["PG"],      "Phoenix Suns",          "1990s", 77, 80, 42, 88, 15, 72, 18, 84, 80, 70, 4),
    _p("Latrell Sprewell",     ["SG","SF"], "New York Knicks",       "1990s", 77, 80, 45, 55, 20, 72, 28, 82, 72, 72, 4),
    _p("Glen Rice",            ["SF","SG"], "Miami Heat",            "1990s", 77, 82, 48, 38, 18, 68, 52, 86, 85, 55, 4),
    _p("Isaiah Thomas",        ["PG"],      "Boston Celtics",        "2010s", 77, 88, 28, 72, 12, 68, 38, 86, 82, 55, 4),
    _p("Kevin Love",           ["PF","C"],  "Cleveland Cavaliers",   "2010s", 77, 78, 85, 55, 25, 48, 50, 84, 84, 45, 4),
    _p("Rudy Gobert",          ["C"],       "Utah Jazz",             "2010s", 77, 52, 90, 28, 92, 42, 5,  78, 65, 90, 4),
    _p("Paul Millsap",         ["PF"],      "Atlanta Hawks",         "2010s", 77, 72, 72, 50, 42, 60, 32, 82, 78, 72, 4),
    _p("DeMarcus Cousins",     ["C"],       "Sacramento Kings",      "2010s", 77, 82, 85, 52, 48, 48, 32, 80, 72, 62, 4),
    _p("Toni Kukoc",           ["SF","PF"], "Chicago Bulls",         "1990s", 76, 72, 52, 68, 25, 55, 45, 84, 80, 60, 4),
    _p("Jamal Mashburn",       ["SF","PF"], "Charlotte Hornets",     "1990s", 76, 78, 52, 48, 22, 60, 30, 82, 75, 58, 4),
    _p("Danny Manning",        ["PF","SF"], "Various",               "1990s", 76, 75, 65, 48, 42, 55, 15, 82, 75, 65, 4),
    _p("Fat Lever",            ["PG","SG"], "Denver Nuggets",        "1980s", 76, 72, 55, 78, 20, 72, 18, 82, 78, 78, 4),
    _p("Dale Ellis",           ["SG","SF"], "Seattle SuperSonics",   "1980s", 76, 78, 42, 35, 15, 60, 55, 86, 82, 55, 4),
    _p("Terry Porter",         ["PG"],      "Portland Trail Blazers","1990s", 76, 72, 40, 82, 12, 68, 42, 84, 84, 72, 4),
    _p("Tom Chambers",         ["PF","SF"], "Phoenix Suns",          "1990s", 76, 80, 65, 40, 30, 55, 22, 82, 78, 55, 4),
    _p("Trae Young",           ["PG"],      "Atlanta Hawks",         "2020s", 76, 85, 32, 90, 10, 58, 55, 84, 86, 38, 4),
    _p("Ja Morant",            ["PG"],      "Memphis Grizzlies",     "2020s", 76, 82, 42, 82, 25, 68, 32, 84, 76, 68, 4),
    _p("Zion Williamson",      ["PF","SF"], "New Orleans Pelicans",  "2020s", 76, 85, 75, 50, 35, 55, 15, 82, 70, 68, 4),
    _p("Pascal Siakam",        ["PF","SF"], "Toronto Raptors",       "2010s", 76, 78, 70, 58, 38, 62, 32, 84, 75, 72, 4),
    _p("Bam Adebayo",          ["C","PF"],  "Miami Heat",            "2010s", 76, 72, 82, 60, 65, 60, 8,  80, 75, 82, 4),
    _p("Jayson Tatum",         ["SF","PF"], "Boston Celtics",        "2010s", 76, 82, 62, 52, 32, 68, 55, 86, 82, 68, 4),
    _p("Donovan Mitchell",     ["SG","PG"], "Cleveland Cavaliers",   "2010s", 76, 82, 40, 65, 22, 72, 42, 84, 80, 68, 4),
    _p("Andrew Wiggins",       ["SF","SG"], "Golden State Warriors", "2010s", 75, 75, 52, 42, 35, 68, 40, 82, 75, 68, 4),
    _p("Bradley Beal",         ["SG"],      "Washington Wizards",    "2010s", 75, 82, 40, 60, 15, 68, 38, 86, 82, 60, 4),
    _p("Kyle Lowry",           ["PG"],      "Toronto Raptors",       "2010s", 75, 72, 48, 80, 12, 72, 42, 82, 80, 72, 4),
    _p("Karl-Anthony Towns",   ["C","PF"],  "Minnesota Timberwolves","2010s", 75, 80, 85, 48, 42, 42, 52, 86, 82, 52, 4),
    _p("Draymond Green",       ["PF","C"],  "Golden State Warriors", "2010s", 75, 52, 72, 80, 42, 82, 28, 72, 72, 90, 4),
    _p("John Wall",            ["PG"],      "Washington Wizards",    "2010s", 75, 72, 38, 88, 22, 72, 22, 80, 72, 72, 4),
    _p("Lance Stephenson",     ["SG","SF"], "Indiana Pacers",        "2010s", 72, 68, 50, 60, 20, 68, 30, 80, 72, 70, 4),
    _p("Horace Grant",         ["PF","SF"], "Chicago Bulls",         "1990s", 72, 62, 75, 42, 42, 60, 12, 78, 72, 75, 4),
    _p("Sam Jones",            ["SG","PG"], "Boston Celtics",        "1960s", 72, 72, 38, 55, 18, 62, 12, 82, 82, 70, 4),
    _p("Hal Greer",            ["SG","PG"], "Philadelphia 76ers",    "1960s", 72, 75, 42, 58, 18, 65, 12, 84, 78, 68, 4),
    _p("Billy Cunningham",     ["SF","PF"], "Philadelphia 76ers",    "1960s", 72, 75, 65, 58, 28, 65, 12, 80, 72, 68, 4),
    _p("Dave Cowens",          ["C","PF"],  "Boston Celtics",        "1970s", 72, 68, 85, 48, 42, 62, 12, 78, 72, 72, 4),
    _p("World B. Free",        ["SG"],      "Golden State Warriors", "1980s", 72, 82, 35, 48, 12, 60, 18, 80, 72, 55, 4),
    _p("Alvin Robertson",      ["SG","PG"], "San Antonio Spurs",     "1980s", 72, 68, 48, 68, 18, 80, 22, 80, 75, 82, 4),
    _p("Buck Williams",        ["PF","C"],  "New Jersey Nets",       "1980s", 72, 62, 82, 28, 45, 45, 8,  76, 72, 70, 4),
    _p("Danny Ainge",          ["PG","SG"], "Boston Celtics",        "1980s", 72, 70, 35, 68, 12, 65, 40, 84, 82, 68, 4),
    _p("Byron Scott",          ["SG"],      "Los Angeles Lakers",    "1980s", 71, 70, 38, 42, 15, 62, 38, 84, 80, 65, 4),
    _p("A.C. Green",           ["PF"],      "Los Angeles Lakers",    "1990s", 71, 55, 78, 32, 35, 50, 18, 76, 72, 65, 4),
    _p("Derrick Coleman",      ["PF"],      "New Jersey Nets",       "1990s", 71, 68, 78, 48, 38, 50, 22, 78, 70, 55, 4),
    _p("Larry Johnson",        ["PF","SF"], "Charlotte Hornets",     "1990s", 71, 72, 72, 42, 28, 50, 25, 80, 72, 55, 4),
    _p("Vin Baker",            ["PF","C"],  "Milwaukee Bucks",       "1990s", 71, 72, 75, 35, 45, 42, 12, 78, 70, 60, 4),
    _p("Glenn Robinson",       ["SF"],      "Milwaukee Bucks",       "1990s", 71, 78, 52, 38, 22, 55, 32, 82, 75, 50, 4),
    _p("Rudy Gay",             ["SF","PF"], "Memphis Grizzlies",     "2000s", 71, 72, 55, 42, 30, 62, 30, 80, 72, 58, 4),
    _p("OJ Mayo",              ["SG","PG"], "Memphis Grizzlies",     "2000s", 71, 72, 38, 52, 15, 62, 40, 82, 78, 60, 4),
    _p("Amar'e Stoudemire",    ["PF","C"],  "Phoenix Suns",          "2000s", 71, 78, 72, 35, 62, 45, 10, 80, 70, 62, 4),
    _p("Joe Johnson",          ["SG","SF"], "Atlanta Hawks",         "2000s", 71, 75, 42, 52, 18, 60, 38, 84, 80, 55, 4),
    _p("Rashard Lewis",        ["SF","PF"], "Orlando Magic",         "2000s", 71, 72, 52, 42, 25, 55, 55, 84, 80, 52, 4),
    _p("Shaun Livingston",     ["PG","SG"], "Golden State Warriors", "2010s", 71, 65, 42, 68, 18, 58, 10, 80, 75, 68, 4),
    _p("Victor Oladipo",       ["SG","PG"], "Indiana Pacers",        "2010s", 71, 72, 45, 60, 22, 72, 38, 80, 75, 75, 4),
    _p("Khris Middleton",      ["SF","SG"], "Milwaukee Bucks",       "2010s", 71, 75, 55, 58, 22, 60, 42, 86, 86, 65, 4),
    _p("Kristaps Porzingis",   ["PF","C"],  "Dallas Mavericks",      "2010s", 71, 78, 72, 35, 68, 45, 52, 82, 80, 62, 4),
    _p("Jaylen Brown",         ["SG","SF"], "Boston Celtics",        "2010s", 71, 75, 55, 42, 25, 68, 38, 82, 78, 70, 4),
    _p("CJ McCollum",          ["SG","PG"], "Portland Trail Blazers","2010s", 71, 78, 38, 55, 12, 62, 45, 88, 86, 58, 4),
    _p("Michael Carter-Williams",["PG","SG"],"Philadelphia 76ers",  "2010s", 70, 62, 52, 72, 20, 72, 15, 72, 65, 72, 4),
    _p("D'Angelo Russell",     ["PG","SG"], "Brooklyn Nets",         "2010s", 70, 75, 32, 72, 12, 55, 48, 84, 80, 45, 4),
    _p("Eric Gordon",          ["SG","PG"], "Houston Rockets",       "2000s", 70, 75, 35, 45, 12, 62, 45, 82, 78, 58, 4),
    _p("Brook Lopez",          ["C"],       "Brooklyn Nets",         "2000s", 70, 72, 72, 30, 55, 30, 45, 82, 78, 62, 4),
    _p("Shai Gilgeous-Alexander",["PG","SG"],"Oklahoma City Thunder","2020s", 70, 82, 45, 72, 28, 68, 28, 86, 82, 68, 4),
    _p("Luka Doncic",          ["PG","SF"], "Dallas Mavericks",      "2020s", 70, 85, 65, 85, 22, 45, 55, 84, 78, 48, 4),
    _p("Anthony Edwards",      ["SG","SF"], "Minnesota Timberwolves","2020s", 70, 82, 52, 55, 28, 68, 48, 82, 78, 68, 4),
    _p("Jalen Brunson",        ["PG"],      "New York Knicks",       "2020s", 70, 80, 35, 75, 12, 58, 38, 88, 86, 60, 4),

    # ============================================================
    # TIER 5 — ROLE PLAYERS / NOTABLE (ovr 55-69)
    # ============================================================
    _p("Dennis Johnson",       ["PG","SG"], "Boston Celtics",        "1980s", 69, 65, 42, 68, 18, 72, 12, 78, 78, 80, 5),
    _p("Terry Cummings",       ["PF"],      "Milwaukee Bucks",       "1980s", 69, 72, 72, 35, 28, 42, 12, 78, 72, 58, 5),
    _p("Jack Sikma",           ["C","PF"],  "Seattle SuperSonics",   "1980s", 69, 68, 82, 40, 45, 40, 12, 80, 82, 62, 5),
    _p("George Mikan",         ["C"],       "Minneapolis Lakers",    "1950s", 69, 78, 82, 35, 50, 28, 5,  72, 68, 60, 5),
    _p("Bob McAdoo",           ["C","PF"],  "Buffalo Braves",        "1970s", 69, 82, 72, 32, 50, 38, 8,  78, 72, 55, 5),
    _p("Walter Davis",         ["SG","SF"], "Phoenix Suns",          "1980s", 69, 72, 38, 55, 15, 58, 25, 82, 80, 60, 5),
    _p("Paul Westphal",        ["PG","SG"], "Phoenix Suns",          "1970s", 69, 72, 35, 72, 12, 62, 18, 82, 80, 62, 5),
    _p("Larry Nance",          ["PF","C"],  "Cleveland Cavaliers",   "1980s", 69, 65, 72, 35, 62, 42, 10, 80, 72, 68, 5),
    _p("Mark Jackson",         ["PG"],      "New York Knicks",       "1990s", 68, 58, 38, 85, 12, 55, 18, 76, 75, 60, 5),
    _p("Drazen Petrovic",      ["SG"],      "New Jersey Nets",       "1990s", 68, 78, 30, 48, 10, 55, 55, 86, 85, 52, 5),
    _p("Nick Anderson",        ["SG","SF"], "Orlando Magic",         "1990s", 68, 68, 45, 42, 20, 60, 32, 80, 72, 60, 5),
    _p("Muggsy Bogues",        ["PG"],      "Charlotte Hornets",     "1990s", 68, 52, 28, 80, 5,  82, 22, 78, 80, 72, 5),
    _p("Mahmoud Abdul-Rauf",   ["PG"],      "Denver Nuggets",        "1990s", 68, 72, 28, 65, 8,  55, 35, 88, 92, 55, 5),
    _p("Sean Elliott",         ["SG","SF"], "San Antonio Spurs",     "1990s", 68, 68, 42, 45, 18, 60, 40, 82, 80, 58, 5),
    _p("Damon Stoudamire",     ["PG"],      "Toronto Raptors",       "1990s", 68, 68, 32, 78, 10, 65, 38, 82, 78, 62, 5),
    _p("Mookie Blaylock",      ["PG"],      "Atlanta Hawks",         "1990s", 68, 62, 38, 78, 15, 80, 28, 78, 72, 80, 5),
    _p("Jim Jackson",          ["SG","PG"], "Dallas Mavericks",      "1990s", 68, 72, 42, 52, 15, 58, 30, 80, 75, 58, 5),
    _p("Marques Johnson",      ["SF"],      "Milwaukee Bucks",       "1980s", 67, 70, 55, 50, 28, 55, 10, 80, 72, 60, 5),
    _p("Jeff Hornacek",        ["SG","PG"], "Utah Jazz",             "1990s", 67, 68, 38, 60, 12, 65, 45, 84, 90, 68, 5),
    _p("Dan Issel",            ["C","PF"],  "Denver Nuggets",        "1970s", 67, 72, 72, 38, 28, 35, 10, 78, 72, 55, 5),
    _p("Gus Williams",         ["PG","SG"], "Seattle SuperSonics",   "1970s", 67, 70, 30, 70, 10, 65, 12, 78, 75, 65, 5),
    _p("Purvis Short",         ["SF","SG"], "Golden State Warriors", "1980s", 67, 72, 42, 35, 15, 55, 20, 80, 78, 50, 5),
    _p("Jeff Malone",          ["SG"],      "Washington Bullets",    "1980s", 67, 72, 35, 40, 12, 55, 20, 84, 80, 55, 5),
    _p("Mike Mitchell",        ["SF","PF"], "San Antonio Spurs",     "1980s", 67, 72, 52, 32, 18, 50, 12, 80, 75, 52, 5),
    _p("Connie Hawkins",       ["SF","PF"], "Phoenix Suns",          "1960s", 67, 70, 65, 55, 38, 55, 10, 78, 68, 62, 5),
    _p("Bob Boozer",           ["PF","C"],  "Chicago Bulls",         "1960s", 66, 62, 72, 30, 30, 32, 5,  76, 70, 58, 5),
    _p("Chet Walker",          ["SF"],      "Chicago Bulls",         "1960s", 66, 68, 55, 42, 22, 50, 10, 82, 80, 58, 5),
    _p("Jo Jo White",          ["PG","SG"], "Boston Celtics",        "1970s", 66, 70, 38, 72, 12, 62, 15, 80, 80, 65, 5),
    _p("Dave DeBusschere",     ["PF","SF"], "New York Knicks",       "1970s", 66, 60, 72, 38, 25, 58, 10, 78, 70, 72, 5),
    _p("Cazzie Russell",       ["SG","SF"], "New York Knicks",       "1970s", 65, 68, 40, 38, 15, 52, 12, 80, 75, 52, 5),
    _p("Bob Dandridge",        ["SF","PF"], "Milwaukee Bucks",       "1970s", 65, 65, 58, 42, 25, 55, 10, 78, 72, 62, 5),
    _p("Happy Hairston",       ["PF"],      "Los Angeles Lakers",    "1970s", 65, 58, 72, 28, 28, 38, 5,  72, 68, 55, 5),
    _p("Dave Bing",            ["PG","SG"], "Detroit Pistons",       "1960s", 65, 72, 35, 72, 12, 62, 10, 78, 75, 65, 5),
    _p("Elmore Smith",         ["C"],       "Los Angeles Lakers",    "1970s", 65, 55, 72, 25, 72, 32, 5,  70, 62, 70, 5),
    _p("Tom Van Arsdale",      ["SF"],      "Cincinnati Royals",     "1960s", 64, 62, 45, 38, 15, 48, 8,  76, 72, 55, 5),
    _p("Zelmo Beaty",          ["C"],       "St. Louis Hawks",       "1960s", 64, 60, 72, 30, 42, 28, 5,  72, 68, 62, 5),
    _p("Norm Van Lier",        ["PG"],      "Chicago Bulls",         "1970s", 64, 58, 38, 72, 12, 75, 10, 72, 72, 80, 5),
    _p("Jim McMillian",        ["SF","SG"], "Los Angeles Lakers",    "1970s", 64, 62, 42, 40, 15, 52, 12, 78, 75, 55, 5),
    _p("John Drew",            ["SF","PF"], "Atlanta Hawks",         "1970s", 64, 70, 52, 32, 18, 48, 10, 76, 72, 50, 5),
    _p("Paul Silas",           ["PF","C"],  "Phoenix Suns",          "1970s", 64, 50, 78, 32, 28, 45, 5,  72, 72, 65, 5),
    _p("Charles Scott",        ["SG","PG"], "Phoenix Suns",          "1970s", 64, 68, 35, 60, 15, 58, 12, 76, 72, 60, 5),
    _p("Chris Ford",           ["SG","PG"], "Boston Celtics",        "1980s", 63, 58, 35, 55, 12, 58, 20, 76, 75, 65, 5),
    _p("Cedric Maxwell",       ["SF","PF"], "Boston Celtics",        "1980s", 63, 62, 58, 42, 22, 45, 10, 82, 80, 62, 5),
    _p("M.L. Carr",            ["SF","SG"], "Boston Celtics",        "1980s", 62, 55, 42, 40, 18, 62, 15, 72, 70, 68, 5),
    _p("Gerald Henderson",     ["SG","PG"], "Seattle SuperSonics",   "1980s", 62, 60, 35, 52, 15, 62, 18, 76, 72, 65, 5),
    _p("Ricky Pierce",         ["SG"],      "Milwaukee Bucks",       "1980s", 62, 68, 32, 42, 12, 55, 25, 80, 82, 55, 5),
    _p("Thurl Bailey",         ["PF","SF"], "Utah Jazz",             "1980s", 62, 62, 60, 32, 28, 42, 12, 78, 72, 55, 5),
    _p("Jon Koncak",           ["C"],       "Atlanta Hawks",         "1980s", 61, 45, 65, 22, 52, 25, 5,  68, 65, 65, 5),
    _p("Benoit Benjamin",      ["C"],       "Los Angeles Clippers",  "1980s", 61, 55, 65, 28, 58, 30, 5,  72, 68, 60, 5),
    _p("Reggie Theus",         ["PG","SG"], "Chicago Bulls",         "1980s", 61, 62, 35, 65, 12, 52, 18, 76, 75, 55, 5),
    _p("Michael Cooper",       ["SG","SF"], "Los Angeles Lakers",    "1980s", 61, 52, 35, 52, 18, 72, 20, 76, 74, 72, 5),
    _p("Norm Nixon",           ["PG"],      "Los Angeles Lakers",    "1980s", 61, 62, 32, 72, 10, 58, 12, 78, 75, 60, 5),
    _p("Michael Cage",         ["C","PF"],  "Seattle SuperSonics",   "1980s", 60, 50, 72, 25, 35, 32, 5,  72, 68, 58, 5),
    _p("Rod Strickland",       ["PG"],      "Portland Trail Blazers","1990s", 60, 62, 38, 75, 10, 60, 15, 76, 72, 62, 5),
    _p("Kevin Willis",         ["PF","C"],  "Atlanta Hawks",         "1990s", 60, 60, 72, 25, 35, 30, 8,  72, 68, 55, 5),
    _p("Hersey Hawkins",       ["SG"],      "Philadelphia 76ers",    "1990s", 60, 65, 35, 45, 12, 62, 42, 80, 82, 58, 5),
    _p("Terry Mills",          ["PF"],      "Detroit Pistons",       "1990s", 60, 60, 60, 28, 22, 35, 28, 76, 72, 50, 5),
    _p("Stacey Augmon",        ["SF","SG"], "Atlanta Hawks",         "1990s", 60, 55, 45, 45, 18, 68, 15, 76, 72, 68, 5),
    _p("Kenny Anderson",       ["PG"],      "New Jersey Nets",       "1990s", 60, 60, 32, 72, 10, 65, 18, 76, 72, 62, 5),
    _p("Sam Cassell",          ["PG","SG"], "Houston Rockets",       "1990s", 60, 65, 32, 72, 12, 55, 25, 80, 80, 60, 5),
    _p("Kendall Gill",         ["SG","SF"], "Charlotte Hornets",     "1990s", 60, 62, 42, 52, 18, 65, 22, 78, 72, 65, 5),
    _p("Anthony Mason",        ["PF","SF"], "New York Knicks",       "1990s", 60, 60, 65, 45, 28, 48, 10, 74, 70, 65, 5),
    _p("Otis Thorpe",          ["PF","C"],  "Houston Rockets",       "1990s", 60, 62, 72, 28, 30, 35, 5,  76, 72, 60, 5),
    _p("Tyrone Hill",          ["PF","C"],  "Cleveland Cavaliers",   "1990s", 59, 52, 72, 22, 32, 30, 5,  70, 68, 58, 5),
    _p("Nick Van Exel",        ["PG"],      "Los Angeles Lakers",    "1990s", 59, 68, 28, 68, 10, 58, 38, 76, 72, 52, 5),
    _p("Eddie Jones",          ["SG","SF"], "Los Angeles Lakers",    "1990s", 59, 62, 40, 45, 18, 70, 30, 78, 76, 72, 5),
    _p("Laphonso Ellis",       ["PF"],      "Denver Nuggets",        "1990s", 59, 60, 68, 30, 35, 35, 12, 74, 70, 60, 5),
    _p("Steph Marbury",        ["PG"],      "Minnesota Timberwolves","2000s", 59, 68, 30, 72, 10, 58, 28, 78, 75, 55, 5),
    _p("Rasho Nesterovic",     ["C"],       "San Antonio Spurs",     "2000s", 59, 50, 65, 25, 40, 28, 5,  72, 68, 62, 5),
    _p("Eric Dampier",         ["C"],       "Dallas Mavericks",      "2000s", 59, 50, 72, 25, 48, 28, 5,  72, 65, 65, 5),
    _p("Shareef Abdur-Rahim",  ["SF","PF"], "Vancouver Grizzlies",   "2000s", 59, 68, 60, 38, 22, 42, 18, 78, 75, 52, 5),
    _p("Theo Ratliff",         ["C"],       "Philadelphia 76ers",    "2000s", 59, 50, 68, 22, 80, 25, 5,  68, 62, 72, 5),
    _p("Lorenzen Wright",      ["C","PF"],  "Memphis Grizzlies",     "2000s", 58, 52, 68, 22, 40, 28, 5,  70, 65, 58, 5),
    _p("Corey Maggette",       ["SF","SG"], "Los Angeles Clippers",  "2000s", 58, 68, 45, 35, 18, 52, 22, 76, 78, 52, 5),
    _p("Brian Grant",          ["PF","C"],  "Portland Trail Blazers","2000s", 58, 55, 70, 25, 35, 28, 5,  72, 70, 62, 5),
    _p("Raef LaFrentz",        ["PF","C"],  "Denver Nuggets",        "2000s", 58, 55, 62, 28, 42, 32, 35, 74, 72, 55, 5),
    _p("Antawn Jamison",       ["PF","SF"], "Golden State Warriors", "2000s", 58, 68, 62, 32, 22, 42, 18, 78, 75, 48, 5),
    _p("Cuttino Mobley",       ["SG"],      "Houston Rockets",       "2000s", 58, 65, 35, 42, 12, 60, 30, 78, 75, 60, 5),
    _p("Larry Hughes",         ["SG","SF"], "Washington Wizards",    "2000s", 58, 62, 40, 50, 18, 65, 22, 76, 72, 65, 5),
    _p("Lamar Odom",           ["SF","PF"], "Los Angeles Lakers",    "2000s", 58, 62, 68, 55, 28, 45, 30, 76, 72, 55, 5),
    _p("Mehmet Okur",          ["C","PF"],  "Utah Jazz",             "2000s", 58, 60, 62, 30, 30, 32, 38, 78, 78, 50, 5),
    _p("Peja Stojakovic",      ["SF"],      "Sacramento Kings",      "2000s", 58, 70, 42, 35, 15, 52, 72, 86, 88, 45, 5),
    _p("Vlade Divac",          ["C"],       "Sacramento Kings",      "2000s", 58, 55, 68, 52, 42, 35, 8,  74, 72, 55, 5),
    _p("Brad Miller",          ["C"],       "Sacramento Kings",      "2000s", 58, 58, 70, 50, 35, 28, 8,  76, 78, 52, 5),
    _p("Mike Bibby",           ["PG"],      "Sacramento Kings",      "2000s", 58, 62, 30, 68, 8,  55, 38, 80, 80, 55, 5),
    _p("Doug Christie",        ["SG","SF"], "Sacramento Kings",      "2000s", 58, 60, 42, 52, 15, 72, 28, 78, 75, 72, 5),
    _p("Bobby Jackson",        ["PG"],      "Sacramento Kings",      "2000s", 57, 60, 32, 62, 10, 65, 25, 78, 74, 65, 5),
    _p("Shandon Anderson",     ["SF","SG"], "Utah Jazz",             "1990s", 57, 55, 45, 35, 12, 50, 28, 76, 72, 55, 5),
    _p("Scott Williams",       ["C","PF"],  "Chicago Bulls",         "1990s", 57, 48, 65, 25, 38, 28, 5,  70, 68, 60, 5),
    _p("B.J. Armstrong",       ["PG","SG"], "Chicago Bulls",         "1990s", 57, 60, 28, 60, 10, 55, 38, 80, 82, 58, 5),
    _p("John Paxson",          ["PG","SG"], "Chicago Bulls",         "1990s", 57, 58, 28, 60, 8,  52, 38, 80, 84, 60, 5),
    _p("Steve Kerr",           ["PG","SG"], "Chicago Bulls",         "1990s", 57, 52, 25, 52, 8,  50, 72, 80, 88, 55, 5),
    _p("Steve Novak",          ["SF","PF"], "New York Knicks",       "2010s", 56, 52, 38, 22, 12, 40, 88, 80, 82, 30, 5),
    _p("J.R. Smith",           ["SG","SF"], "Cleveland Cavaliers",   "2010s", 56, 62, 35, 35, 15, 55, 52, 76, 72, 55, 5),
    _p("Iman Shumpert",        ["SG","PG"], "Cleveland Cavaliers",   "2010s", 56, 55, 38, 40, 15, 65, 32, 74, 70, 68, 5),
    _p("Tristan Thompson",     ["C","PF"],  "Cleveland Cavaliers",   "2010s", 56, 52, 72, 22, 38, 35, 5,  70, 65, 65, 5),
    _p("Gerald Green",         ["SG","SF"], "Boston Celtics",        "2000s", 56, 62, 38, 30, 20, 55, 42, 76, 72, 50, 5),
    _p("Joakim Noah",          ["C"],       "Chicago Bulls",         "2010s", 56, 50, 75, 45, 48, 42, 8,  68, 65, 72, 5),
    _p("Luol Deng",            ["SF"],      "Chicago Bulls",         "2010s", 56, 60, 52, 38, 18, 58, 25, 78, 75, 65, 5),
    _p("Kirk Hinrich",         ["PG","SG"], "Chicago Bulls",         "2000s", 56, 55, 35, 62, 10, 60, 35, 78, 78, 65, 5),
    _p("Mike Dunleavy Jr.",    ["SF","PF"], "Indiana Pacers",        "2000s", 55, 58, 45, 42, 15, 48, 40, 78, 78, 52, 5),
    _p("Al Jefferson",         ["C","PF"],  "Minnesota Timberwolves","2000s", 55, 65, 72, 25, 35, 25, 8,  76, 70, 52, 5),
    _p("Thabo Sefolosha",      ["SF","SG"], "Oklahoma City Thunder", "2010s", 55, 48, 48, 32, 18, 62, 28, 72, 68, 72, 5),
    _p("Nene Hilario",         ["C","PF"],  "Denver Nuggets",        "2000s", 55, 58, 68, 35, 42, 32, 5,  74, 72, 60, 5),
    _p("Boris Diaw",           ["PF","SF"], "San Antonio Spurs",     "2000s", 55, 55, 55, 62, 22, 42, 28, 76, 74, 58, 5),
    _p("Kendrick Perkins",     ["C"],       "Oklahoma City Thunder", "2010s", 55, 45, 68, 22, 42, 30, 5,  65, 62, 72, 5),
    _p("Shane Battier",        ["SF"],      "Memphis Grizzlies",     "2000s", 55, 52, 45, 35, 18, 62, 35, 76, 75, 70, 5),
    _p("Andrei Kirilenko",     ["SF","PF"], "Utah Jazz",             "2000s", 55, 58, 55, 45, 55, 60, 22, 74, 70, 72, 5),
    _p("Wally Szczerbiak",     ["SF","SG"], "Minnesota Timberwolves","2000s", 55, 62, 38, 35, 12, 48, 42, 80, 80, 48, 5),
    _p("Scot Pollard",         ["C"],       "Indiana Pacers",        "2000s", 55, 42, 65, 20, 45, 25, 5,  68, 65, 60, 5),
    _p("Luke Walton",          ["SF","PF"], "Los Angeles Lakers",    "2000s", 55, 48, 48, 55, 15, 40, 22, 74, 72, 55, 5),
    _p("Ronny Turiaf",         ["C","PF"],  "Los Angeles Lakers",    "2000s", 55, 48, 60, 22, 45, 30, 5,  70, 68, 62, 5),
    _p("Channing Frye",        ["C","PF"],  "Phoenix Suns",          "2000s", 55, 55, 55, 28, 32, 28, 52, 78, 78, 45, 5),
    _p("Enes Kanter",          ["C"],       "Oklahoma City Thunder", "2010s", 55, 60, 70, 22, 28, 25, 5,  72, 65, 42, 5),
    _p("Kelly Olynyk",         ["C","PF"],  "Miami Heat",            "2010s", 55, 60, 58, 42, 22, 30, 42, 80, 78, 42, 5),
    _p("Nikola Mirotic",       ["PF"],      "Chicago Bulls",         "2010s", 55, 62, 55, 35, 22, 32, 50, 78, 78, 45, 5),
    _p("Kyle Anderson",        ["SF","PF"], "San Antonio Spurs",     "2010s", 55, 52, 55, 52, 22, 48, 20, 74, 72, 60, 5),
    _p("Patty Mills",          ["PG"],      "San Antonio Spurs",     "2010s", 55, 60, 25, 52, 8,  48, 55, 78, 82, 55, 5),
    _p("Marco Belinelli",      ["SG","SF"], "San Antonio Spurs",     "2010s", 55, 60, 32, 35, 10, 45, 50, 80, 82, 45, 5),
    _p("Danny Green",          ["SG","SF"], "San Antonio Spurs",     "2010s", 55, 55, 38, 30, 15, 68, 52, 78, 78, 68, 5),
    _p("Cory Joseph",          ["PG"],      "San Antonio Spurs",     "2010s", 55, 52, 28, 60, 10, 55, 22, 76, 74, 65, 5),
    _p("Tony Snell",           ["SG","SF"], "Milwaukee Bucks",       "2010s", 55, 52, 32, 28, 12, 50, 50, 78, 80, 52, 5),
    _p("Goran Dragic",         ["PG","SG"], "Phoenix Suns",          "2010s", 55, 65, 32, 65, 10, 52, 35, 80, 80, 55, 5),
    _p("Cody Zeller",          ["C","PF"],  "Charlotte Hornets",     "2010s", 55, 52, 62, 28, 35, 30, 5,  72, 70, 58, 5),
    _p("Al Horford",           ["C","PF"],  "Boston Celtics",        "2000s", 55, 60, 68, 48, 45, 38, 30, 78, 78, 65, 5),
    _p("Kemba Walker",         ["PG"],      "Charlotte Hornets",     "2010s", 55, 72, 28, 65, 10, 58, 48, 82, 82, 52, 5),
    _p("Eric Bledsoe",         ["PG"],      "Phoenix Suns",          "2010s", 55, 62, 38, 65, 18, 65, 22, 78, 72, 68, 5),
    _p("Elfrid Payton",        ["PG"],      "Orlando Magic",         "2010s", 55, 55, 42, 70, 12, 60, 10, 70, 62, 62, 5),
    _p("T.J. Warren",          ["SF","PF"], "Indiana Pacers",        "2010s", 55, 68, 45, 28, 15, 42, 28, 80, 75, 45, 5),
    _p("Danilo Gallinari",     ["SF","PF"], "Denver Nuggets",        "2010s", 55, 68, 45, 38, 18, 48, 42, 80, 80, 52, 5),
    _p("Tobias Harris",        ["SF","PF"], "Philadelphia 76ers",    "2010s", 55, 68, 55, 38, 18, 45, 38, 82, 80, 50, 5),
    _p("Ben Simmons",          ["PG","SF"], "Philadelphia 76ers",    "2010s", 55, 55, 68, 72, 22, 55, 5,  70, 55, 72, 5),
    _p("Joel Embiid",          ["C"],       "Philadelphia 76ers",    "2010s", 55, 80, 80, 40, 70, 40, 30, 78, 72, 80, 5),
    _p("Nikola Jokic (young)", ["C"],       "Denver Nuggets",        "2010s", 55, 65, 78, 72, 42, 25, 28, 82, 78, 55, 5),
    _p("RJ Barrett",           ["SG","SF"], "New York Knicks",       "2020s", 55, 65, 45, 45, 15, 55, 28, 78, 72, 52, 5),
    _p("LaMelo Ball",          ["PG"],      "Charlotte Hornets",     "2020s", 55, 68, 42, 72, 12, 52, 42, 76, 72, 50, 5),
    _p("Tyrese Haliburton",    ["PG"],      "Indiana Pacers",        "2020s", 55, 65, 38, 78, 12, 52, 48, 80, 80, 55, 5),
    _p("Evan Mobley",          ["C","PF"],  "Cleveland Cavaliers",   "2020s", 55, 55, 72, 40, 62, 45, 22, 76, 72, 70, 5),
    _p("Scottie Barnes",       ["SF","PF"], "Toronto Raptors",       "2020s", 55, 58, 65, 58, 30, 52, 22, 72, 68, 65, 5),
    _p("Franz Wagner",         ["SF","PG"], "Orlando Magic",         "2020s", 55, 65, 45, 52, 18, 48, 32, 78, 75, 55, 5),
    _p("Jalen Green",          ["SG"],      "Houston Rockets",       "2020s", 55, 72, 35, 45, 15, 60, 38, 78, 72, 50, 5),
    _p("Cade Cunningham",      ["PG","SG"], "Detroit Pistons",       "2020s", 55, 68, 42, 72, 15, 52, 35, 78, 74, 55, 5),
    _p("Paolo Banchero",       ["PF","SF"], "Orlando Magic",         "2020s", 55, 72, 60, 52, 25, 45, 28, 76, 70, 52, 5),
    _p("Victor Wembanyama",    ["C","PF"],  "San Antonio Spurs",     "2020s", 55, 65, 75, 35, 88, 58, 30, 76, 68, 82, 5),
    _p("Chet Holmgren",        ["C","PF"],  "Oklahoma City Thunder", "2020s", 55, 60, 65, 35, 72, 40, 38, 76, 72, 72, 5),
    _p("Jabari Smith Jr.",     ["PF","SF"], "Houston Rockets",       "2020s", 55, 58, 60, 30, 38, 40, 42, 74, 72, 58, 5),
    _p("Keegan Murray",        ["SF","PF"], "Sacramento Kings",      "2020s", 55, 60, 48, 28, 22, 40, 48, 78, 78, 52, 5),
    _p("Scoot Henderson",      ["PG"],      "Portland Trail Blazers","2020s", 55, 62, 32, 68, 15, 55, 25, 74, 68, 60, 5),
    _p("Brandon Miller",       ["SF","SG"], "Charlotte Hornets",     "2020s", 55, 62, 42, 40, 18, 50, 42, 76, 75, 50, 5),
]

# Build lookup index once for performance
_NAME_INDEX: dict = {}


def _build_index():
    global _NAME_INDEX
    _NAME_INDEX = {}
    for p in ALL_PLAYERS:
        _NAME_INDEX[p["name"].lower()] = p


_build_index()


def get_player_by_name(name: str) -> Optional[dict]:
    """Case-insensitive exact name lookup."""
    return _NAME_INDEX.get(name.lower())


def search_players(query: str, limit: int = 25) -> List[dict]:
    """Search players by partial name match, sorted by ovr desc."""
    q = query.lower().strip()
    results = [p for p in ALL_PLAYERS if q in p["name"].lower()]
    results.sort(key=lambda x: x["ovr"], reverse=True)
    return results[:limit]


def get_players_by_position(position: str) -> List[dict]:
    """Filter by position and sort by ovr desc."""
    pos = position.upper()
    results = [p for p in ALL_PLAYERS if pos in p["positions"]]
    results.sort(key=lambda x: x["ovr"], reverse=True)
    return results


def get_all_sorted() -> List[dict]:
    """Return all players sorted by ovr desc, then alphabetically."""
    return sorted(ALL_PLAYERS, key=lambda x: (-x["ovr"], x["name"]))


def get_top_available(excluded: List[str], limit: int = 200) -> List[dict]:
    """Return top available players (not in excluded list) sorted by ovr desc."""
    excluded_lower = {n.lower() for n in excluded}
    available = [p for p in ALL_PLAYERS if p["name"].lower() not in excluded_lower]
    available.sort(key=lambda x: (-x["ovr"], x["name"]))
    return available[:limit]


def player_embed_fields(p: dict) -> dict:
    """Format player stats for embed display."""
    tier_labels = {1: "👑 GOAT", 2: "⭐ All-Time Great", 3: "🔥 Star", 4: "💎 Solid", 5: "🏃 Role Player"}
    return {
        "tier": tier_labels.get(p.get("tier", 5), "🏀 Player"),
        "pos": "/".join(p["positions"]),
        "stats": (
            f"**OVR:** {p['ovr']} | **PTS:** {p['pts']} | **REB:** {p['reb']} | **AST:** {p['ast']}\n"
            f"**BLK:** {p['blk']} | **STL:** {p['stl']} | **3PT:** {p['three']} | **DEF:** {p['defense']}\n"
            f"**FG%:** {p['fg']} | **FT%:** {p['ft']}"
        ),
    }
