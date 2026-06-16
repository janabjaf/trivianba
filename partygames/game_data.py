import random

# ── Identity Theft ────────────────────────────────────────────────────────────
IDENTITY_THEFT_CHARACTERS = [
    {"name": "Dr. Elara Voss", "occupation": "Quantum Physicist", "quirk": "Corrects everyone's grammar mid-sentence"},
    {"name": "Marcus Thorn", "occupation": "Retired Spy", "quirk": "Never sits with their back to a door"},
    {"name": "Penelope Cruz-Wang", "occupation": "Professional Food Critic", "quirk": "Rates everything out of 10, including people"},
    {"name": "Admiral Reginald Fife", "occupation": "Naval Commander", "quirk": "Refers to all rooms as 'decks'"},
    {"name": "Yuki Tanaka", "occupation": "Game Show Host", "quirk": "Starts sentences with 'And the answer is…'"},
    {"name": "Desmond Okafor", "occupation": "Conspiracy Theorist", "quirk": "Whispers the important parts of sentences"},
    {"name": "Valentina Reyes", "occupation": "Opera Singer", "quirk": "Occasionally bursts into brief opera when emotional"},
    {"name": "Chad Brickwell", "occupation": "Life Coach", "quirk": "Turns every statement into a motivational quote"},
    {"name": "Iris Fong", "occupation": "Forensic Accountant", "quirk": "Estimates the cost of everything they see"},
    {"name": "Professor Aldous Grimm", "occupation": "Medieval Historian", "quirk": "Adds 'tis and 'twas to modern sentences"},
    {"name": "Blossom Hart", "occupation": "Animal Psychic", "quirk": "Narrates what nearby animals are thinking"},
    {"name": "Rex Steele", "occupation": "Stunt Double", "quirk": "Assesses every chair for weight-bearing capacity"},
    {"name": "Nadine Dupont", "occupation": "Mime Artist", "quirk": "Goes completely silent and mimes for 5-second stretches"},
    {"name": "Otto Kuhnert", "occupation": "Swiss Watchmaker", "quirk": "Finishes every statement with the exact time"},
    {"name": "Priya Malhotra", "occupation": "Reality TV Producer", "quirk": "Calls every situation 'good content'"},
    {"name": "Fletcher Doone", "occupation": "Deep Sea Diver", "quirk": "Holds breath dramatically before answering questions"},
    {"name": "Cassandra Bloom", "occupation": "Tarot Card Reader", "quirk": "Issues ominous prophecies for mundane events"},
    {"name": "Horatio Finch", "occupation": "Competitive Crossword Champion", "quirk": "Responds to questions with anagram clues"},
    {"name": "Moxie Delacroix", "occupation": "Roller Derby Champion", "quirk": "Assigns everyone a derby nickname"},
    {"name": "Zephyr Kim", "occupation": "Cloud Artist", "quirk": "Describes all situations using weather metaphors"},
]

IDENTITY_THEFT_PROMPTS = [
    "What is your most embarrassing habit that only your closest friends know about?",
    "Describe your ideal Saturday morning in detail.",
    "What is one thing you absolutely cannot live without?",
    "If you could change one thing about the world, what would it be and why?",
    "Describe the strangest dream you've ever had.",
    "What would your friends say is your biggest flaw?",
    "What's your guilty pleasure that you've never told anyone?",
    "If you had to eat the same meal every day, what would it be?",
    "Describe your personal style in three words.",
    "What do you do when nobody is watching?",
    "What is a skill you're secretly terrible at but claim to be good at?",
    "Describe the most awkward situation you've ever been in.",
]

# ── Spyfall ───────────────────────────────────────────────────────────────────
SPYFALL_LOCATIONS = [
    {"name": "Beach", "roles": ["Lifeguard", "Tourist", "Vendor", "Surfer", "Child"]},
    {"name": "Casino", "roles": ["Dealer", "Security Guard", "High Roller", "Bartender", "Cocktail Server"]},
    {"name": "Hospital", "roles": ["Surgeon", "Nurse", "Patient", "Janitor", "Visitor"]},
    {"name": "Space Station", "roles": ["Astronaut", "Commander", "Engineer", "Scientist", "Robot"]},
    {"name": "School", "roles": ["Teacher", "Student", "Principal", "Janitor", "Lunch Lady"]},
    {"name": "Restaurant", "roles": ["Chef", "Waiter", "Food Critic", "Manager", "Busboy"]},
    {"name": "Bank", "roles": ["Teller", "Manager", "Security Guard", "Loan Officer", "Robber"]},
    {"name": "Movie Set", "roles": ["Director", "Actor", "Camera Operator", "Makeup Artist", "Extra"]},
    {"name": "Submarine", "roles": ["Captain", "Navigator", "Engineer", "Cook", "Sonar Operator"]},
    {"name": "Police Station", "roles": ["Detective", "Officer", "Chief", "Suspect", "Lawyer"]},
    {"name": "Airport", "roles": ["Pilot", "Flight Attendant", "Passenger", "Security", "Baggage Handler"]},
    {"name": "Hotel", "roles": ["Concierge", "Bellhop", "Guest", "Maid", "Manager"]},
    {"name": "Museum", "roles": ["Curator", "Tour Guide", "Security Guard", "Visitor", "Restorer"]},
    {"name": "Theater", "roles": ["Director", "Actor", "Audience Member", "Stagehand", "Ticket Seller"]},
    {"name": "Circus", "roles": ["Ringmaster", "Acrobat", "Clown", "Animal Trainer", "Vendor"]},
    {"name": "Pirate Ship", "roles": ["Captain", "First Mate", "Navigator", "Gunner", "Cook"]},
    {"name": "Military Base", "roles": ["General", "Soldier", "Medic", "Engineer", "Spy"]},
    {"name": "Antarctic Station", "roles": ["Scientist", "Explorer", "Doctor", "Cook", "Mechanic"]},
    {"name": "Supermarket", "roles": ["Cashier", "Manager", "Stock Boy", "Shopper", "Security Guard"]},
    {"name": "Cruise Ship", "roles": ["Captain", "Entertainer", "Chef", "Passenger", "Sailor"]},
    {"name": "Vineyard", "roles": ["Winemaker", "Tour Guide", "Sommelier", "Grape Picker", "Chef"]},
    {"name": "Haunted House", "roles": ["Owner", "Ghost Hunter", "Skeptic", "Historian", "Terrified Guest"]},
]

