"""Gaussian primitives for expectation propagation.

Everything in the TrueSkill 2 paper (Minka, Cleven & Zaykov 2018) is built out
of one-dimensional Gaussians. This module provides:

  * the standard-normal pdf / cdf / inverse-cdf,
  * `Gaussian` — a 1-D Gaussian in natural (precision, precision-mean) form,
    which makes the EP message operations (multiply, divide) trivial,
  * the truncated-Gaussian correction terms v/w for "greater than" (win) and
    "within margin" (draw) observations, exactly as in Herbrich et al. 2007
    (classic TrueSkill), which the paper reuses unchanged for team orderings.

Numerical notes. The cdf is computed via math.erfc (not 1+erf), which keeps
full relative accuracy in the left tail down to z ~ -37; naive 1+erf loses all
precision below z ~ -8, which would put percent-level errors into the v/w
corrections exactly where upsets are scored. Beyond the reach of erfc the
hazard and the v/w corrections switch to Mills-ratio asymptotic series, so
they remain smooth, finite and side-correct (w < 1 strictly) arbitrarily far
into the tail instead of collapsing to the degenerate w = 1.

Pure standard library — no numpy.
"""

from __future__ import annotations

import math

SQRT2 = math.sqrt(2.0)
SQRT2PI = math.sqrt(2.0 * math.pi)

# Below this a truncation denominator (a difference of cdfs) is considered
# unrepresentable and the asymptotic ratio form is used instead.
_TINY = 2.222758749e-162
# hazard() switches from the direct pdf/cdf ratio to the Mills-ratio series
# here; at z = -30 the two agree to ~1e-12 relative.
_HAZARD_ASYMPTOTIC_Z = -30.0


def pdf(x: float) -> float:
    """Standard normal density."""
    return math.exp(-0.5 * x * x) / SQRT2PI


def cdf(x: float) -> float:
    """Standard normal cumulative distribution.

    Computed as erfc(-x/sqrt(2))/2, which — unlike (1+erf(x/sqrt(2)))/2 —
    keeps full relative precision in the left tail (down to ~1e-308).
    """
    return 0.5 * math.erfc(-x / SQRT2)


