# trueskill2 — reference implementation in Python

A from-scratch, pure-standard-library Python implementation of the full
TrueSkill 2 generative model and inference from the paper:

> Tom Minka, Ryan Cleven, Yordan Zaykov.
> *"TrueSkill 2: An improved Bayesian skill rating system."*
> Microsoft Research technical report MSR-TR-2018-8, March 2018.

A faithful Markdown transcription of the paper itself lives next to this
package: [`reference/TRUESKILL2_PAPER.md`](../TRUESKILL2_PAPER.md). The code
cites the paper's equation and section numbers (`eq (n)`, `§n`) throughout.

## Role in this project

This package is the **referee** for the CSR ladder's in-game rating engine.
The overlay's C++ TrueSkill 2 engine is independently rewritten from the same
paper, and every ladder rebuild is cross-checked by replaying the full match
history through this package with the exact Halo Wars configuration: the two
implementations agree to ~1e-13 (pure floating-point-ordering noise) on
win/loss-only fixtures. Publishing the referee means anyone can verify the
math behind the ladder.

## Layout

| Module | What it implements |
|---|---|
| `gaussian.py` | Gaussian arithmetic the factor graph is built from |
| `match.py` | Match / team / player-result data model |
| `factorgraph.py` | The per-match factor graph and EP inference (§4) |
| `online.py` | The forward-only online update loop (§3) |
| `batch.py` | Batch (multi-pass) rating over a match archive |
| `params.py` | Model parameters and the Halo Wars engine configuration surface |
| `metrics.py` | The §5 evaluation protocol (predict-then-update) |
| `fitting.py` | Parameter fitting (Rprop maximization of model evidence) |

## License

MIT. Ported by the author from their MCC Halo 3 Custom Games Tracker project,
where this package was originally written.