# ── Werewolf ──────────────────────────────────────────────────────────────────
WEREWOLF_ROLE_DESCRIPTIONS = {
    "Werewolf":  "🐺 **Werewolf** — Each night, you and your fellow werewolves choose one player to eliminate. During the day, hide your identity and vote against villagers.",
    "Villager":  "👤 **Villager** — You have no special powers. Work together with others to identify and vote out the werewolves.",
    "Seer":      "🔮 **Seer** — Each night you may secretly investigate one player and learn whether they are a Werewolf or not.",
    "Doctor":    "⚕️ **Doctor** — Each night you may protect one player from being eliminated. You may protect yourself, but not two nights in a row.",
    "Hunter":    "🏹 **Hunter** — If you are eliminated, you immediately take down one other player of your choice.",
    "Witch":     "🧙 **Witch** — You have one heal potion (save tonight's victim) and one poison potion (kill any player tonight). Each can only be used once.",
}

WEREWOLF_ROLE_COMPOSITION = {
    4:  ["Werewolf", "Seer", "Villager", "Villager"],
    5:  ["Werewolf", "Seer", "Doctor", "Villager", "Villager"],
    6:  ["Werewolf", "Werewolf", "Seer", "Doctor", "Villager", "Villager"],
    7:  ["Werewolf", "Werewolf", "Seer", "Doctor", "Hunter", "Villager", "Villager"],
    8:  ["Werewolf", "Werewolf", "Seer", "Doctor", "Hunter", "Villager", "Villager", "Villager"],
    9:  ["Werewolf", "Werewolf", "Seer", "Doctor", "Hunter", "Witch", "Villager", "Villager", "Villager"],
    10: ["Werewolf", "Werewolf", "Werewolf", "Seer", "Doctor", "Hunter", "Witch", "Villager", "Villager", "Villager"],
}

# ── Murder Mystery ────────────────────────────────────────────────────────────
MURDER_MYSTERY_VICTIMS = ["Lord Ashworth", "Lady Pemberton", "Professor Crane", "Countess Bellamy", "Mr. Hargrove"]
MURDER_MYSTERY_WEAPONS = ["candlestick", "rope", "lead pipe", "wrench", "kitchen knife", "revolver", "poisoned wine", "fireplace poker"]
MURDER_MYSTERY_SETTINGS = [
    "a Victorian mansion during a thunderstorm",
    "a luxury cruise ship in the Mediterranean",
    "an isolated ski lodge in the Alps",
    "a grand opera house in Paris",
    "a country estate during a garden party",
]
MURDER_MYSTERY_CLUES = [
    "Muddy footprints were found leading away from the scene.",
    "A torn piece of fabric was discovered near the body.",
    "The victim's diary mentions a secret meeting tonight.",
    "A half-eaten meal suggests the victim knew their killer.",
    "A glove was found — but only one of a pair.",
    "The security camera footage has been deleted.",
    "Witnesses heard arguing two hours before the murder.",
    "A suspicious car was parked outside all evening.",
    "The victim recently changed their will.",
    "An unusual perfume/cologne was detected at the scene.",
]

