"""
NBAdex Season Simulation Engine — Elite Commentary Edition.
Category-based fantasy scoring: PTS, REB, AST, BLK, STL, 3PM, FG%, FT%
Players only do what they actually did in real life — no fake shit.
"""
import random
from typing import Dict, List, Optional, Tuple
from .players import get_player_by_name

CATEGORIES = ["pts", "reb", "ast", "blk", "stl", "three", "fg", "ft"]
CATEGORY_LABELS = {
    "pts": "📊 Points (PPG)",
    "reb": "🏀 Rebounds (RPG)",
    "ast": "🎯 Assists (APG)",
    "blk": "🚫 Blocks (BPG)",
    "stl": "🥷 Steals (SPG)",
    "three": "🔥 3-Pointers Made",
    "fg": "🎯 Field Goal %",
    "ft": "🏆 Free Throw %",
}

VARIANCE = 4  # Random noise per category per matchup

# ──────────────────────────────────────────────────────────────────────────────
# Real player profiles — accurate to actual career performance
# ──────────────────────────────────────────────────────────────────────────────

PLAYER_PROFILES: Dict[str, Dict] = {
    "Michael Jordan": {
        "strengths": "scoring, clutch shots, on-ball defense",
        "weakness": "three-point shooting (career 32.7%)",
        "signature": "the fadeaway midrange",
        "lines": [
            "Jordan took it personally. Again. He dropped 52 points on pure will.",
            "MJ hit the game-winner. Of course he did. Has he ever *not*?",
            "Jordan with that fadeaway over two defenders — nothing but net. Go home.",
            "No one on that roster could check Jordan. Not one person.",
            "His Airness was in a different dimension tonight. 48-6-6, 4 steals.",
        ],
        "weakness_lines": [
            "Jordan bricked three straight threes — he's not a three-point shooter, never was.",
        ],
        "category_dominance": {"pts": 99, "stl": 95},
    },
    "LeBron James": {
        "strengths": "playmaking, court vision, physical dominance, versatility",
        "weakness": "three-point consistency in early career",
        "signature": "the chase-down block, the freight-train drive",
        "lines": [
            "LeBron posted a 41-12-11 triple-double and made it look routine.",
            "The King is on another level right now. Physical freak. Basketball IQ off the charts.",
            "LeBron hit a pull-up triple with two men in his face. That's not fair.",
            "There is no stopping LeBron when he's locked in. You can only hope to slow him.",
            "LeBron bullied his way to the rim all night. 38 points, 14 boards, 9 dimes.",
        ],
        "category_dominance": {"pts": 92, "reb": 82, "ast": 92},
    },
    "Kareem Abdul-Jabbar": {
        "strengths": "the skyhook (literally unblockable), longevity, scoring efficiency",
        "weakness": "free throw shooting dropped late career",
        "signature": "the skyhook — no one has ever blocked it, ever",
        "lines": [
            "The Skyhook. There is no answer for it. There has never been an answer for it.",
            "Kareem dropped 38 on pure efficiency. 16-of-21 from the field. That's craft.",
            "You can't teach that skyhook. You can't defend it either. Kareem had another masterclass.",
            "The Captain is 40 years old and still doing this to people. Generational.",
        ],
        "category_dominance": {"pts": 94, "reb": 88, "blk": 88},
    },
    "Magic Johnson": {
        "strengths": "passing, leadership, fast break, IQ",
        "weakness": "three-point shooting (career 30.3% on low volume)",
        "signature": "no-look passes, running the Showtime fast break",
        "lines": [
            "Magic with the no-look over his shoulder — his teammate didn't even see it coming. The crowd did.",
            "Showtime. Pure Showtime. Magic ran this team like a maestro.",
            "22 assists tonight. TWENTY-TWO. Magic Johnson is simply not human.",
            "Magic made everyone on his team better just by being on the floor. You feel it.",
        ],
        "category_dominance": {"ast": 98, "pts": 82},
    },
    "Wilt Chamberlain": {
        "strengths": "scoring, rebounding, physical dominance — statistically unprecedented",
        "weakness": "free throw shooting (career 51.1%) — opponents fouled him intentionally",
        "signature": "100-point game, 55-rebound game, statistical absurdity",
        "lines": [
            "Wilt had 42 points and 28 rebounds. These are real numbers. Actual numbers.",
            "Nobody could stop Wilt inside. Nobody. He did whatever he wanted.",
            "Wilt was getting fouled on purpose at the line — and still putting up 40.",
            "The man averaged 50 points and 25 rebounds for an ENTIRE SEASON. Let that sink in.",
        ],
        "weakness_lines": [
            "Wilt went 3-of-12 from the free throw line. Career 51.1% — teams fouled him all night and it worked.",
            "Hack-a-Wilt is very real. He's going to the line and throwing bricks.",
        ],
        "category_dominance": {"pts": 96, "reb": 99},
    },
    "Larry Bird": {
        "strengths": "shooting, passing, clutch, trash talking, IQ",
        "weakness": "athleticism, back injuries late career",
        "signature": "telling defenders where he was going, then doing it anyway",
        "lines": [
            "Bird told the defender which hand he was going to use. Hit the shot. Said 'told you.'",
            "Larry Legend with the game-winner. He does this. Consistently. Infuriatingly.",
            "Bird called his shot from half-court in warmups. Drained it. This actually happened.",
            "44-14-12 with 6 steals. Bird was the most complete small forward who ever lived.",
        ],
        "category_dominance": {"pts": 90, "reb": 80, "ast": 85, "three": 65},
    },
    "Shaquille O'Neal": {
        "strengths": "pure physical dominance, unstoppable in the paint",
        "weakness": "free throw shooting (career 52.7%) — teams literally fouled him on purpose",
        "signature": "the Shaq Attack, breaking backboards, making grown men look like children",
        "lines": [
            "Shaq backed down his defender, spun, and dunked on two people. There's no stopping that.",
            "Hack-a-Shaq is in full effect. He's going to the line. This is painful to watch.",
            "Shaq was unstoppable in the paint tonight. 42 points, 18 rebounds, 5 blocks.",
            "That man just posterized an entire defense. Shaq is a force of nature.",
        ],
        "weakness_lines": [
            "Shaq is 4-of-14 from the free throw line. Teams are fouling him intentionally. Career 52.7% — this is a known weakness.",
        ],
        "category_dominance": {"pts": 96, "reb": 90, "blk": 85},
    },
    "Tim Duncan": {
        "strengths": "fundamentals, two-way play, playoff performance, consistency",
        "weakness": "no three-point shot whatsoever",
        "signature": "the bank shot, staying in position, doing the right thing every single time",
        "lines": [
            "Tim Duncan with the bank shot. Fundamental. Efficient. Unstoppable.",
            "The Big Fundamental doesn't need flash. He just wins. Quietly. Every time.",
            "Duncan dropped 28-14 and blocked 4 shots. He's been doing this for 19 years.",
            "The perfect player. No weaknesses, no ego, just winning.",
        ],
        "category_dominance": {"reb": 90, "blk": 88, "def": 92},
    },
    "Kobe Bryant": {
        "strengths": "scoring, shot creation, clutch, Mamba mentality",
        "weakness": "shot volume (can force shots), 3-of-24 moments exist",
        "signature": "the fadeaway, the turnaround, the 3:00am workout",
        "lines": [
            "Kobe Bryant does not care who's guarding him. 40 points on pure obsession.",
            "The Mamba hit a fadeaway over three defenders and SCREAMED. That's the mentality.",
            "Kobe hasn't slept in two days and still dropped 38. The man is not normal.",
            "Cold. Calculated. Ruthless. Kobe Bryant ate your defense alive and smiled doing it.",
        ],
        "weakness_lines": [
            "Kobe is forcing it tonight — 8-of-26 from the field. The Mamba has bad nights too.",
        ],
        "category_dominance": {"pts": 95, "stl": 88},
    },
    "Bill Russell": {
        "strengths": "defense, shot-blocking, rebounding, winning (11 RINGS)",
        "weakness": "scoring (career 15.1 PPG — he was never the offensive option)",
        "signature": "the block that changed the game, winning at all costs",
        "lines": [
            "Russell blocked four shots in a row. He is the greatest defensive player who ever lived.",
            "Bill Russell has 11 championships. Eleven. Let every other GOAT debate end there.",
            "Russell controlled the game without scoring 20 points. That's how dominant his defense was.",
            "He didn't need to score 30. He just needed to make sure nobody else did either.",
        ],
        "weakness_lines": [
            "Russell went 5-of-14 from the field — but had 22 rebounds and 6 blocks. He doesn't need to score.",
        ],
        "category_dominance": {"reb": 97, "blk": 94, "def": 98},
    },
    "Stephen Curry": {
        "strengths": "three-point shooting (greatest of all time), handles, pull-up range",
        "weakness": "size (6'2\"), interior defense",
        "signature": "logo threes, 400 three-pointers in a season, changing how basketball is played",
        "lines": [
            "Curry just hit a three from the Warriors logo. He was barely past half court. Sit down.",
            "13 three-pointers. In one game. This man changed basketball forever and he's not done.",
            "Steph pulled up from 35 feet with a hand in his face. It went in. The crowd lost its mind.",
            "No one in basketball history has shot it like this. Not even close. Stephen Curry is one of a kind.",
        ],
        "category_dominance": {"three": 99, "pts": 90, "fg": 88},
    },
    "Kevin Durant": {
        "strengths": "shooting over anyone, unstoppable scoring, shot creation at 7 feet",
        "weakness": "playoff record before GSW, decision-making",
        "signature": "step-back three at 7 feet, unguardable combination of size and skill",
        "lines": [
            "Kevin Durant stepped back and hit a three over a 6'8\" defender. You can't teach 7 feet.",
            "KD dropped 54 points on 60% shooting. Nobody can guard him. It's a reach-in-and-steal situation.",
            "Durant is 7-foot-nothing and can do everything. Score, rebound, pass, defend. Unreal talent.",
            "There is no legal defensive scheme that stops Kevin Durant when he's like this.",
        ],
        "category_dominance": {"pts": 98, "fg": 90, "three": 80},
    },
    "Hakeem Olajuwon": {
        "strengths": "footwork, Dream Shake, blocks, interior scoring",
        "weakness": "era-specific — competed before modern big man training",
        "signature": "the Dream Shake — nobody has ever mastered post footwork like this man",
        "lines": [
            "The Dream Shake. Nobody — NOBODY — has ever had footwork like Hakeem Olajuwon.",
            "Hakeem swatted three shots in a row and made it look elegant. Absolutely savage.",
            "Dream Shake, Dream Shake, block, Dream Shake. Hakeem runs the paint.",
            "Olajuwon's footwork is the stuff of legend. Pure artistry in the post.",
        ],
        "category_dominance": {"blk": 97, "pts": 85, "reb": 88},
    },
    "Giannis Antetokounmpo": {
        "strengths": "athleticism, rim attacks, defense, rebounding, improved mid-range",
        "weakness": "three-point shooting (career ~28%), FT% was criticized early career",
        "signature": "the Euro step at full speed, crashing the offensive glass",
        "lines": [
            "Giannis took three dribbles from half-court and dunked. This man has Stretch Armstrong arms.",
            "The Greek Freak with another 40-15-8. He is a physical anomaly. Basketball shouldn't look like this.",
            "Giannis rejected three players with one swipe. His wingspan is longer than some people's entire height.",
        ],
        "weakness_lines": [
            "Giannis going to the free throw line — career 70% — teams are hacking him intentionally.",
        ],
        "category_dominance": {"reb": 90, "pts": 88, "blk": 78, "def": 90},
    },
    "Allen Iverson": {
        "strengths": "pound-for-pound greatest scorer, speed, heart, crossover",
        "weakness": "efficiency (career 42.5% FG), size",
        "signature": "the crossover, scoring 30 on any team, zero regard for physical size disadvantage",
        "lines": [
            "Allen Iverson is 6 feet tall and just scored 48 points on your best defender. Pound for pound.",
            "The crossover. AI had an answer to every close-out in history. You try to guard him, you fall over.",
            "Iverson is limping on one ankle and still dropped 35. The man is made of pure heart.",
            "He's six feet tall in the NBA and led the league in scoring 4 times. Let that register.",
        ],
        "category_dominance": {"pts": 96, "stl": 85},
    },
    "Dennis Rodman": {
        "strengths": "rebounding (7x league leader), defense, motor, hustle",
        "weakness": "scoring (career 7.3 PPG — he almost never scored), three-point shooting (nearly non-existent)",
        "signature": "crashing every board in existence, infuriating opponents, hair colors",
        "lines": [
            "Rodman had 28 rebounds tonight. Not points — rebounds. The man is a vacuum.",
            "Dennis Rodman doesn't need to score. He won 5 championships by doing what nobody else would.",
            "Rodman grabbed every single missed shot in that fourth quarter. 11 offensive boards.",
            "Zero points. 24 rebounds. 5 blocks. 8 steals. That is a Dennis Rodman game.",
        ],
        "weakness_lines": [
            "Rodman went 0-for-3 from the field — but had 19 rebounds. He is not paid to score and everyone knows it.",
            "Dennis Rodman attempting a three-pointer is against the laws of nature.",
        ],
        "category_dominance": {"reb": 98, "def": 88, "stl": 72},
    },
    "Oscar Robertson": {
        "strengths": "triple-double machine (averaged one for a season), complete player",
        "weakness": "era — limited three-point game",
        "signature": "the first true triple-double player, basketball IQ ahead of his time",
        "lines": [
            "Oscar Robertson averaged a triple-double for an entire SEASON. In 1961. Think about that.",
            "The Big O did it all — scored, rebounded, passed. The complete package before that phrase existed.",
            "Robertson with 38-14-12. He invented the triple-double. This is just normal for him.",
        ],
        "category_dominance": {"pts": 88, "ast": 92, "reb": 65},
    },
    "Chris Paul": {
        "strengths": "passing, pick-and-roll mastery, steals, leadership, IQ",
        "weakness": "injury history, late playoff exits",
        "signature": "the midrange elbow pull-up, most surgical point guard of his era",
        "lines": [
            "CP3 ran the pick-and-roll to absolute perfection. Twenty assists, zero turnovers.",
            "Chris Paul just stole the ball AGAIN. Three steals in two minutes. Annoying. Brilliant.",
            "The Point God sees the game three seconds ahead of everyone else. He's already made the pass.",
        ],
        "category_dominance": {"ast": 97, "stl": 88, "fg": 88},
    },
    "John Stockton": {
        "strengths": "all-time assists leader, all-time steals leader, efficiency, consistency",
        "weakness": "postseason success (never won a ring)",
        "signature": "the Stockton-to-Malone pick-and-roll — ran it 40,000 times and it never got old",
        "lines": [
            "Stockton-to-Malone. They've run this play since 1985 and it still works every time.",
            "Stockton is the all-time assists leader AND steals leader. Both categories. At the same time.",
            "John Stockton doesn't look like an elite NBA player. He just IS one. Consistently. For 19 seasons.",
        ],
        "category_dominance": {"ast": 98, "stl": 88},
    },
    "Nikola Jokic": {
        "strengths": "passing from center position, court vision, efficiency, IQ",
        "weakness": "athleticism, defense can be a liability against elite athletes",
        "signature": "full-court passes from the post, making 7-footers pass like point guards look normal",
        "lines": [
            "Nikola Jokic just threw a full-court bounce pass in traffic. Nobody else even SAW that option.",
            "The Joker dropped a 30-20-15 triple-double from the center position. He is redefining the position.",
            "Most centers can't pass. Jokic might be the best passer in the entire league regardless of position.",
        ],
        "category_dominance": {"reb": 90, "ast": 85, "pts": 80},
    },
    "Kawhi Leonard": {
        "strengths": "two-way dominance, shot creation, clutch shot-making, hands",
        "weakness": "load management, health",
        "signature": "the Kawhi laugh, the bouncing corner three vs Milwaukee, hand size of a velociraptor",
        "lines": [
            "Kawhi Leonard with ice in his veins. Buzzer beater. Series over. Cold as it gets.",
            "His hands are genuinely enormous. He just plucked that ball out of the air and drove for the and-one.",
            "40 points on 62% shooting. Kawhi doesn't celebrate. He barely blinks. Terrifying.",
        ],
        "category_dominance": {"pts": 85, "stl": 90, "fg": 88, "def": 92},
    },
    "Dirk Nowitzki": {
        "strengths": "one-legged fadeaway (unguardable), three-point shooting, efficiency",
        "weakness": "defense was not his strength",
        "signature": "the one-legged fadeaway from the elbow — the shot that nobody could guard, ever",
        "lines": [
            "Dirk with the one-legged fadeaway. Nobody — and I mean nobody — can guard that shot.",
            "A 7-foot German who shoots threes in rhythm and posts up. This should not exist. It does.",
            "Dirk Nowitzki single-handedly willed his team to a championship. That 2011 run was art.",
        ],
        "category_dominance": {"pts": 92, "three": 80, "fg": 90, "ft": 92},
    },
    "Gary Payton": {
        "strengths": "defense (DPOY 1996), trash talking, floor general",
        "weakness": "era — three-point game wasn't emphasized",
        "signature": "The Glove — smothering the ball-handler, making their life miserable all night",
        "lines": [
            "Gary Payton just bodied that point guard for 48 minutes. The Glove is on.",
            "Nobody in NBA history talked more trash AND backed it up better than Gary Payton.",
            "Payton's on-ball defense is suffocating. His man had 3 points in the first half.",
        ],
        "category_dominance": {"stl": 90, "ast": 85, "def": 92},
    },
    "Pete Maravich": {
        "strengths": "scoring, handles, creativity, entertainment",
        "weakness": "era, and he played in the pre-three-point era primarily",
        "signature": "no-look passes behind the back, scoring 44 PPG in college without a three-point line",
        "lines": [
            "Pistol Pete just passed the ball through two defenders' legs. I don't think he even looked.",
            "Maravich dropped 48 points. In 1976. Without a three-point line. Sit down.",
            "Pete Maravich was 30 years ahead of his time. Some of these passes shouldn't even be legal.",
        ],
        "category_dominance": {"pts": 92, "ast": 80},
    },
    "Moses Malone": {
        "strengths": "rebounding, free throw drawing, interior scoring, toughness",
        "weakness": "era-limited",
        "signature": "Fo, Fo, Fo — he predicted a sweep in the '83 playoffs and nearly delivered",
        "lines": [
            "Moses Malone grabbed 4 consecutive offensive rebounds on the same possession. He does not stop.",
            "Nobody drew fouls like Moses Malone. And nobody made more of them.",
            "Three men tried to box Malone out. He had 23 rebounds. The math doesn't add up. He doesn't care.",
        ],
        "category_dominance": {"reb": 95, "pts": 82, "ft": 80},
    },
    "Isiah Thomas": {
        "strengths": "scoring, leadership, clutch, fast break, tough",
        "weakness": "small stature, playoff rivalries with Jordan",
        "signature": "hobbled on a bad ankle, scoring 25 points in a quarter in the NBA Finals",
        "lines": [
            "Isiah Thomas is playing on a sprained ankle and just torched that defense for 38.",
            "The Bad Boys were built in Isiah Thomas's image. Tough, relentless, and always right there.",
            "Isiah had 10 assists and 5 steals. He ran that offense with his eyes closed.",
        ],
        "category_dominance": {"pts": 85, "ast": 92, "stl": 78},
    },
    "Charles Barkley": {
        "strengths": "rebounding (6'6\" leading the NBA in rebounding), scoring, physical power",
        "weakness": "championships (0 rings), turnovers",
        "signature": "being the best player at 6'6\" when everyone told him he was too small",
        "lines": [
            "Charles Barkley is 6'6\" and just out-rebounded two 7-footers. The Round Mound is relentless.",
            "Barkley posted 30 points and 20 rebounds. He's 250 pounds and moves like a bullet.",
            "Everybody said Chuck was too small to dominate. He averaged 22 and 12 for his career. Now what?",
        ],
        "category_dominance": {"pts": 88, "reb": 90},
    },
    "Scottie Pippen": {
        "strengths": "defense, versatility, playmaking, two-way excellence",
        "weakness": "ISO scoring isn't his strength, migraine headaches at bad times",
        "signature": "guarding the best opposing player every night, making Jordan's Bulls actually work",
        "lines": [
            "Scottie Pippen guarded four different positions in one game. He's the ultimate two-way wing.",
            "Without Pippen, Jordan has no dynasty. Pippen was the engine. Jordan was the star.",
            "Pippen with 22-8-9 and 4 steals. He is the most underrated great player of all time.",
        ],
        "category_dominance": {"stl": 88, "ast": 80, "def": 92},
    },
    "David Robinson": {
        "strengths": "athleticism, defense, versatility, scoring, blocks",
        "weakness": "Hakeem in '95 playoffs exposed him at times",
        "signature": "the Admiral — former Navy officer, 7-foot man who runs like a shooting guard",
        "lines": [
            "David Robinson is 7 feet tall and just blocked five shots. The Admiral is dominant.",
            "Robinson scored 71 points on the last day of the season to win the scoring title. Calculated.",
            "The Admiral does it all — 30 points, 12 rebounds, 5 blocks. Elite athlete, elite player.",
        ],
        "category_dominance": {"pts": 82, "reb": 85, "blk": 88, "def": 88},
    },
    "Kevin Garnett": {
        "strengths": "defense, intensity, versatility, communication, fire",
        "weakness": "couldn't do it alone in Minnesota for years",
        "signature": "the pregame ritual, the intensity, 'ANYTHING IS POSSIBLE'",
        "lines": [
            "Kevin Garnett was not playing basketball tonight. He was at war. There's a difference.",
            "KG locked down three different positions and talked through every possession. Non-stop fire.",
            "28-14 with a chase-down block. Garnett plays every minute like it's Game 7 of the Finals.",
        ],
        "category_dominance": {"reb": 90, "blk": 88, "def": 92, "stl": 72},
    },
    "Dwyane Wade": {
        "strengths": "attacking the rim, clutch, athleticism, leadership",
        "weakness": "three-point shooting (career 29.8%)",
        "signature": "the slithering left-hand layup, drawing contact on impossible drives",
        "lines": [
            "Dwyane Wade is getting to the rim at will. Nobody can stay in front of him.",
            "Flash just drew his 12th foul. He finds contact on every drive. Elite skill.",
            "Wade dropped 40 in the Finals. He does this. He's always done this in big moments.",
        ],
        "category_dominance": {"pts": 88, "blk": 55, "stl": 80},
    },
    "James Harden": {
        "strengths": "isolation scoring, step-back three, free throw drawing",
        "weakness": "defense, playoff exits, step-back is now contested better",
        "signature": "the step-back three, going to the line 20 times a game, Euro step",
        "lines": [
            "Harden with the step-back three. It doesn't matter how well you're guarding him.",
            "James Harden just drew his 15th foul of the night. He is an absolute nightmare to guard.",
            "36 points, 11 assists. Harden runs the half-court offense better than almost anyone alive.",
        ],
        "category_dominance": {"pts": 92, "ast": 82, "ft": 88},
    },
    "Kyrie Irving": {
        "strengths": "ball handling, finishing, layup package, shot-making",
        "weakness": "playmaking compared to elite PGs, availability",
        "signature": "the impossible floater, crossovers in traffic, knife-edge finishing",
        "lines": [
            "Kyrie Irving just finished through three defenders with his left hand while falling away. That's a skill.",
            "The ball handling is absurd. He's an artist with the basketball.",
            "Kyrie dropped 43 on 58% shooting. When he's dialed in, nobody can guard him one-on-one.",
        ],
        "category_dominance": {"pts": 88, "fg": 90},
    },
    "Damian Lillard": {
        "strengths": "deep three-point range, clutch shots, loyalty, PG scoring",
        "weakness": "team around him for most of his career",
        "signature": "logo threes, buzzer beaters from the fourth quarter halfway line",
        "lines": [
            "Damian Lillard hit a three from 38 feet with a hand in his face. Goodnight.",
            "Dame Time has arrived. 44 points in the fourth quarter. You should've guarded the logo.",
            "Nobody in the league hits from this range consistently. Lillard changed the definition of 'open.'",
        ],
        "category_dominance": {"pts": 90, "three": 85, "ft": 88},
    },
}

