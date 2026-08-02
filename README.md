# HaloWars-DE-TrueSkill

**Competitive TrueSkill & CSR ratings, leaderboards, and match history for Halo Wars: Definitive Edition (Microsoft Store).**

> ### 🚧 First public release coming soon — watch this repo.
> The tool is in active development and live testing with the current ranked community. Star/watch the repo to be notified when the first release lands.

Halo Wars: Definitive Edition shipped without the original ranked experience — no skill ratings, no leaderboards, no match history. This project brings all of that back for the Microsoft Store version, as an in-game overlay backed by a community ladder.

**See the ladder live:** [Halo Wars DE Stats](https://halo-wars-definitive-edition-stats.pages.dev) — leaderboards, player pages, and recent games from the current community, updated automatically.

---

## Features

### 🏆 Skill ratings & leaderboards
- **TrueSkill™** ladder — the same rating model used by Xbox Live matchmaking, tracked per game type (1v1 / 2v2 / 3v3 / Deathmatch).
- **CSR** ladder — a TrueSkill 2 based Competitive Skill Rank with Halo-style tiers: Bronze → Silver → Gold → Platinum → Diamond → **Onyx**, plus a **Champion** accolade for the top of the board.
- Two rank display styles, switchable in-game: modern **tier emblems** or the classic **Halo 2 1–50** numbered ranks.
- Monthly wins boards alongside the lifetime skill ladders.

### 📜 Match history
- Every ranked game recorded automatically: map, teams, leaders, scores, duration, and per-player rating changes.
- Rich in-overlay match cards with map thumbnails, leader portraits, and result icons — filter by game type, playlist, map, or player.

### 🎖️ In-game rank icons
- The game itself draws rank art next to players in the **pre-game lobby and the in-match scoreboard** — your opponents' ranks visible right where the original Halo Wars showed them, using the classic 1–50 numerals.

### 🌐 PC ↔ Xbox custom lobbies
- Cross-play custom-game lobbies between PC (Microsoft Store) and Xbox players: search for Xbox-hosted lobbies and advertise your own PC lobby to Xbox friends.

### ⚡ FPS cap control
- Raise the game's frame-rate cap: 60 / 120 / 240 / 360 FPS, plus a built-in frame-rate meter. No config files, one hotkey.

---

## Screenshots

*Coming with the first release.*

---

## Requirements

- Windows 10/11 (64-bit)
- **Halo Wars: Definitive Edition — Microsoft Store / Xbox app version** (the Steam version is not supported by this tool)
- The launcher must be run **as administrator**

**Why administrator?** The Microsoft Store version of the game runs in a Windows sandbox (an *AppContainer*) that normal programs are not allowed to attach to. The launcher needs elevation once per game session to load the overlay into the game — this is the only supported way to add an overlay to a Store game. The overlay itself only reads match results and draws its interface; it does not modify gameplay.

---

## Installation

Instructions will ship with the first release. In short: download the launcher from the [Releases](../../releases) page, run it as administrator, start the game — the launcher keeps the tool up to date automatically.

---

## FAQ

**Is this a cheat?**
No. The overlay records match outcomes and displays ratings/statistics. It does not provide any gameplay advantage.

**Does it work with the Steam version?**
Not currently — this tool targets the Microsoft Store version.

**Where do the ratings come from?**
Every match is rated with the TrueSkill™ and TrueSkill 2 algorithms — the published rating systems designed for Xbox Live and Halo matchmaking — over a shared community ladder. Ratings for the whole ladder are visible on the [stats site](https://halo-wars-definitive-edition-stats.pages.dev).

**How do I join the ranked ladder?**
The ladder uses a verified player roster to keep ratings fair. You can file a join request directly from the in-game overlay.

---

*This tool is free software distributed as-is; all rights reserved. Not affiliated with Microsoft, Xbox Game Studios, or 343 Industries / Halo Studios. Halo Wars is a trademark of Microsoft Corporation.*

**Revived by Hysterically.**