# ── Auction Heist ─────────────────────────────────────────────────────────────
AUCTION_ARTIFACTS = [
    {"name": "The Crimson Diamond", "description": "A flawless 50-carat red diamond, allegedly stolen from a maharaja's vault in 1923.", "fake": False, "value": 5_000_000},
    {"name": "Napoleon's Compass", "description": "A brass pocket compass claimed to have guided Napoleon at Waterloo. Suspiciously still points south.", "fake": True, "value": 0},
    {"name": "Ancient Scroll of Wisdom", "description": "A papyrus scroll with authentic Egyptian hieroglyphs, carbon-dated to 2000 BCE.", "fake": False, "value": 750_000},
    {"name": "The Golden Mask", "description": "A gleaming burial mask said to be from an undiscovered pharaoh's tomb.", "fake": True, "value": 0},
    {"name": "Picasso's Lost Sketch", "description": "A preliminary pencil sketch for Guernica, with Pablo Picasso's own signature.", "fake": False, "value": 1_200_000},
    {"name": "Galileo's Telescope", "description": "A wooden and brass telescope bearing the initials G.G. First used to observe Jupiter's moons.", "fake": False, "value": 3_400_000},
    {"name": "The Fabergé Egg (Replica)", "description": "Advertised as original; experts on-site have spotted several anachronistic details.", "fake": True, "value": 0},
    {"name": "Viking Runestone", "description": "A carved granite stone bearing runic inscriptions from approximately 900 CE.", "fake": False, "value": 890_000},
]

# ── Chain Reaction ────────────────────────────────────────────────────────────
CHAIN_REACTION_STARTERS = [
    "A dragon lands in Times Square.",
    "All the world's coffee mysteriously disappears overnight.",
    "Dogs develop the ability to speak fluent English.",
    "The internet goes down for 48 hours worldwide.",
    "Every clock in the world resets to midnight simultaneously.",
    "It starts raining glitter globally for a full week.",
    "All mirrors begin showing what you'll look like in 10 years.",
    "Pizza is declared illegal in 47 countries.",
    "Gravity is reduced by 50% for exactly one hour.",
    "Every human being spontaneously swaps accents with a stranger.",
    "Cats are elected to all national governments simultaneously.",
    "The sun turns lime green for a day.",
    "Everyone wakes up speaking a different language.",
    "ATMs begin dispensing compliments instead of cash.",
]

# ── Time Traveler ─────────────────────────────────────────────────────────────
TIME_TRAVELER_ERAS = [
    {"name": "Ancient Egypt (1200 BCE)", "emoji": "🏺", "hint": "Pharaohs rule, pyramids are freshly built, cats are sacred"},
    {"name": "Medieval Europe (1250 CE)", "emoji": "⚔️", "hint": "Knights, feudal lords, plague is looming, no science"},
    {"name": "The Renaissance (1510 CE)", "emoji": "🎨", "hint": "Art and science flourishing, Da Vinci is alive"},
    {"name": "The Wild West (1880s)", "emoji": "🤠", "hint": "Frontier towns, outlaws, gold rush, no electricity"},
    {"name": "The Roaring Twenties (1925)", "emoji": "🎷", "hint": "Jazz, Prohibition, flappers, stock market mania"},
    {"name": "Cold War Era (1962)", "emoji": "☢️", "hint": "Space race, nuclear tension, black-and-white TV"},
    {"name": "Present Day (2024)", "emoji": "📱", "hint": "Smartphones, AI, social media, streaming services"},
    {"name": "Near Future (2055)", "emoji": "🤖", "hint": "AI governs, Mars colony exists, climate solved by tech"},
    {"name": "Far Future (2300)", "emoji": "🚀", "hint": "Interplanetary civilization, Earth is a museum planet"},
    {"name": "Distant Future (5000 CE)", "emoji": "🌌", "hint": "Humanity merged with technology, unrecognizable society"},
]

TIME_TRAVELER_SCENARIOS = [
    "An alien spacecraft lands in the middle of your town and a door opens.",
    "The government announces free unlimited clean energy for all humanity, effective tomorrow.",
    "Scientists confirm that humans are no longer aging past 30.",
    "A new social media platform allows users to read each other's minds.",
    "All animals suddenly develop human-level intelligence overnight.",
    "A time machine is put up for public auction, starting at $1.",
    "The last known ocean is discovered to contain an advanced civilization.",
    "Scientists announce they can perfectly predict the weather 100 years in advance.",
    "A global vote is called to elect a single 'World President'.",
    "A virus makes everyone forget how to use technology for 24 hours.",
]

# ── Movie Pitch ───────────────────────────────────────────────────────────────
MOVIE_GENRES = [
    "Psychological Thriller", "Romantic Comedy", "Spaghetti Western", "Found-Footage Horror",
    "Animated Musical", "Political Satire", "Documentary", "Sci-Fi Action",
    "Gothic Romance", "Buddy Cop Comedy", "Disaster Movie", "Coming-of-Age Drama",
    "Mockumentary", "Noir Mystery", "Supernatural Horror", "Sports Underdog Story",
]

MOVIE_ACTORS = [
    "Nicolas Cage", "Meryl Streep", "Dwayne Johnson", "Cate Blanchett",
    "Jim Carrey", "Viola Davis", "Keanu Reeves", "Helen Mirren",
    "Will Ferrell", "Lupita Nyong'o", "Jack Black", "Tilda Swinton",
    "Christopher Walken", "Awkwafina", "Jeff Goldblum", "Zendaya",
    "Danny DeVito", "Janelle Monáe", "Steve Buscemi", "Florence Pugh",
]