# Category-specific commentary lines (used when no player profile matches)
CATEGORY_COMMENTARY = {
    "pts": [
        "{w} was putting up BUCKETS. {top} was unconscious from the field.",
        "The scoring category wasn't close — {w} shot their way to a dominant win.",
        "{w} outscored {l} at will. {top} leading the charge with a vintage performance.",
    ],
    "reb": [
        "{w} owned the glass completely. {top} was a wrecking ball on the boards.",
        "Rebounding? Not even a conversation. {w} dominated every missed shot.",
        "{w} crashed the offensive boards relentlessly — second-chance points everywhere.",
    ],
    "ast": [
        "{w} ran the offense like a well-oiled machine. {top} orchestrating everything.",
        "The passing game was a different level — {w} moved the ball with precision.",
        "{top} had eyes in the back of their head tonight. {w} absolutely dominated assists.",
    ],
    "blk": [
        "{w} turned the paint into a no-fly zone. {top} was swatting everything.",
        "The rim protection was elite — {w} made their opponents think twice going inside.",
        "{top} blocked everything that came near the basket. {l} stopped going inside in the second half.",
    ],
    "stl": [
        "{w} was picking pockets all night. {top} was absolutely predatory on defense.",
        "The ball security for {l}? Nonexistent. {w} was hunting for turnovers.",
        "{top} with hands everywhere — {w} turned defense into offense all night.",
    ],
    "three": [
        "{w} was raining threes from every corner. {l} had no answer for the shooting.",
        "The three-point category was one-sided — {w} bombed away from deep.",
        "{top} was on fire from beyond the arc. {w} won the perimeter battle decisively.",
    ],
    "fg": [
        "{w} was hyper-efficient from the field — smart shot selection all night.",
        "Field goal efficiency? {w} had it mastered. Every shot was a quality look.",
        "{top} picked their spots perfectly. {w} made their shots count.",
    ],
    "ft": [
        "{w} hit their free throws when it mattered. {l} left points on the board.",
        "The free throw line was where {w} sealed it — automatic from the stripe.",
        "Clutch free throws from {top} — {w} didn't blink under pressure.",
    ],
}

