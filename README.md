# HaloWars-DE-TrueSkill

**Competitive TrueSkill & CSR ratings, leaderboards, and match history for Halo Wars: Definitive Edition (Microsoft Store).**

🌐 **Live ladder: [halo-wars-definitive-edition-stats.pages.dev](https://halo-wars-definitive-edition-stats.pages.dev)** — leaderboards, player pages, and recent games from the current ranked community, updated automatically.

> ### 🚧 First public release coming soon — watch this repo.
> The tool is in active development and live testing with the current ranked community. Star/watch the repo to be notified when the first release lands.

The original Halo Wars (2009) was built around a **TrueSkill™-powered ranked ladder** — skill ratings, a public leaderboard, and the climb was half the game. When **Halo Wars: Definitive Edition** was released, that entire system was removed: no skill ratings, no leaderboard, no match history. **This project is a rebuild of that ranked experience** for the Microsoft Store version — an in-game overlay backed by a community ladder, restoring what Definitive Edition left out and modernizing it with TrueSkill 2.

This ladder is built for — and used by — the **high-level Halo Wars: DE competitive community**: the players still competing seriously are the ones being rated on it.

---

## Features

### 🏆 Skill ratings & leaderboards
- **TrueSkill™** ladder — the same rating model used by Xbox Live matchmaking, tracked per game type (1v1 / 2v2 / 3v3 / Deathmatch).
- **TrueSkill 2 (CSR)** ladder — **the recommended system** — a Competitive Skill Rank powered by our from-scratch rewrite of Microsoft Research's TrueSkill 2 algorithm, with Halo-style tiers: Bronze → Silver → Gold → Platinum → Diamond → **Onyx**, plus a **Champion** accolade for the top of the board.
- Two rank display styles, switchable in-game: modern **tier emblems** or the classic **Halo 2 1–50** numbered ranks.
- Monthly wins boards alongside the lifetime skill ladders.

### 📜 Match history
- Every ranked game recorded automatically: map, teams, leaders, scores, duration, and per-player rating changes.
- Rich in-overlay match cards with map thumbnails, leader portraits, and result icons — filter by game type, playlist, map, or player.

<p align="center">
  <img src="assets/maps/blood_gulch.jpg" width="150">&nbsp;
  <img src="assets/maps/exile.jpg" width="150">&nbsp;
  <img src="assets/maps/fort_deen.jpg" width="150">&nbsp;
  <img src="assets/maps/chasms.jpg" width="150">
</p>
<p align="center">
  <img src="assets/leaders/cutter.jpg" width="64">&nbsp;
  <img src="assets/leaders/forge.jpg" width="64">&nbsp;
  <img src="assets/leaders/anders.jpg" width="64">&nbsp;
  <img src="assets/leaders/arbiter.jpg" width="64">&nbsp;
  <img src="assets/leaders/brute.jpg" width="64">&nbsp;
  <img src="assets/leaders/prophet.jpg" width="64">
</p>

*The map art and leader portraits used on the match cards.*

### 🎖️ In-game rank icons
- The game itself draws rank art next to players in the **pre-game lobby and the in-match scoreboard** — your opponents' ranks visible at a glance, using the classic 1–50 numerals.

### 🌐 PC ↔ Xbox custom lobbies
- Cross-play custom-game lobbies between PC (Microsoft Store) and Xbox players: search for Xbox-hosted lobbies and advertise your own PC lobby to Xbox friends.

### ⚡ FPS cap control
- Raise the game's frame-rate cap: 60 / 120 / 240 / 360 FPS, plus a built-in frame-rate meter. No config files, one hotkey.

---

## How the ratings work

Two rating systems run side by side over the same match history. Both are *earned in real matches only* — there is no placement quiz, and ratings can't be edited by anyone, including us.

### TrueSkill™

TrueSkill models every player with two numbers: an estimated skill **μ** and an uncertainty **σ**. The number shown on the ladder is the **conservative estimate** (μ − 3σ) — skill the system considers *proven*, not just guessed. That has two visible effects:

- **New players start at 1** and climb quickly: while your uncertainty is high, every result teaches the system a lot, so your first games move your rating fast.
- **Established players move slowly**: after many games the system knows your level, so a single win or loss shifts you only a little.

### TrueSkill 2 (CSR)

CSR runs on **TrueSkill 2** — the successor algorithm Microsoft designed for Halo 5 / Halo Infinite ranked play. Our engine is a **from-scratch rewrite implemented directly from the published research paper** ([*TrueSkill 2: An improved Bayesian skill rating system* — Minka, Cleven & Zaykov, Microsoft Research, 2018](https://www.microsoft.com/en-us/research/publication/trueskill-2-improved-bayesian-skill-rating-system/)), running the full Bayesian factor-graph update, not an approximation. **This is the recommended rating system** — the one we use as the main competitive ladder — and it maps skill onto Halo-style tiers. Each tier below Onyx has six sub-ranks of 50 CSR each:

| Tier | CSR range |
|---|---|
| <img src="assets/csr/csr-bronze-1.png" width="32" align="center"> **Bronze 1–6** | 0 – 299 |
| <img src="assets/csr/csr-silver-1.png" width="32" align="center"> **Silver 1–6** | 300 – 599 |
| <img src="assets/csr/csr-gold-1.png" width="32" align="center"> **Gold 1–6** | 600 – 899 |
| <img src="assets/csr/csr-platinum-1.png" width="32" align="center"> **Platinum 1–6** | 900 – 1199 |
| <img src="assets/csr/csr-diamond-1.png" width="32" align="center"> **Diamond 1–6** | 1200 – 1499 |
| <img src="assets/csr/csr-onyx.png" width="32" align="center"> **Onyx** | 1500+ (shows your exact CSR) |
| <img src="assets/csr/csr-champion.png" width="32" align="center"> **Champion** | Top players on the leaderboard at 1600+ |

*The actual tier emblems the overlay and leaderboards display.*

Everyone starts at CSR 0 with maximum uncertainty. Like TrueSkill, early games move you hundreds of CSR at a time while the system finds your level; once established, a typical match moves you a few dozen. **Champion is not a CSR threshold you can camp** — it is an accolade for the very top of the board, recalculated as the leaderboard changes.

### Halo 2 style: ranks 1–50

Prefer the classic ladder? Switch the display to **Halo 2 1–50** ranks (in the overlay and the in-game lobby/scoreboard icons). Your CSR is mapped onto the iconic 50-rank ladder:

<p align="center">
  <img src="assets/h2/h2-rank-01.png" width="56">&nbsp;
  <img src="assets/h2/h2-rank-10.png" width="56">&nbsp;
  <img src="assets/h2/h2-rank-25.png" width="56">&nbsp;
  <img src="assets/h2/h2-rank-40.png" width="56">&nbsp;
  <img src="assets/h2/h2-rank-45.png" width="56">&nbsp;
  <img src="assets/h2/h2-rank-50.png" width="56">
</p>

Just like the original, the climb gets steeper near the top:

| CSR | Halo 2 rank |
|---|---|
| 0 – 1599 | 1 – 44 (≈ every 36 CSR) |
| 1600 – 1899 | 45 – 49 (every 60 CSR) |
| 1900+ | **50** |

### Example: a new player's first session

1. You install the tool and play your first ranked 3v3 — you show as **rank 1 / CSR 0** (unproven, not "bad").
2. You win two games against mid-Gold opponents: the system learns fast — you jump to mid-Silver territory in one evening.
3. You lose to a Diamond team: barely moves you — losing to better players is expected and costs little.
4. Over the next ~10–20 games your uncertainty shrinks, the swings get smaller, and your rating settles where you actually play.

All of this is visible live on the **[stats site](https://halo-wars-definitive-edition-stats.pages.dev)**: full leaderboards, every player's rating history, and recent games with per-match rating changes.

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
Every match is rated with the TrueSkill™ and TrueSkill 2 algorithms — the published rating systems designed for Xbox Live and Halo matchmaking, rewritten from the original research papers — over a shared community ladder. See [How the ratings work](#how-the-ratings-work) above, and browse the whole ladder on the [stats site](https://halo-wars-definitive-edition-stats.pages.dev).

**How do I join the ranked ladder?**
The ladder uses a verified player roster to keep ratings fair. You can file a join request directly from the in-game overlay.

**Can my rating go down for losing to a much better player?**
Only slightly — both systems weigh results by how *surprising* they are. Losing to a favorite costs little; beating one pays a lot.

---

*This tool is free software distributed as-is; all rights reserved. Not affiliated with Microsoft, Xbox Game Studios, or 343 Industries / Halo Studios. Halo Wars is a trademark of Microsoft Corporation.*

**Revived by Hysterically.**