RIDICULOUS_OBJECTS = [
    "a sentient wheel of cheese",
    "a backwards clock that speeds up when touched",
    "a crying robot that never explains why",
    "a magic 8-ball that only responds in Latin",
    "a sandwich that grants wishes but only for rivals",
    "a gym bag full of unsent love letters",
    "a golden rubber duck",
    "a phone that only calls dead relatives",
    "a snowglobe containing a live miniature city",
    "a spoon that turns everything it touches into soup",
    "an alarm clock that screams compliments",
    "a library card that works in alternate dimensions",
    "a compass that always points toward drama",
    "a mirror that shows your deepest regret",
    "a briefcase full of expired coupons from the future",
]

# ── Debate Club ───────────────────────────────────────────────────────────────
DEBATE_TOPICS = [
    ("Cats make better companions than dogs", "Dogs make better companions than cats"),
    ("Remote work is better than office work", "Office work is better than remote work"),
    ("Books are better than movies for storytelling", "Movies are better than books for storytelling"),
    ("Social media has done more harm than good", "Social media has done more good than harm"),
    ("Space exploration deserves more funding", "Ocean exploration deserves more funding"),
    ("Pineapple belongs on pizza", "Pineapple does NOT belong on pizza"),
    ("Breakfast is the most important meal", "Dinner is the most important meal"),
    ("Cold showers are better than hot showers", "Hot showers are better than cold showers"),
    ("City life is superior to country life", "Country life is superior to city life"),
    ("Video games should be considered a sport", "Video games should NOT be considered a sport"),
    ("Luck matters more than skill in life", "Skill matters more than luck in life"),
    ("The journey is more important than the destination", "The destination is more important than the journey"),
]

# ── Quiplash ──────────────────────────────────────────────────────────────────
QUIPLASH_PROMPTS = [
    "The worst name for a baby",
    "A rejected superhero power",
    "The new slogan for gravity",
    "Something you should NOT bring to a job interview",
    "The worst thing to whisper to someone in an elevator",
    "A bumper sticker written by a philosophy professor",
    "The world's most boring supervillain plan",
    "A new Olympic event that should exist",
    "The worst advice column name",
    "A terrible name for a restaurant",
    "The most awkward thing to say at a wedding",
    "A fortune cookie message from a pessimist",
    "The official slogan for disappointment",
    "Something that would make a rollercoaster less fun",
    "The worst thing a GPS could say",
    "A terrible motivational poster message",
]

# ── Hot Take ──────────────────────────────────────────────────────────────────
HOT_TAKE_PROMPTS = [
    "Drop your hottest take on modern technology",
    "What's your most controversial food opinion?",
    "Share your spiciest take on pop culture",
    "Give your most unpopular opinion about social media",
    "What's an 'iconic' thing that's actually overrated?",
    "Your most controversial opinion about music",
    "Hottest take on movies or TV shows",
    "Most controversial travel opinion you hold",
    "Spiciest opinion about sports",
    "Unpopular opinion about daily habits (sleep, exercise, diet, etc.)",
]

# ── Two Truths and a Lie ──────────────────────────────────────────────────────
TWO_TRUTHS_TIPS = [
    "Make your lie believable!",
    "Mix mundane truths with wild ones to throw people off.",
    "The more specific your lie, the more convincing it sounds.",
    "Real-sounding details make the best lies.",
]

# ── Would You Rather ──────────────────────────────────────────────────────────
WOULD_YOU_RATHER_QUESTIONS = [
    ("Have the ability to fly", "Have the ability to be invisible"),
    ("Always speak the truth", "Always know when others are lying to you"),
    ("Never need to sleep again", "Never need to eat again"),
    ("Live 100 years in the past", "Live 100 years in the future"),
    ("Have unlimited money", "Have unlimited free time"),
    ("Be famous but widely disliked", "Be unknown but deeply loved"),
    ("Only be able to whisper forever", "Only be able to shout forever"),
    ("Know exactly how you'll die", "Know exactly when you'll die"),
    ("Have super strength", "Have super intelligence"),
    ("Be a master chef", "Be a world-class musician"),
    ("Speak every language fluently", "Play every instrument perfectly"),
    ("Always be cold", "Always be hot"),
    ("Fight 1 horse-sized duck", "Fight 100 duck-sized horses"),
    ("Have no past memories", "Have no future dreams"),
    ("Lose all your money", "Lose all your friends and family"),
]

