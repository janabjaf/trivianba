# NBA Trivia Cog for Red-DiscordBot

## Installation

1. Ensure you have the `nba_api` and `unidecode` libraries installed:
   ```bash
   pip install nba_api unidecode
   ```
   (The cog will attempt to install these automatically via `info.json` requirements when loaded by Red)

2. Add this cog to your bot:
   - Place the `nba_trivia` folder in your cogs directory.
   - Load it: `[p]load nba_trivia`

## Commands

- `[p]teamtrivia`: Guess the NBA team from its logo.
- `[p]playertrivia`: Guess the NBA player from their headshot.

## Data Sources

- Team data and Player data is fetched from the official NBA stats API via `nba_api`.
- Images are sourced from official NBA/ESPN CDNs.
