# HaloWars-DE-TrueSkill

**Competitive TrueSkill & CSR ratings, leaderboards, and match history for Halo Wars: Definitive Edition (Microsoft Store).**

🌐 **Live ladder: [halo-wars-definitive-edition-stats.pages.dev](https://halo-wars-definitive-edition-stats.pages.dev)** — leaderboards, player pages, and recent games from the current ranked community, updated automatically.

> ### ⬇️ [Download v1.1 — the community leaderboard, built in](../../releases/latest)
> Unzip, double-click `Install Auto-Load.bat` once, play. No terminal, no administrator rights — see [Installation](#installation).
> On first launch the overlay downloads the community match history and the leaderboards fill themselves in; your own finished matches upload automatically. To be **rated**, press *Request to join* on the Verified Roster tab (see [Joining the ladder](#joining-the-ladder)). Prefer a purely local tracker? Delete the two `sync_` lines from `ms_trueskill_config.txt` and nothing is ever uploaded.

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

CSR runs on **TrueSkill 2** — the successor algorithm Microsoft designed for Halo 5 / Halo Infinite ranked play. Our engine is a **from-scratch rewrite implemented directly from the published research paper** ([*TrueSkill 2: An improved Bayesian skill rating system* — Minka, Cleven & Zaykov, Microsoft Research, 2018](https://www.microsoft.com/en-us/research/publication/trueskill-2-improved-bayesian-skill-rating-system/)), running the full Bayesian factor-graph update, not an approximation. Both the paper and the math are published right here in this repo: a faithful Markdown transcription of the full paper ([reference/TRUESKILL2_PAPER.md](reference/TRUESKILL2_PAPER.md)) and the MIT-licensed **Python reference implementation** ([reference/trueskill2/](reference/trueskill2/)) that the in-game engine is verified against — the two agree to ~1e-13, so anyone can check the ladder's math. **This is the recommended rating system** — the one we use as the main competitive ladder — and it maps skill onto Halo-style tiers. Each tier below Onyx has six sub-ranks of 50 CSR each:

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

## Where the data comes from

**Halo Wars: Definitive Edition has no official API** — no Halo Waypoint stats, no public match service, nothing to query. So as each ranked match ends, the overlay reads the match data directly from the running game's memory (map, teams, leaders, scores, duration — the same info as the post-game screen) and syncs it to the shared community database that powers the ladder and the [stats site](https://halo-wars-definitive-edition-stats.pages.dev). Every player in a match reports the same game independently and duplicates are merged, so the ladder stays consistent without any official service behind it.

---

## Joining the ladder

Downloading the overlay connects you to the community history immediately — the leaderboards fill in on first launch, and your finished matches upload automatically. **Being rated** is one step more: the ladder is an invite list (the Verified Roster), and a match moves ratings only when every player in it is verified — that's what keeps the board free of smurfs, farming, and fake results.

1. Open the overlay (**INSERT**) → **Verified Roster** tab → **Request to join** (it fills in your gamertag).
2. A community moderator approves the request — once you're on the roster, your ratings recompute automatically, **past games included**.
3. Until then your games are recorded and visible in Match History, they just don't move anyone's rating yet.

**Opting out entirely:** delete the `sync_server_url` and `sync_api_key` lines from `ms_trueskill_config.txt` next to the DLL — with them removed, the overlay is a purely local tracker and nothing is ever uploaded anywhere.

---

## Screenshots

**Match History** — every ranked game with map, teams, leaders, duration, and per-player rating changes:

<p align="center">
  <img src="assets/screenshots/match-history.png" width="900">
</p>

*Player names in screenshots are replaced with placeholders. More screenshots coming soon.*

---

## Requirements

- Windows 10/11 (64-bit)
- **Halo Wars: Definitive Edition — Microsoft Store / Xbox app version** (the Steam version is not supported by this tool)
- **No administrator rights**

**Does it need administrator?** No — and no UAC prompt at any point. The Microsoft Store version of the game runs inside a Windows sandbox (an *AppContainer*), which is why the overlay has to be loaded into the game rather than simply run alongside it. That loading is done by an ordinary user-level program, and once loaded the overlay lives inside the game's own sandbox with no privileges of its own. It only reads match results and draws its interface; it does not modify gameplay or touch any game file.

---

## Installation

1. Download the latest release from the [Releases](../../releases) page and unzip it anywhere you like. Keep `HaloWarsStatsLoader.exe` and `MSTrueSkill.dll` **together in the same folder**.
2. Double-click **`Install Auto-Load.bat`** once — no terminal, no prompt, no administrator. (Prefer the command line? `HaloWarsStatsLoader.exe --install` does the same thing.)
3. Start Halo Wars from the Xbox app as usual. The overlay appears by itself a few seconds in — press **INSERT** to show or hide it.

That is the whole setup. From then on it loads every time you play, and nothing is added to the game's own folder.

To stop it loading automatically, double-click `Uninstall Auto-Load.bat` (or run `HaloWarsStatsLoader.exe --uninstall`).

`HaloWarsStatsLoader.exe --status` shows what is currently set up, and `--inject` loads the overlay into a game that is already running if you would rather not install anything at all.

> Moving the folder after installing breaks it, because the autostart entry records the exact path. Run `--install` again from the new location.

---

## FAQ

**Is this a cheat?**
No. The overlay records match outcomes and displays ratings/statistics. It does not provide any gameplay advantage.

**Does it work with the Steam version?**
Not currently — this tool targets the Microsoft Store version.

**Where do the ratings come from?**
Every match is rated with the TrueSkill™ and TrueSkill 2 algorithms — the published rating systems designed for Xbox Live and Halo matchmaking, rewritten from the original research papers — over a shared community ladder. See [How the ratings work](#how-the-ratings-work) above, and browse the whole ladder on the [stats site](https://halo-wars-definitive-edition-stats.pages.dev).

**The game has no API — how do you get match data at all?**
The overlay records each match's results from your own game as it ends — see [Where the data comes from](#where-the-data-comes-from).

**How do I join the ranked ladder?**
The ladder uses a verified player roster to keep ratings fair. You can file a join request directly from the in-game overlay.

**Can my rating go down for losing to a much better player?**
Only slightly — both systems weigh results by how *surprising* they are. Losing to a favorite costs little; beating one pays a lot.

---

## Built with

- **[Dear ImGui](https://github.com/ocornut/imgui)** — the overlay's user interface. MIT License.
- **[MinHook](https://github.com/TsudaKageyu/minhook)** — the hooking library that lets the overlay draw inside the game. BSD 2-Clause License.
- **TrueSkill™ / TrueSkill 2** — rating engines implemented from scratch from the published Microsoft Research papers ([TrueSkill](https://www.microsoft.com/en-us/research/publication/trueskilltm-a-bayesian-skill-rating-system/), [TrueSkill 2](https://www.microsoft.com/en-us/research/publication/trueskill-2-improved-bayesian-skill-rating-system/)). The TrueSkill 2 paper transcription and Python reference implementation are published in [reference/](reference/).

Full license texts for bundled open-source components ship alongside every binary release (`licenses\` in the zip).

---

*This tool is free software distributed as-is; all rights reserved. Not affiliated with Microsoft, Xbox Game Studios, or 343 Industries / Halo Studios. Halo Wars is a trademark of Microsoft Corporation.*

**Revived by Hysterically.**