# ── Trivia ────────────────────────────────────────────────────────────────────
TRIVIA_QUESTIONS = [
    # Geography
    {"q": "What is the capital of Australia?", "a": "canberra", "category": "Geography", "options": ["Sydney", "Melbourne", "Canberra", "Perth"]},
    {"q": "Which is the world's longest river?", "a": "nile", "category": "Geography", "options": ["Amazon", "Nile", "Yangtze", "Mississippi"]},
    {"q": "What country has the most natural lakes?", "a": "canada", "category": "Geography", "options": ["Russia", "Canada", "USA", "Finland"]},
    {"q": "On which continent is the Sahara Desert?", "a": "africa", "category": "Geography", "options": ["Asia", "Australia", "Africa", "South America"]},
    {"q": "What is the smallest country in the world?", "a": "vatican city", "category": "Geography", "options": ["Monaco", "Vatican City", "San Marino", "Liechtenstein"]},
    {"q": "Which mountain is the tallest in the world?", "a": "mount everest", "category": "Geography", "options": ["K2", "Kangchenjunga", "Mount Everest", "Makalu"]},
    # Science
    {"q": "What is the chemical symbol for gold?", "a": "au", "category": "Science", "options": ["Go", "Au", "Ag", "Gd"]},
    {"q": "How many bones are in the adult human body?", "a": "206", "category": "Science", "options": ["196", "206", "213", "224"]},
    {"q": "What planet is known as the Red Planet?", "a": "mars", "category": "Science", "options": ["Venus", "Jupiter", "Mars", "Saturn"]},
    {"q": "What is the speed of light (approximately)?", "a": "300000 km/s", "category": "Science", "options": ["150,000 km/s", "300,000 km/s", "500,000 km/s", "700,000 km/s"]},
    {"q": "What gas do plants absorb during photosynthesis?", "a": "carbon dioxide", "category": "Science", "options": ["Oxygen", "Nitrogen", "Carbon dioxide", "Hydrogen"]},
    {"q": "What is the powerhouse of the cell?", "a": "mitochondria", "category": "Science", "options": ["Nucleus", "Ribosome", "Mitochondria", "Golgi apparatus"]},
    # History
    {"q": "In what year did World War II end?", "a": "1945", "category": "History", "options": ["1943", "1944", "1945", "1946"]},
    {"q": "Who was the first person to walk on the moon?", "a": "neil armstrong", "category": "History", "options": ["Buzz Aldrin", "Neil Armstrong", "Yuri Gagarin", "Alan Shepard"]},
    {"q": "The Berlin Wall fell in what year?", "a": "1989", "category": "History", "options": ["1985", "1987", "1989", "1991"]},
    {"q": "Who painted the Mona Lisa?", "a": "leonardo da vinci", "category": "History", "options": ["Michelangelo", "Raphael", "Leonardo da Vinci", "Donatello"]},
    {"q": "In what year did the Titanic sink?", "a": "1912", "category": "History", "options": ["1908", "1910", "1912", "1915"]},
    # Pop Culture
    {"q": "What is the best-selling video game of all time?", "a": "minecraft", "category": "Pop Culture", "options": ["Tetris", "GTA V", "Minecraft", "Wii Sports"]},
    {"q": "How many seasons does Game of Thrones have?", "a": "8", "category": "Pop Culture", "options": ["6", "7", "8", "9"]},
    {"q": "What band was Freddie Mercury the lead singer of?", "a": "queen", "category": "Pop Culture", "options": ["The Beatles", "Queen", "Led Zeppelin", "Pink Floyd"]},
    {"q": "Who wrote Harry Potter?", "a": "j.k. rowling", "category": "Pop Culture", "options": ["J.R.R. Tolkien", "J.K. Rowling", "C.S. Lewis", "Philip Pullman"]},
    {"q": "What is the highest-grossing film of all time (not adjusted for inflation)?", "a": "avatar", "category": "Pop Culture", "options": ["Avengers: Endgame", "Titanic", "Avatar", "Star Wars: The Force Awakens"]},
    # Math & Logic
    {"q": "What is the square root of 144?", "a": "12", "category": "Math", "options": ["10", "11", "12", "13"]},
    {"q": "How many sides does a hexagon have?", "a": "6", "category": "Math", "options": ["5", "6", "7", "8"]},
    {"q": "What is 15% of 200?", "a": "30", "category": "Math", "options": ["25", "30", "35", "40"]},
    {"q": "What is the next prime number after 11?", "a": "13", "category": "Math", "options": ["12", "13", "15", "17"]},
    # Language
    {"q": "How many letters are in the English alphabet?", "a": "26", "category": "Language", "options": ["24", "25", "26", "28"]},
    {"q": "What is the most spoken language in the world by native speakers?", "a": "mandarin chinese", "category": "Language", "options": ["English", "Spanish", "Mandarin Chinese", "Hindi"]},
    {"q": "What is a group of crows called?", "a": "murder", "category": "Language", "options": ["Flock", "Gaggle", "Murder", "Pack"]},
    {"q": "What word is both a noun and a verb and contains all 5 vowels in order?", "a": "facetious", "category": "Language", "options": ["Facetious", "Pneumonia", "Sequoia", "Dialogue"]},
]