def ppf(p: float) -> float:
    """Inverse standard-normal cdf.

    Acklam's rational approximation (~1e-9) polished with one Halley step
    against the erfc-exact cdf, giving ~1e-15 relative accuracy. The upper
    half reflects onto the lower (1-p is exact in floating point for
    p >= 0.5), so both tails keep full relative accuracy.
    """
    if p <= 0.0:
        return -math.inf
    if p >= 1.0:
        return math.inf
    if p > 0.5:
        return -ppf(1.0 - p)
    a = (-3.969683028665376e1, 2.209460984245205e2, -2.759285104469687e2,
         1.383577518672690e2, -3.066479806614716e1, 2.506628277459239e0)
    b = (-5.447609879822406e1, 1.615858368580409e2, -1.556989798598866e2,
         6.680131188771972e1, -1.328068155288572e1)
    c = (-7.784894002430293e-3, -3.223964580411365e-1, -2.400758277161838e0,
         -2.549732539343734e0, 4.374664141464968e0, 2.938163982698783e0)
    d = (7.784695709041462e-3, 3.224671290700398e-1, 2.445134137142996e0,
         3.754408661907416e0)
    plow = 0.02425
    phigh = 1.0 - plow
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        x = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    elif p <= phigh:
        q = p - 0.5
        r = q * q
        x = ((((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q) / \
            (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
    else:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        x = -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    # One Halley step: for f(x) = cdf(x) - p, x <- x - u / (1 + x*u/2) with
    # u = f(x)/pdf(x). Takes Acklam's ~1e-9 estimate to ~1e-15.
    density = pdf(x)
    if density > 0.0:
        u = (cdf(x) - p) / density
        x -= u / (1.0 + 0.5 * x * u)
    return x


def hazard(z: float) -> float:
    """phi(z)/Phi(z), computed stably arbitrarily far into the left tail.

    The direct ratio is exact while the erfc-based cdf is representable
    (z > ~-37); below the switch point the Mills-ratio asymptotic series
    1/Phi(z) ~ -z / phi(z) * (1 + 1/z^2 - ...) is used (relative error
    ~1e-12 at the z = -30 switch, shrinking further out).
    """
    if z > _HAZARD_ASYMPTOTIC_Z:
        return pdf(z) / cdf(z)
    zi = 1.0 / z
    zi2 = zi * zi
    return -z - zi * (1.0 + zi2 * (-2.0 + zi2 * (10.0 - 74.0 * zi2)))


class Gaussian:
    """A 1-D Gaussian in natural form: pi = 1/sigma^2, tau = mu/sigma^2.

    pi == 0 encodes the (improper) uniform distribution, which is what an EP
    message starts out as. Multiplication and division of densities are then
    just addition and subtraction of (pi, tau).
    """

    __slots__ = ("pi", "tau")

    def __init__(self, pi: float = 0.0, tau: float = 0.0) -> None:
        self.pi = pi
        self.tau = tau

    # -- constructors ---------------------------------------------------------
    @staticmethod
    def from_mu_sigma(mu: float, sigma: float) -> "Gaussian":
        pi = 1.0 / (sigma * sigma)
        return Gaussian(pi, pi * mu)

    @staticmethod
    def from_mu_var(mu: float, var: float) -> "Gaussian":
        pi = 1.0 / var
        return Gaussian(pi, pi * mu)

    # -- moments --------------------------------------------------------------
    @property
    def mu(self) -> float:
        return 0.0 if self.pi == 0.0 else self.tau / self.pi

    @property
    def var(self) -> float:
        return math.inf if self.pi == 0.0 else 1.0 / self.pi

    @property
    def sigma(self) -> float:
        return math.inf if self.pi == 0.0 else math.sqrt(1.0 / self.pi)

    # -- density algebra ------------------------------------------------------
    def mul(self, other: "Gaussian") -> "Gaussian":
        return Gaussian(self.pi + other.pi, self.tau + other.tau)

    def div(self, other: "Gaussian") -> "Gaussian":
        return Gaussian(self.pi - other.pi, self.tau - other.tau)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        if self.pi == 0.0:
            return "N(uniform)"
        return f"N(mu={self.mu:.4f}, sigma={self.sigma:.4f})"


def delta(a: Gaussian, b: Gaussian) -> float:
    """Convergence metric between two messages (as in Herbrich's TrueSkill)."""
    pi_delta = abs(a.pi - b.pi)
    if pi_delta == math.inf:
        return 0.0
    return max(abs(a.tau - b.tau), math.sqrt(pi_delta))


# -----------------------------------------------------------------------------
# Truncated-Gaussian corrections for the team-ordering observations
# (Herbrich et al. 2007; reused unchanged by TrueSkill 2 for wins and draws).
# -----------------------------------------------------------------------------

def v_win(t: float, margin: float) -> float:
    """Additive mean correction for the observation `diff > margin`."""
    return hazard(t - margin)


def w_win(t: float, margin: float) -> float:
    """Multiplicative variance correction for `diff > margin`.

    Exactly v*(v + x) with x = t - margin; deep in the losing tail that
    product cancels catastrophically, so the equivalent series
    1 - 1/x^2 + 6/x^4 - 50/x^6 is used instead (w stays strictly below 1,
    keeping the 1-w update denominator positive).
    """
    x = t - margin
    if x < _HAZARD_ASYMPTOTIC_Z:
        x2 = 1.0 / (x * x)
        return 1.0 - x2 * (1.0 - x2 * (6.0 - 50.0 * x2))
    v = v_win(t, margin)
    return v * (v + x)


def _vw_draw_tail(at: float, margin: float) -> "tuple[float, float]":
    """(v, w) for `|diff| <= margin` when cdf(a) - cdf(b) underflows.

    With a = margin - at and b = -margin - at both far in the left tail,
    divide the exact expressions through by phi(a):

        r = phi(b)/phi(a) = exp(-2*margin*at)
        Z/phi(a) = M(a) - r*M(b)          with M the Mills ratio 1/hazard
        v = (r - 1) / (Z/phi(a))
        w = v^2 + (a - b*r) / (Z/phi(a))

    Every factor is O(at), so this stays accurate arbitrarily deep.
    """
    a = margin - at
    b = -margin - at
    rm1 = math.expm1(-2.0 * margin * at)  # r - 1, exact for small margins
    r = rm1 + 1.0
    denom = 1.0 / hazard(a) - r / hazard(b)  # Z / phi(a)
    if denom <= 0.0:
        # margin == 0 (a point observation diff == 0): the posterior collapses
        # onto the margin. Report the limit rather than a 0/0.
        return -at, 1.0 - 2.0 ** -52
    v = rm1 / denom
    return v, v * v + (a - b * r) / denom


def v_draw(t: float, margin: float) -> float:
    """Additive mean correction for the observation `|diff| <= margin`."""
    at = abs(t)
    a = margin - at
    b = -margin - at
    denom = cdf(a) - cdf(b)
    if denom > _TINY:
        v = (pdf(b) - pdf(a)) / denom
    else:
        v, _ = _vw_draw_tail(at, margin)
    return -v if t < 0.0 else v


def w_draw(t: float, margin: float) -> float:
    """Multiplicative variance correction for `|diff| <= margin`."""
    at = abs(t)
    a = margin - at
    b = -margin - at
    denom = cdf(a) - cdf(b)
    if denom <= _TINY:
        _, w = _vw_draw_tail(at, margin)
        return w
    v = (pdf(b) - pdf(a)) / denom
    return v * v + (a * pdf(a) - b * pdf(b)) / denom