# ──────────────────────────────────────────────────────────────────────────────
# Roast lines for bad teams
# ──────────────────────────────────────────────────────────────────────────────

ROAST_LINES = [
    "This team looks like it was assembled by someone who drafted with their eyes closed.",
    "I've seen better rosters on a rec league team. At noon. On a Tuesday.",
    "This team's best player is a career role player. That's not a criticism — that's a eulogy.",
    "The opposing bench literally started laughing when they saw this starting lineup.",
    "This roster has more question marks than a spam email. Who approved this?",
    "Draft grade: D. The 'D' stands for 'Did you even try?'",
    "This team finished last and then looked surprised. Nobody else was.",
    "The good news: they have some hustle guys. The bad news: you need more than hustle.",
]

WINNER_CELEBRATION_LINES = [
    "Ladies and gentlemen, we have a CHAMPION.",
    "This is what dominance looks like. Book it. Done.",
    "You built the best team and now everyone knows it.",
    "The draft was won in the early rounds. This was inevitable.",
]

# ──────────────────────────────────────────────────────────────────────────────
# Core simulation functions
# ──────────────────────────────────────────────────────────────────────────────

def _get_top_player(roster: List[str], category: str) -> Optional[dict]:
    """Return the player with the highest rating in the given category."""
    best = None
    best_val = -1
    for name in roster:
        p = get_player_by_name(name)
        if p and p.get(category, 0) > best_val:
            best_val = p[category]
            best = p
    return best