# ── Escape Room ───────────────────────────────────────────────────────────────
ESCAPE_ROOM_PUZZLES = [
    {
        "title": "🔐 The Year Lock",
        "description": "You find a 4-digit combination lock. The clue reads:\n*'The year humanity first walked on the moon.'*",
        "answer": "1969",
        "hint": "Think about famous space history — specifically Neil Armstrong."
    },
    {
        "title": "🔤 The Caesar Cipher",
        "description": "A coded message reads: **KHOOR ZRUOG**\nIt was made by shifting each letter **3 positions forward** in the alphabet.",
        "answer": "hello world",
        "hint": "Shift each letter backwards by 3. K→H, H→E, etc."
    },
    {
        "title": "🧮 The Word Number",
        "description": "A safe display reads:\n*'I am odd. Take away one letter and I become even. What am I?'*",
        "answer": "seven",
        "hint": "Think about the WORD, not the math. 'Seven' minus a letter…"
    },
    {
        "title": "🌍 The Map Clue",
        "description": "A map shows a country. Its flag features a red maple leaf on a white background flanked by red bars.",
        "answer": "canada",
        "hint": "Think North American countries and their famous national symbols."
    },
    {
        "title": "🎵 The Music Box",
        "description": "A music box plays: **Do Re Mi Fa Sol ___ Ti Do**\nWhat note fills the blank?",
        "answer": "la",
        "hint": "Solfège scale: Do Re Mi Fa Sol La Ti Do"
    },
    {
        "title": "🔢 The Missing Number",
        "description": "A keypad shows the pattern: **2, 6, 18, 54, ___**\nWhat is the next number?",
        "answer": "162",
        "hint": "Each number is multiplied by 3."
    },
    {
        "title": "🌑 The Shadow Riddle",
        "description": "Etched on the wall:\n*'I have cities, but no houses live there. I have mountains, but no trees grow there. I have water, but no fish swim there. What am I?'*",
        "answer": "map",
        "hint": "It's something you look at to find places."
    },
    {
        "title": "⚖️ The Balance Puzzle",
        "description": "Three bags of gold are labeled 3kg, 4kg, and 5kg. Which two bags combined weigh exactly **8kg**?",
        "answer": "3 and 5",
        "hint": "Simple arithmetic: which pair adds up to 8?"
    },
    {
        "title": "🕐 The Clock Code",
        "description": "An old clock is stopped at **3:15**. The clue says: *'Add the hour hand number and the minute position number together.'*\nThe minute hand at 3 position = 3. What is the code?",
        "answer": "6",
        "hint": "Hour hand = 3, minute hand position = 3. What's 3+3?"
    },
    {
        "title": "🐾 The Animal Vault",
        "description": "The vault opens when you type the animal that has the most hearts.\n*'An octopus has three hearts. A ___ also has three hearts but lives on land.'*",
        "answer": "earthworm",
        "hint": "It's a common garden creature that most people overlook."
    },
]

# ── Word Bomb ─────────────────────────────────────────────────────────────────
WORD_BOMB_COMBOS = [
    "ST", "ER", "TH", "AN", "IN", "ON", "RE", "EN", "AT", "ED",
    "AR", "OR", "IC", "AL", "NG", "LE", "OU", "IT", "HA", "ME",
    "BL", "TR", "CH", "SH", "PH", "CK", "NT", "PR", "GR", "FR",
    "OT", "EX", "IM", "UN", "CON", "PRE", "OUT", "OVE", "INT", "MAN",
]

# ── Alphabet Chain ────────────────────────────────────────────────────────────
ALPHABET_CHAIN_CATEGORIES = [
    "animals", "countries", "cities", "foods", "movies",
    "celebrity names", "video games", "sports teams", "TV shows", "brands",
    "musical artists", "types of vehicles", "things in a kitchen", "professions",
]

# ── Price Is Right ────────────────────────────────────────────────────────────
PRICE_IS_RIGHT_ITEMS = [
    {"item": "A gallon of whole milk (USA avg)", "price": 4.50, "hint": "A refrigerator staple"},
    {"item": "A large pepperoni pizza from a major chain", "price": 18.00, "hint": "America's favorite circular food"},
    {"item": "A monthly Netflix Standard subscription (USD)", "price": 15.49, "hint": "Popular streaming service"},
    {"item": "A new Apple AirPods Pro (Gen 2)", "price": 249.00, "hint": "Wireless earbuds from Apple"},
    {"item": "A brand new Honda Civic (base trim, 2024)", "price": 23_950.00, "hint": "One of the most popular sedans worldwide"},
    {"item": "A Starbucks Grande Latte (USD)", "price": 5.45, "hint": "Coffee shop classic"},
    {"item": "A round-trip flight NYC to London (economy, avg)", "price": 680.00, "hint": "Transatlantic economy travel"},
    {"item": "A brand new PlayStation 5 (disc edition)", "price": 499.99, "hint": "Sony's latest home console"},
    {"item": "A 12-pack of Coca-Cola cans", "price": 6.99, "hint": "Classic soda, bulk pack"},
    {"item": "A New York Times 1-year digital subscription", "price": 17.00, "hint": "Monthly cost of a major newspaper subscription"},
]

