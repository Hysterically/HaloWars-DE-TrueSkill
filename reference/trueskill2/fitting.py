"""Parameter estimation (§4).

The paper treats model parameters as point masses and updates them with Rprop
(Riedmiller & Braun 1993), where each gradient is accumulated from the EP
messages flowing into the parameter across a whole batch sweep, iterating
~100 sweeps over millions of matches.

This module implements the same outer loop — Rprop ascent on a batch objective
over the historical data, with the paper's constraints (beta fixed, w_d >= 0,
m_q <= 0, squadOffset(1) = 0, variances positive) — with one deliberate,
documented simplification suited to small datasets: the per-parameter gradient
SIGN is obtained by finite differences of the objective rather than by
accumulating EP messages. Rprop only consumes gradient signs, so on datasets
where a full replay is cheap (this repo's use case: hundreds of matches, not
millions) the two coincide in behaviour while this version stays independent
of inference internals. The default objective is the §5 predictive log-loss of
match outcomes — a smooth, differentiable surrogate for the paper's headline
§5 metric, predictive accuracy (which, being piecewise-constant, gives no
usable gradient sign for Rprop).

The paper also notes the estimation "breaks down for game modes with less than
1000 matches. For such modes, we used the parameters estimated from the most
similar popular mode." — for a friends-group tracker, fit a single shared mode
or fit only a few parameters.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .match import Match
from .metrics import evaluate_online
from .params import CountModel, ModeParams, Params, QuitModel


# -----------------------------------------------------------------------------
# Rprop (sign-based resilient propagation), maximizing.
# -----------------------------------------------------------------------------

@dataclass
class RpropOptions:
    iterations: int = 100  # §4: "reasonable parameter estimates in about 100 iterations"
    step_init: float = 0.05
    step_min: float = 1e-5
    step_max: float = 1.0
    eta_plus: float = 1.2
    eta_minus: float = 0.5
    #: Relative finite-difference size for the gradient-sign probe.
    fd_rel: float = 1e-2
    fd_abs: float = 1e-4


def rprop_maximize(
    objective: Callable[[Sequence[float]], float],
    x0: Sequence[float],
    lower: Optional[Sequence[Optional[float]]] = None,
    upper: Optional[Sequence[Optional[float]]] = None,
    options: Optional[RpropOptions] = None,
    on_iteration: Optional[Callable[[int, List[float], float], None]] = None,
) -> Tuple[List[float], float]:
    """Rprop ascent. Returns (best_x, best_objective)."""
    opt = options or RpropOptions()
    x = list(x0)
    n = len(x)
    lo = list(lower) if lower is not None else [None] * n
    hi = list(upper) if upper is not None else [None] * n
    steps = [opt.step_init] * n
    prev_sign = [0] * n

    def clamp(i: int, v: float) -> float:
        if lo[i] is not None:
            v = max(v, lo[i])
        if hi[i] is not None:
            v = min(v, hi[i])
        return v

    best_x = list(x)
    best_f = objective(x)
    f = best_f
    for it in range(opt.iterations):
        # True (Jacobi) Rprop: every coordinate's gradient sign is probed at the
        # SAME frozen point captured at the start of the sweep, then all updates
        # are applied together — matching §4's "at the end of each iteration, we
        # update each parameter" (gradients accumulated from one sweep). Stepping
        # x[i] in place mid-sweep would evaluate later coordinates at a
        # half-stepped point (coordinate ascent, not Rprop).
        x_frozen = list(x)
        new_x = list(x)
        for i in range(n):
            h = max(opt.fd_abs, opt.fd_rel * abs(x_frozen[i]))
            xp = list(x_frozen)
            xp[i] = clamp(i, x_frozen[i] + h)
            xm = list(x_frozen)
            xm[i] = clamp(i, x_frozen[i] - h)
            if xp[i] == xm[i]:
                continue
            g = objective(xp) - objective(xm)
            sign = (g > 0) - (g < 0)
            if sign == 0:
                prev_sign[i] = 0
                continue
            if prev_sign[i] * sign > 0:
                steps[i] = min(steps[i] * opt.eta_plus, opt.step_max)
            elif prev_sign[i] * sign < 0:
                steps[i] = max(steps[i] * opt.eta_minus, opt.step_min)
            prev_sign[i] = sign
            new_x[i] = clamp(i, x_frozen[i] + sign * steps[i])
        x = new_x
        f = objective(x)
        if f > best_f:
            best_f = f
            best_x = list(x)
        if on_iteration is not None:
            on_iteration(it, list(x), f)
    return best_x, best_f


# -----------------------------------------------------------------------------
# Binding named ModeParams fields to an optimizer vector.
# -----------------------------------------------------------------------------

#: name -> (getter, setter, lower bound, upper bound). Setters return a new
#: ModeParams (they're frozen dataclasses). Count/quit entries require the
#: corresponding sub-model to be present on the params being fitted.
_FIELDS: Dict[str, Tuple[Callable, Callable, Optional[float], Optional[float]]] = {
    "gamma": (lambda m: m.gamma, lambda m, v: replace(m, gamma=v), 0.0, None),
    "tau": (lambda m: m.tau, lambda m, v: replace(m, tau=v), 0.0, None),
    "v0": (lambda m: m.v0, lambda m, v: replace(m, v0=v), 1e-6, None),
    "m0": (lambda m: m.m0, lambda m, v: replace(m, m0=v), None, None),
    "draw_margin": (lambda m: m.draw_margin, lambda m, v: replace(m, draw_margin=v), 0.0, None),
    "mode_weight": (lambda m: m.mode_weight, lambda m, v: replace(m, mode_weight=v), 0.0, None),  # w_d >= 0
    "kill.weight_perf": (
        lambda m: m.kill.weight_perf,
        lambda m, v: replace(m, kill=replace(m.kill, weight_perf=v)),
        None, None,
    ),
    "kill.weight_opp": (
        lambda m: m.kill.weight_opp,
        lambda m, v: replace(m, kill=replace(m.kill, weight_opp=v)),
        None, None,
    ),
    "kill.variance": (
        lambda m: m.kill.variance,
        lambda m, v: replace(m, kill=replace(m.kill, variance=v)),
        1e-6, None,
    ),
    "death.weight_perf": (
        lambda m: m.death.weight_perf,
        lambda m, v: replace(m, death=replace(m.death, weight_perf=v)),
        None, None,
    ),
    "death.weight_opp": (
        lambda m: m.death.weight_opp,
        lambda m, v: replace(m, death=replace(m.death, weight_opp=v)),
        None, None,
    ),
    "death.variance": (
        lambda m: m.death.variance,
        lambda m, v: replace(m, death=replace(m.death, variance=v)),
        1e-6, None,
    ),
    "quit.mean": (  # m_q <= 0 (§9)
        lambda m: m.quit.mean,
        lambda m, v: replace(m, quit=replace(m.quit, mean=v)),
        None, 0.0,
    ),
    "quit.variance": (
        lambda m: m.quit.variance,
        lambda m, v: replace(m, quit=replace(m.quit, variance=v)),
        1e-6, None,
    ),
    "quit.p_unrelated": (  # p_u (§9), a probability
        lambda m: m.quit.p_unrelated,
        lambda m, v: replace(m, quit=replace(m.quit, p_unrelated=v)),
        0.0, 1.0,
    ),
    "quit.p_related": (  # p_r (§9), a probability
        lambda m: m.quit.p_related,
        lambda m, v: replace(m, quit=replace(m.quit, p_related=v)),
        0.0, 1.0,
    ),
}

#: Shared base-skill tunables (§11, eqs 14-16), addressed as "base.<field>".
#: These live on Params.base (BaseSkillParams), not a ModeParams, so they are
#: routed separately from _FIELDS. getter/setter operate on BaseSkillParams.
_BASE_FIELDS: Dict[str, Tuple[Callable, Callable, Optional[float], Optional[float]]] = {
    "vb": (lambda b: b.vb, lambda b, v: replace(b, vb=v), 1e-6, None),  # v_b (14), > 0
    "gamma": (lambda b: b.gamma, lambda b, v: replace(b, gamma=v), 0.0, None),  # gamma_base (15)
    "tau": (lambda b: b.tau, lambda b, v: replace(b, tau=v), 0.0, None),  # tau_base (16)
}

#: "squad_offset[k]" / "experience_offset[k]" address element k of the eq-(7) /
#: eq-(8) tunable arrays (§6, §7). Fit these by index; squad_offset[0] stays
#: pinned to 0 (squadOffset(1) = 0).
_ARRAY_RE = re.compile(r"^(squad_offset|experience_offset)\[(\d+)\]$")

FITTABLE = tuple(sorted(_FIELDS)) + tuple("base." + b for b in sorted(_BASE_FIELDS))


#: A resolved fittable parameter: read it from / write it to a full Params (given
#: the mode being fit), plus its bounds. Unifies per-mode scalars, base-skill
#: scalars ("base.*") and offset-array elements ("squad_offset[k]" / ...).
_Resolved = Tuple[
    Callable[[Params, str], float],  # get(params, mode) -> value
    Callable[[Params, str, float], Params],  # set(params, mode, value) -> Params
    Optional[float],  # lower bound
    Optional[float],  # upper bound
]


def _resolve_field(name: str) -> _Resolved:
    """Bind a fittable-parameter name to (get, set, lower, upper) over Params."""
    if name in _FIELDS:
        getter, setter, lo, hi = _FIELDS[name]
        return (
            lambda p, mode: getter(p.mode(mode)),
            lambda p, mode, v: p.with_mode(mode, setter(p.mode(mode), v)),
            lo,
            hi,
        )
    if name.startswith("base."):
        field = name[len("base."):]
        if field not in _BASE_FIELDS:
            raise ValueError(f"unknown base parameter {name!r}; choose from {FITTABLE}")
        getter, setter, lo, hi = _BASE_FIELDS[field]
        return (
            lambda p, mode: getter(p.base),
            lambda p, mode, v: replace(p, base=setter(p.base, v)),
            lo,
            hi,
        )
    m = _ARRAY_RE.match(name)
    if m:
        arr_name, k = m.group(1), int(m.group(2))
        attr = "squad_offsets" if arr_name == "squad_offset" else "experience_offsets"
        pin_first = arr_name == "squad_offset"

        def get(p: Params, mode: str) -> float:
            arr = getattr(p.mode(mode), attr)
            if k < len(arr):
                return arr[k]
            return arr[-1] if arr else 0.0

        def st(p: Params, mode: str, v: float) -> Params:
            mp = p.mode(mode)
            arr = list(getattr(mp, attr))
            while len(arr) <= k:  # grow, repeating the last known value
                arr.append(arr[-1] if arr else 0.0)
            arr[k] = v
            if pin_first and arr:
                arr[0] = 0.0  # squadOffset(1) is fixed to 0 (§6)
            return p.with_mode(mode, replace(mp, **{attr: tuple(arr)}))

        # squadOffset(1) is pinned, so element 0 has no free range; the offset
        # arrays are otherwise free (the paper places no sign constraint on them).
        return get, st, None, None
    raise ValueError(
        f"unknown fittable parameter {name!r}; choose from {FITTABLE} "
        f"or an offset element like 'squad_offset[2]' / 'experience_offset[5]'"
    )


def fit_mode_params(
    matches: Sequence[Match],
    params: Params,
    mode: str,
    names: Sequence[str],
    objective: Optional[Callable[[Params], float]] = None,
    options: Optional[RpropOptions] = None,
    verbose: bool = False,
) -> Tuple[Params, float]:
    """Fit the named parameters of one mode by Rprop over the match history.

    The default objective is the negative §5 predictive log-loss (higher is
    better). Returns the updated Params and the best objective value.
    """
    resolved = [_resolve_field(name) for name in names]

    if objective is None:
        def objective(p: Params) -> float:
            return -evaluate_online(matches, p).log_loss

    def params_with(vec: Sequence[float]) -> Params:
        p = params
        for (_, setter, _, _), v in zip(resolved, vec):
            p = setter(p, mode, v)
        return p

    x0 = [getter(params, mode) for getter, _, _, _ in resolved]
    lower = [lo for _, _, lo, _ in resolved]
    upper = [hi for _, _, _, hi in resolved]

    def on_iter(it: int, x: List[float], f: float) -> None:
        if verbose:
            pretty = ", ".join(f"{n}={v:.5g}" for n, v in zip(names, x))
            print(f"  rprop iter {it + 1}: objective={f:.5f}  {pretty}")

    def guarded(v: Sequence[float]) -> float:
        # An Rprop probe far from the seed (its steps grow geometrically) can
        # push EP into numerical collapse — e.g. extreme count weights drive a
        # message precision to zero and the replay raises. Score such a point
        # as unusable instead of aborting the whole fit.
        try:
            f = objective(params_with(v))
        except (ZeroDivisionError, OverflowError, ValueError):
            return float("-inf")
        return f if f == f else float("-inf")  # NaN is unusable too

    best_x, best_f = rprop_maximize(guarded, x0, lower, upper, options, on_iter)
    return params_with(best_x), best_f


def field_value(params: Params, mode: str, name: str) -> float:
    """Read the current value of any fittable parameter from a Params.

    Accepts every FITTABLE name plus base-skill scalars ("base.vb", ...) and
    offset-array elements ("squad_offset[2]", "experience_offset[5]").
    """
    getter, _, _, _ = _resolve_field(name)
    return getter(params, mode)


__all__ = ["rprop_maximize", "RpropOptions", "fit_mode_params", "field_value", "FITTABLE"]