def _get_team_stars(roster: List[str], n: int = 2) -> List[dict]:
    """Return top N players by overall rating."""
    players = [get_player_by_name(n) for n in roster if get_player_by_name(n)]
    players.sort(key=lambda p: p["ovr"], reverse=True)
    return players[:n]


def _player_commentary_line(player_name: str, situation: str = "general") -> str:
    """Get a real commentary line for a specific player."""
    profile = PLAYER_PROFILES.get(player_name)
    if not profile:
        return f"{player_name} came to play tonight."
    lines = profile.get("lines", [f"{player_name} delivered a stellar performance."])
    return random.choice(lines)


def _weakness_line(player_name: str) -> Optional[str]:
    """Get a weakness-revealing commentary line for a player."""
    profile = PLAYER_PROFILES.get(player_name)
    if not profile:
        return None
    wlines = profile.get("weakness_lines", [])
    return random.choice(wlines) if wlines else None


def calculate_team_scores(roster: List[str]) -> Dict[str, float]:
    """
    Calculate a team's 8-category scores.
    Starters (top 8 by OVR) weighted at 80%, bench at 20%.
    Slight variance added per category to simulate real-season noise.
    """
    players = [get_player_by_name(name) for name in roster if get_player_by_name(name)]
    if not players:
        return {cat: 45.0 for cat in CATEGORIES}

    players.sort(key=lambda x: x["ovr"], reverse=True)
    starters = players[:8]
    bench = players[8:]

    scores = {}
    for cat in CATEGORIES:
        s_avg = sum(p[cat] for p in starters) / len(starters) if starters else 45
        b_avg = sum(p[cat] for p in bench) / len(bench) if bench else 0
        score = (s_avg * 0.80 + b_avg * 0.20) if bench else s_avg
        # Variance: ±VARIANCE points simulating real-season randomness
        score += random.gauss(0, VARIANCE * 0.6)
        scores[cat] = round(max(0.0, min(99.0, score)), 2)
    return scores