# ── Gladiator Draft ───────────────────────────────────────────────────────────
GLADIATOR_FIGHTERS = [
    {"name": "Thrak the Unbroken", "emoji": "🪓", "hp": 120, "atk": 18, "spd": 10, "special": "Berserker Rage (+8 atk for 2 turns)"},
    {"name": "Serpentius Rex", "emoji": "🐍", "hp": 90, "atk": 22, "spd": 16, "special": "Poison Strike (5 dmg/turn for 3 turns)"},
    {"name": "Ironwall Borin", "emoji": "🛡️", "hp": 160, "atk": 12, "spd": 7, "special": "Shield Wall (block next attack)"},
    {"name": "Quicksilver Zara", "emoji": "⚡", "hp": 80, "atk": 20, "spd": 22, "special": "Double Strike (attack twice)"},
    {"name": "The Ancient One", "emoji": "🧙", "hp": 100, "atk": 25, "spd": 11, "special": "Mystic Blast (ignores armor)"},
    {"name": "Burning Helios", "emoji": "🔥", "hp": 95, "atk": 24, "spd": 13, "special": "Inferno (area damage)"},
    {"name": "Stonefist Grak", "emoji": "🗿", "hp": 140, "atk": 16, "spd": 8, "special": "Earthquake (stuns opponent 1 turn)"},
    {"name": "Shadowblade Nyx", "emoji": "🌑", "hp": 85, "atk": 21, "spd": 19, "special": "Vanish (dodge next attack)"},
    {"name": "The Colossus", "emoji": "⚙️", "hp": 180, "atk": 14, "spd": 5, "special": "Iron Stomp (50% of opponent's HP as bonus dmg)"},
    {"name": "Stormcaller Aela", "emoji": "⛈️", "hp": 95, "atk": 20, "spd": 17, "special": "Lightning Chain (hits all remaining enemies)"},
    {"name": "Razorclaw Fenris", "emoji": "🐺", "hp": 105, "atk": 23, "spd": 15, "special": "Frenzy (attack 3x at half dmg)"},
    {"name": "The Glacial Bishop", "emoji": "❄️", "hp": 110, "atk": 17, "spd": 12, "special": "Freeze (opponent skips next turn)"},
    {"name": "Venom Queen Lyra", "emoji": "🕷️", "hp": 88, "atk": 19, "spd": 20, "special": "Web Trap (reduces opponent SPD by half)"},
    {"name": "Desert Reaper Khem", "emoji": "☀️", "hp": 100, "atk": 21, "spd": 14, "special": "Sand Blind (opponent has 50% miss chance next turn)"},
    {"name": "The Warlord Maxis", "emoji": "👑", "hp": 130, "atk": 19, "spd": 11, "special": "Rally Cry (heals 25 HP)"},
]

# ── Math Duel ─────────────────────────────────────────────────────────────────
def generate_math_question(difficulty: int):
    """Generate a math question at the given difficulty (1=easy, 2=medium, 3=hard)."""
    if difficulty == 1:
        a, b = random.randint(2, 20), random.randint(2, 20)
        op = random.choice(["+", "-", "*"])
        if op == "+":
            return f"{a} + {b}", str(a + b)
        elif op == "-":
            a, b = max(a, b), min(a, b)
            return f"{a} - {b}", str(a - b)
        else:
            a, b = random.randint(2, 12), random.randint(2, 12)
            return f"{a} × {b}", str(a * b)
    elif difficulty == 2:
        q_type = random.choice(["percent", "square", "chain"])
        if q_type == "percent":
            pct = random.choice([10, 15, 20, 25, 30, 50])
            n = random.choice([20, 40, 50, 80, 100, 120, 200])
            return f"{pct}% of {n}", str(int(pct * n / 100))
        elif q_type == "square":
            n = random.randint(3, 15)
            return f"{n}²", str(n * n)
        else:
            a, b, c = random.randint(2, 10), random.randint(2, 10), random.randint(2, 10)
            return f"{a} × {b} + {c}", str(a * b + c)
    else:
        q_type = random.choice(["power", "multi_step", "fraction"])
        if q_type == "power":
            base, exp = random.randint(2, 5), random.randint(2, 4)
            return f"{base}^{exp}", str(base ** exp)
        elif q_type == "multi_step":
            a, b, c = random.randint(5, 20), random.randint(2, 10), random.randint(2, 15)
            return f"({a} + {b}) × {c}", str((a + b) * c)
        else:
            n1, n2 = random.randint(1, 10), random.randint(1, 10)
            d = random.randint(2, 8)
            result = n1 * d + n2 * d
            return f"{n1}/{d} + {n2}/{d} (as a fraction, simplest form numerator only)", str(n1 + n2)

# ── Bingo ─────────────────────────────────────────────────────────────────────
def generate_bingo_card():
    """Generate a 5x5 bingo card with a FREE center space."""
    card = []
    ranges = [(1, 15), (16, 30), (31, 45), (46, 60), (61, 75)]
    for col_range in ranges:
        nums = random.sample(range(col_range[0], col_range[1] + 1), 5)
        card.append(nums)
    card[2][2] = "FREE"
    return card

def format_bingo_card(card, called: set):
    """Format a bingo card for display."""
    header = " B    I    N    G    O \n"
    rows = ""
    for row in range(5):
        for col in range(5):
            val = card[col][row]
            if val == "FREE" or (isinstance(val, int) and val in called):
                rows += " ✅  "
            else:
                rows += f" {str(val):>2}  "
        rows += "\n"
    return f"```\n{header}{rows}```"