def head_to_head(
    team_a_name: str, team_a_roster: List[str],
    team_b_name: str, team_b_roster: List[str],
    playoff: bool = False,
) -> Tuple[str, Dict]:
    """
    Simulate one head-to-head matchup between two teams.
    Playoff mode reduces variance (more deterministic).
    Returns winner name and detailed result dict.
    """
    # Playoff mode: run 3 simulations, take majority winner (best-of-3 mini-sim)
    if playoff:
        wins_a = 0
        wins_b = 0
        series_detail = []
        for _ in range(3):
            sa = calculate_team_scores(team_a_roster)
            sb = calculate_team_scores(team_b_roster)
            game_wins_a = sum(1 for cat in CATEGORIES if sa[cat] > sb[cat])
            game_wins_b = sum(1 for cat in CATEGORIES if sb[cat] > sa[cat])
            if game_wins_a >= game_wins_b:
                wins_a += 1
            else:
                wins_b += 1
            series_detail.append((sa, sb, game_wins_a, game_wins_b))
        # Use the scores from the last game for category detail
        scores_a, scores_b, gwa, gwb = series_detail[-1]
    else:
        scores_a = calculate_team_scores(team_a_roster)
        scores_b = calculate_team_scores(team_b_roster)
        wins_a = 0
        wins_b = 0

    cat_wins_a = 0
    cat_wins_b = 0
    category_results = {}

    for cat in CATEGORIES:
        a_val = scores_a[cat]
        b_val = scores_b[cat]
        if a_val > b_val:
            cat_wins_a += 1
            category_results[cat] = (CATEGORY_LABELS[cat], a_val, b_val, team_a_name)
        elif b_val > a_val:
            cat_wins_b += 1
            category_results[cat] = (CATEGORY_LABELS[cat], a_val, b_val, team_b_name)
        else:
            tied_winner = random.choice([team_a_name, team_b_name])
            if tied_winner == team_a_name:
                cat_wins_a += 1
            else:
                cat_wins_b += 1
            category_results[cat] = (CATEGORY_LABELS[cat], a_val, b_val, tied_winner)

    if not playoff:
        wins_a = cat_wins_a
        wins_b = cat_wins_b

    if wins_a > wins_b or (wins_a == wins_b and cat_wins_a >= cat_wins_b):
        winner = team_a_name
    else:
        winner = team_b_name

    return winner, {
        "scores_a": scores_a,
        "scores_b": scores_b,
        "wins_a": wins_a,
        "wins_b": wins_b,
        "cat_wins_a": cat_wins_a,
        "cat_wins_b": cat_wins_b,
        "categories": category_results,
        "winner": winner,
        "playoff": playoff,
    }


def _generate_matchup_commentary(
    winner_name: str, loser_name: str,
    winner_roster: List[str], loser_roster: List[str],
    result: Dict, playoff: bool = False,
) -> str:
    """Generate elite, player-specific commentary for a matchup."""
    lines = []

    # Find the best player on the winning team
    winner_stars = _get_team_stars(winner_roster, n=2)
    loser_stars = _get_team_stars(loser_roster, n=1)

    top_winner = winner_stars[0] if winner_stars else None
    top_loser = loser_stars[0] if loser_stars else None

    # Opening line
    if playoff:
        openings = [
            f"**{winner_name}** eliminated **{loser_name}** in brutal fashion.",
            f"**{winner_name}** sent **{loser_name}** packing. No mercy.",
            f"It's over for **{loser_name}**. **{winner_name}** advances.",
        ]
    else:
        openings = [
            f"**{winner_name}** def. **{loser_name}** ({result['cat_wins_a']}-{result['cat_wins_b']} categories)",
            f"**{winner_name}** took it from **{loser_name}** — dominant performance.",
        ]
    lines.append(random.choice(openings))

    # Top player highlight
    if top_winner:
        player_line = _player_commentary_line(top_winner["name"])
        lines.append(f"> {player_line}")

    # Category breakdown — find the most lopsided category
    best_cat = None
    best_margin = -1
    for cat, (label, val_a, val_b, cat_winner) in result["categories"].items():
        if cat_winner == winner_name:
            margin = abs(val_a - val_b)
            if margin > best_margin:
                best_margin = margin
                best_cat = (cat, label, val_a, val_b)

    if best_cat:
        cat_key, cat_label, w_val, l_val = best_cat
        cat_top = _get_top_player(winner_roster, cat_key)
        cat_top_name = cat_top["name"] if cat_top else winner_name
        cat_templates = CATEGORY_COMMENTARY.get(cat_key, ["{w} dominated {l} in this area."])
        template = random.choice(cat_templates)
        cat_line = template.format(w=winner_name, l=loser_name, top=cat_top_name)
        lines.append(cat_line)

    # Occasional weakness callout for losing team's star
    if top_loser:
        wline = _weakness_line(top_loser["name"])
        if wline and random.random() < 0.55:
            lines.append(f"> ⚠️ {wline}")

    return "\n".join(lines)


def _generate_season_moments(
    teams: Dict[str, List[str]],
    standings: Dict[str, Dict],
    matchups: List[Dict],
) -> List[str]:
    """Generate 4-5 dramatic regular season highlight moments."""
    moments = []
    team_names = list(teams.keys())

    # Pick 4-5 interesting matchups to highlight
    interesting = sorted(
        matchups,
        key=lambda m: abs(m["cat_wins_a"] - m["cat_wins_b"]) + random.random() * 2,
    )

    highlighted = random.sample(matchups, min(5, len(matchups)))

    for i, match in enumerate(highlighted):
        ta, tb = match["team_a"], match["team_b"]
        winner = match["winner"]
        loser = tb if winner == ta else ta
        w_roster = teams[winner]
        l_roster = teams[loser]

        w_stars = _get_team_stars(w_roster, n=1)
        margin = abs(match["cat_wins_a"] - match["cat_wins_b"])

        if margin >= 5:  # Blowout
            openers = [
                f"💥 **BLOWOUT** — {winner} destroyed {loser} ({match['cat_wins_a']}-{match['cat_wins_b']})",
                f"🚨 **BEATDOWN** — {loser} never had a chance against {winner}",
            ]
        elif margin <= 1:  # Nail-biter
            openers = [
                f"😤 **NAIL-BITER** — {winner} escaped {loser} by one category",
                f"🔥 **WAR** — {winner} and {loser} went to the wire. {winner} survives.",
            ]
        else:
            openers = [
                f"📌 **Week {i + 1}** — {winner} beats {loser} ({match['cat_wins_a']}-{match['cat_wins_b']} categories)",
            ]

        moment_lines = [random.choice(openers)]

        if w_stars:
            star = w_stars[0]
            moment_lines.append(f"  → {_player_commentary_line(star['name'])}")

        moments.append("\n".join(moment_lines))

    return moments