def check_bingo(card, called: set):
    """Check if a bingo card has won."""
    marked = [[card[col][row] == "FREE" or (isinstance(card[col][row], int) and card[col][row] in called)
               for col in range(5)] for row in range(5)]
    for row in marked:
        if all(row):
            return True
    for col in range(5):
        if all(marked[row][col] for row in range(5)):
            return True
    if all(marked[i][i] for i in range(5)):
        return True
    if all(marked[i][4 - i] for i in range(5)):
        return True
    return False

# ── Story Time ────────────────────────────────────────────────────────────────
STORY_STARTERS = [
    "The last train of the night pulled into an empty station, and the only passenger stepped out into the fog.",
    "Nobody expected the new librarian to arrive on a motorcycle and immediately start removing books from the shelves.",
    "The message in the bottle read: 'If you find this, don't go back to your house tonight.'",
    "There was a door at the end of the hallway that nobody in the office had ever noticed before — until Tuesday.",
    "The world's best detective retired on a Monday and by Friday had been pulled into the most bizarre case of her career.",
    "It began, as most disasters do, with someone saying 'How hard could it be?'",
    "The alien looked around at Earth and pulled out a clipboard. 'Right,' it said. 'Who's in charge?'",
    "The old man claimed he'd been asleep for twenty years. The problem was, nobody in town remembered him waking up.",
]

# ── Hangman ───────────────────────────────────────────────────────────────────
HANGMAN_STAGES = [
    "```\n  +---+\n  |   |\n      |\n      |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n      |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n  |   |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n /|   |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n /    |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n / \\  |\n      |\n=========```",
]

HANGMAN_WORDS = [
    "python", "discord", "galaxy", "umbrella", "wizard", "quantum", "tornado", "dolphin",
    "keyboard", "library", "mountain", "phoenix", "rainbow", "spaghetti", "adventure",
    "chocolate", "elephant", "telescope", "mysterious", "labyrinth", "penguin", "volcano",
    "satellite", "symphony", "lighthouse", "cathedral", "paradox", "algorithm", "blueprint",
    "wilderness", "expedition", "chameleon", "constellation", "democracy",
]

# ── Codenames ─────────────────────────────────────────────────────────────────
CODENAMES_WORDS = [
    "AGENT", "AIR", "ALIEN", "ALPS", "AMAZON", "ANGEL", "ANTARCTIC", "APPLE",
    "ARCTIC", "ARM", "AZTEC", "BACK", "BALL", "BAND", "BANK", "BAR",
    "BARK", "BATTERY", "BERLIN", "BERRY", "BILL", "BLACK", "BLOCK", "BOARD",
    "BOLT", "BOMB", "BOND", "BONE", "BOOK", "BOX", "BRIDGE", "BRUSH",
    "BUCK", "BUFFALO", "BUG", "BULB", "BULL", "BURN", "BUTTON", "CANADA",
    "CAP", "CARD", "CARROT", "CASTLE", "CAT", "CAVE", "CELL", "CHAIR",
    "CHICK", "CHINA", "CHIP", "CHOCOLATE", "CHURCH", "CIRCLE", "CLIFF", "CLOCK",
    "CLOUD", "CLUB", "COAST", "COLD", "COMET", "CONTRACT", "COOK", "COPPER",
    "CORNER", "COURT", "COVER", "CRASH", "CROSS", "CUP", "CYCLE", "DANCE",
    "DATE", "DAY", "DIAMOND", "DICE", "DISH", "DOG", "DOOR", "DRAFT",
    "DRAGON", "DRAIN", "DRILL", "DRIVE", "DROP", "DRUM", "DUCK", "DUST",
]

# ── Wavelength ────────────────────────────────────────────────────────────────
WAVELENGTH_SPECTRUMS = [
    ("Cold", "Hot"),
    ("Boring", "Exciting"),
    ("Ugly", "Beautiful"),
    ("Weak", "Strong"),
    ("Quiet", "Loud"),
    ("Simple", "Complex"),
    ("Ancient", "Futuristic"),
    ("Sad", "Happy"),
    ("Small", "Huge"),
    ("Slow", "Fast"),
    ("Cheap", "Expensive"),
    ("Safe", "Dangerous"),
    ("Formal", "Casual"),
    ("Natural", "Artificial"),
    ("Rare", "Common"),
    ("Dark", "Bright"),
    ("Relaxing", "Stressful"),
    ("Soft", "Hard"),
    ("Cowardly", "Brave"),
    ("Pessimistic", "Optimistic"),
]

# ── Personality Swap ──────────────────────────────────────────────────────────
PERSONALITY_SWAP_QUESTIONS = [
    "How do you react when someone cancels plans at the last minute?",
    "What do you do on a rainy Sunday afternoon?",
    "Someone just cut you off in traffic — what happens next?",
    "You find $100 on the street. What do you do?",
    "Describe your ideal party.",
    "You have one hour with no obligations. What do you do?",
    "What would your friends say is your most annoying trait?",
    "How do you handle conflict with a close friend?",
    "What does your perfect vacation look like?",
    "Someone wrongs you publicly. How do you respond?",
]