def _generate_pre_season_analysis(teams: Dict[str, List[str]]) -> List[Tuple[str, str, str]]:
    """
    Generate pre-season power rankings with real commentary.
    Returns list of (rank, team_name, analysis_text).
    """
    ranked = []
    for name, roster in teams.items():
        players = [get_player_by_name(p) for p in roster if get_player_by_name(p)]
        players.sort(key=lambda x: x["ovr"], reverse=True)
        avg_ovr = sum(p["ovr"] for p in players) / len(players) if players else 50
        ranked.append((name, roster, players, avg_ovr))

    ranked.sort(key=lambda x: x[3], reverse=True)

    result = []
    for i, (name, roster, players, avg) in enumerate(ranked):
        top2 = players[:2]
        top_names = " + ".join(p["name"] for p in top2)
        grade = grade_team(roster)

        if i == 0:
            verdicts = [
                f"Clear favorites. **{top_names}** could carry any team in this draft.",
                f"Built to win. **{top_names}** is a terrifying combination.",
                f"The team to beat. **{top_names}** — that's championship DNA.",
            ]
        elif i == 1:
            verdicts = [
                f"Strong contenders. **{top_names}** gives them real upside.",
                f"Could absolutely take it. **{top_names}** is a scary pairing.",
            ]
        elif i == len(ranked) - 1:
            if players:
                verdicts = [
                    f"Rough draft. Their best player is **{players[0]['name']}** (OVR {players[0]['ovr']}). That's concerning.",
                    f"Hard to see a path to the title. This roster needs a miracle.",
                ]
            else:
                verdicts = ["This team has nobody. Truly nobody."]
        else:
            verdicts = [
                f"Middle of the pack. **{top_names}** keeps them competitive.",
                f"Could surprise people if **{top_names}** stays healthy.",
            ]

        result.append((f"#{i+1}", name, random.choice(verdicts) + f" *(Grade: {grade})*"))

    return result


def _generate_championship_speech(
    champion: str, runner_up: str, champion_roster: List[str], result: Dict
) -> str:
    """Generate a dramatic championship ceremony speech."""
    stars = _get_team_stars(champion_roster, n=3)
    star_names = [p["name"] for p in stars]

    mvp_player = stars[0] if stars else None
    mvp_profile = PLAYER_PROFILES.get(mvp_player["name"]) if mvp_player else None

    lines = []
    lines.append(f"🏆 **{random.choice(WINNER_CELEBRATION_LINES)}**")
    lines.append(f"**{champion}** is your NBA Draft Champion!")
    lines.append("")

    if mvp_player:
        lines.append(f"**🌟 Finals MVP: {mvp_player['name']}**")
        if mvp_profile:
            lines.append(f"> {mvp_profile['strengths'].split(',')[0].strip().capitalize()} — that's what won this championship.")
        lines.append("")

    if len(star_names) >= 2:
        lines.append(f"The core of **{', '.join(star_names[:3])}** was simply too much to handle.")

    lines.append("")
    lines.append(f"**{runner_up}** put up a fight, but {champion} was the better team on paper and proved it on the simulated court.")
    lines.append("")

    # Category summary
    cat_wins = result["cat_wins_a"] if result["team_a"] == champion else result["cat_wins_b"]
    cat_losses = result["cat_wins_b"] if result["team_a"] == champion else result["cat_wins_a"]
    lines.append(f"Final Series Score: **{cat_wins}-{cat_losses}** in statistical categories.")

    return "\n".join(lines)


def _roast_last_place(last_team: str, last_roster: List[str]) -> str:
    """Brutally honest assessment of the last place team."""
    players = [get_player_by_name(p) for p in last_roster if get_player_by_name(p)]
    players.sort(key=lambda x: x["ovr"], reverse=True)
    best = players[0] if players else None

    lines = [f"💀 **Last Place: {last_team}**"]
    lines.append(random.choice(ROAST_LINES))

    if best:
        tier = best.get("tier", 5)
        if tier >= 4:
            lines.append(f"Their best player was **{best['name']}** (OVR {best['ovr']}) — a solid player on any competitive team. On this roster, though...")
        elif tier == 3:
            lines.append(f"**{best['name']}** tried their best. The problem was everything around them.")
        else:
            lines.append(f"**{best['name']}** was their anchor. That says it all.")

    return "\n".join(lines)


def simulate_season(teams: Dict[str, List[str]]) -> Dict:
    """
    Full season simulation: round-robin regular season + playoffs.
    Returns rich result dict including narrative text for display.
    """
    random.seed()
    team_names = list(teams.keys())
    standings = {
        name: {"wins": 0, "losses": 0, "cat_wins": 0, "cat_losses": 0}
        for name in team_names
    }
    all_matchups = []

    # Round-robin regular season
    for i, team_a in enumerate(team_names):
        for team_b in team_names[i + 1:]:
            winner, result = head_to_head(team_a, teams[team_a], team_b, teams[team_b])
            result["team_a"] = team_a
            result["team_b"] = team_b
            all_matchups.append(result)

            loser = team_b if winner == team_a else team_a
            standings[winner]["wins"] += 1
            standings[loser]["losses"] += 1
            for name in [team_a, team_b]:
                is_a = name == team_a
                standings[name]["cat_wins"] += result["cat_wins_a"] if is_a else result["cat_wins_b"]
                standings[name]["cat_losses"] += result["cat_wins_b"] if is_a else result["cat_wins_a"]

    # Sort by wins, tiebreak by cat_wins
    sorted_standings = sorted(
        team_names,
        key=lambda n: (standings[n]["wins"], standings[n]["cat_wins"]),
        reverse=True,
    )

    # Playoffs: top 4 teams
    playoff_teams = sorted_standings[:min(4, len(sorted_standings))]
    playoff_matchups = []
    champion = sorted_standings[0]
    runner_up = sorted_standings[1] if len(sorted_standings) > 1 else sorted_standings[0]

    if len(playoff_teams) >= 2:
        if len(playoff_teams) == 2:
            semi_pairs = [(playoff_teams[0], playoff_teams[1])]
        else:
            semi_pairs = [
                (playoff_teams[0], playoff_teams[-1]),
                (playoff_teams[1], playoff_teams[2]),
            ]

        finalists = []
        for ta, tb in semi_pairs:
            winner_sf, result = head_to_head(ta, teams[ta], tb, teams[tb], playoff=True)
            result["team_a"] = ta
            result["team_b"] = tb
            result["round"] = "Semifinal"
            loser_sf = tb if winner_sf == ta else ta
            result["commentary"] = _generate_matchup_commentary(
                winner_sf, loser_sf, teams[winner_sf], teams[loser_sf], result, playoff=True
            )
            playoff_matchups.append(result)
            finalists.append(winner_sf)

        if len(finalists) >= 2:
            winner_f, result = head_to_head(
                finalists[0], teams[finalists[0]],
                finalists[1], teams[finalists[1]],
                playoff=True,
            )
            loser_f = finalists[1] if winner_f == finalists[0] else finalists[0]
            result["team_a"] = finalists[0]
            result["team_b"] = finalists[1]
            result["round"] = "Championship"
            result["commentary"] = _generate_matchup_commentary(
                winner_f, loser_f, teams[winner_f], teams[loser_f], result, playoff=True
            )
            playoff_matchups.append(result)
            champion = winner_f
            runner_up = loser_f
        elif finalists:
            champion = finalists[0]

    # Team scores for category display
    team_scores = {name: calculate_team_scores(teams[name]) for name in team_names}

    # True MVP: player on champion's team with highest ovr OR highest combined scoring/playmaking
    mvp = None
    best_mvp_score = -1
    champ_roster = teams.get(champion, [])
    for pname in champ_roster:
        p = get_player_by_name(pname)
        if p:
            mvp_score = p["ovr"] + p["pts"] * 0.3 + p["ast"] * 0.1
            if mvp_score > best_mvp_score:
                best_mvp_score = mvp_score
                mvp = pname

    # If no champion player found, fallback to global best
    if not mvp:
        for name, roster in teams.items():
            for pname in roster:
                p = get_player_by_name(pname)
                if p and p["ovr"] > best_mvp_score:
                    best_mvp_score = p["ovr"]
                    mvp = pname

    standings_list = [
        (
            name,
            standings[name]["wins"],
            standings[name]["losses"],
            standings[name]["cat_wins"],
            standings[name]["cat_losses"],
        )
        for name in sorted_standings
    ]

    # Generate narrative
    pre_season = _generate_pre_season_analysis(teams)
    season_moments = _generate_season_moments(teams, standings, all_matchups)
    champ_final = next(
        (m for m in playoff_matchups if m.get("round") == "Championship"),
        playoff_matchups[-1] if playoff_matchups else None,
    )
    champ_speech = _generate_championship_speech(
        champion, runner_up, champ_roster, champ_final or {}
    ) if champ_final else f"🏆 **{champion}** wins the championship!"
    last_place_roast = _roast_last_place(sorted_standings[-1], teams[sorted_standings[-1]])

    return {
        "standings": standings_list,
        "matchups": all_matchups,
        "playoffs": playoff_matchups,
        "champion": champion,
        "runner_up": runner_up,
        "mvp": mvp,
        "team_scores": team_scores,
        "narrative": {
            "pre_season": pre_season,
            "season_moments": season_moments,
            "champ_speech": champ_speech,
            "last_place_roast": last_place_roast,
        },
    }


def grade_team(roster: List[str]) -> str:
    """Letter grade for a team based on average OVR and depth."""
    players = [get_player_by_name(p) for p in roster if get_player_by_name(p)]
    if not players:
        return "F"
    avg = sum(p["ovr"] for p in players) / len(players)
    top3_avg = sum(p["ovr"] for p in sorted(players, key=lambda x: x["ovr"], reverse=True)[:3]) / min(3, len(players))
    combined = avg * 0.6 + top3_avg * 0.4
    if combined >= 87:
        return "S"
    elif combined >= 82:
        return "A+"
    elif combined >= 77:
        return "A"
    elif combined >= 72:
        return "B+"
    elif combined >= 67:
        return "B"
    elif combined >= 62:
        return "C+"
    elif combined >= 57:
        return "C"
    else:
        return "D"


def compare_players(name_a: str, name_b: str) -> Optional[Dict]:
    """
    Full head-to-head comparison of two players across all categories.
    Returns structured comparison data with honest commentary.
    """
    pa = get_player_by_name(name_a)
    pb = get_player_by_name(name_b)
    if not pa or not pb:
        return None

    wins_a = 0
    wins_b = 0
    category_breakdown = {}

    for cat in CATEGORIES:
        va = pa[cat]
        vb = pb[cat]
        if va > vb:
            wins_a += 1
            category_breakdown[cat] = (CATEGORY_LABELS[cat], va, vb, pa["name"])
        elif vb > va:
            wins_b += 1
            category_breakdown[cat] = (CATEGORY_LABELS[cat], va, vb, pb["name"])
        else:
            category_breakdown[cat] = (CATEGORY_LABELS[cat], va, vb, "TIE")

    overall_winner = pa["name"] if pa["ovr"] > pb["ovr"] else (pb["name"] if pb["ovr"] > pa["ovr"] else "TIE")

    # Generate honest verdict
    profile_a = PLAYER_PROFILES.get(pa["name"], {})
    profile_b = PLAYER_PROFILES.get(pb["name"], {})

    verdict_lines = []
    if pa["ovr"] == pb["ovr"]:
        verdict_lines.append(f"Both players are rated **OVR {pa['ovr']}** — it comes down to what you need.")
    elif pa["ovr"] > pb["ovr"]:
        gap = pa["ovr"] - pb["ovr"]
        if gap >= 10:
            verdict_lines.append(f"**{pa['name']}** is significantly better overall by {gap} OVR points.")
        elif gap >= 5:
            verdict_lines.append(f"**{pa['name']}** edges it out — {gap} OVR points better overall.")
        else:
            verdict_lines.append(f"**{pa['name']}** wins narrowly — {gap} OVR point difference. Could go either way.")
    else:
        gap = pb["ovr"] - pa["ovr"]
        if gap >= 10:
            verdict_lines.append(f"**{pb['name']}** is significantly better overall by {gap} OVR points.")
        elif gap >= 5:
            verdict_lines.append(f"**{pb['name']}** edges it out — {gap} OVR points better overall.")
        else:
            verdict_lines.append(f"**{pb['name']}** wins narrowly — only {gap} OVR points.")

    if profile_a.get("strengths"):
        verdict_lines.append(f"**{pa['name']}** excels at: {profile_a['strengths']}.")
    if profile_a.get("weakness"):
        verdict_lines.append(f"Real talk — {pa['name']}'s weakness: {profile_a['weakness']}.")
    if profile_b.get("strengths"):
        verdict_lines.append(f"**{pb['name']}** excels at: {profile_b['strengths']}.")
    if profile_b.get("weakness"):
        verdict_lines.append(f"Real talk — {pb['name']}'s weakness: {profile_b['weakness']}.")

    return {
        "player_a": pa,
        "player_b": pb,
        "wins_a": wins_a,
        "wins_b": wins_b,
        "categories": category_breakdown,
        "overall_winner": overall_winner,
        "verdict": "\n".join(verdict_lines),
    }
