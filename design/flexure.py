"""Flexural design of rectangular reinforced-concrete beams.

Implements ACI 318-19 strength design. NSCP 2015 uses the same formulas through
its ACI 318-08/11 lineage; where NSCP 2015 section numbers differ from ACI 318-19
the equivalence is stated in a comment, not silently substituted.
"""

from dataclasses import dataclass
from math import ceil, pi, sqrt

from .materials import Material, PHI_FLEXURE, beta1

# Standard SI rebar diameters in mm (NSCP practice, US #3-#11 equivalents).
# SI diameters keep the package SI-consistent; pass a custom tuple to
# select_bars() to use another bar set.
BAR_DIAMETERS_MM: tuple[float, ...] = (10.0, 12.0, 16.0, 20.0, 25.0, 28.0, 32.0, 36.0)


def bar_area(diameter: float) -> float:
    """Area (mm^2) of one round rebar of given diameter (mm)."""
    return pi * diameter**2 / 4.0


def rho_min(concrete: Material) -> float:
    """Minimum tension-reinforcement ratio, ACI 318-19 9.6.1.2(a).

    NSCP 2015 Sec 410.6.1 (ACI 318-08/11 10.5.1) has the identical formula.
    """
    return max(0.25 * sqrt(concrete.fc) / concrete.fy, 1.4 / concrete.fy)


def rho_max(concrete: Material) -> float:
    """Maximum tension-reinforcement ratio for a tension-controlled section.

    Tension-controlled means net tensile strain eps_t >= 0.005 (ACI 318-19
    Table 21.2.2). With eps_cu = 0.003: c/d = 0.003/(0.003+0.005) = 0.375 and
    As fy = 0.85 fc beta1 c b. NSCP 2015 Sec 410.3 (ACI 318-08/11 10.3.4) is
    the equivalent provision.
    """
    return 0.85 * concrete.fc * beta1(concrete.fc) * 0.375 / concrete.fy


def as_required_singly(Mu_kNm: float, b: float, d: float, concrete: Material) -> float:
    """Required tension steel As (mm^2) for a singly reinforced rectangular beam.

    Solves Mn = As fy (d - a/2) with a = As fy / (0.85 fc b) (Whitney block,
    ACI 318-19 22.2.2.1) using Mn = Mu/phi (21.2.2), then applies the rho_min
    limit (9.6.1.2).

    Raises ValueError when Mu exceeds the capacity of any singly reinforced
    section (the quadratic has no real root); use compression steel instead.

    Units: Mu in kN*m; b, d in mm; stresses in MPa.
    """
    mn = Mu_kNm * 1e6 / PHI_FLEXURE
    a = concrete.fy**2 / (1.7 * concrete.fc * b)
    bb = -concrete.fy * d
    cc = mn
    disc = bb * bb - 4.0 * a * cc
    if disc < 0.0:
        raise ValueError(
            f"Mu={Mu_kNm} kN*m exceeds the capacity of any singly reinforced "
            "section; use compression steel or enlarge the section."
        )
    as_req = (-bb - sqrt(disc)) / (2.0 * a)
    return max(as_req, rho_min(concrete) * b * d)


def _design_doubly(
    mn: float, b: float, d: float, d_prime: float, concrete: Material
) -> tuple[float, float, float, float, float]:
    """Design compression steel for a doubly reinforced section.

    Keeps the section at the tension-controlled limit c = 0.375 d (ACI 318-19
    Table 21.2.2) so eps_t = 0.005. Returns (As_total, A's, c, a, fs').

    ACI 318-19 22.2.2; NSCP 2015 Sec 409.3 is the equivalent provision.
    Units: mn in N*mm; b, d, d' in mm.
    """
    b1 = beta1(concrete.fc)
    c_neutral = 0.375 * d
    a = b1 * c_neutral
    as_1 = 0.85 * concrete.fc * a * b / concrete.fy
    mn_1 = as_1 * concrete.fy * (d - a / 2.0)
    mn_2 = mn - mn_1
    if mn_2 <= 0.0:
        return as_1, 0.0, c_neutral, a, concrete.fy
    eps_s_prime = 0.003 * (c_neutral - d_prime) / c_neutral
    fs_prime = min(concrete.es * eps_s_prime, concrete.fy)
    if fs_prime <= 0.0:
        raise ValueError(
            "d' is too large: compression steel is not in compression at the "
            "tension-controlled limit."
        )
    as_2 = mn_2 / (concrete.fy * (d - d_prime))
    a_s_prime = mn_2 / (fs_prime * (d - d_prime))
    return as_1 + as_2, a_s_prime, c_neutral, a, fs_prime


def phi_mn(
    as_t: float, as_c: float, b: float, d: float, d_prime: float, concrete: Material
) -> tuple[float, float, float]:
    """Design flexural strength phi*Mn (N*mm) for provided steel, by strain compatibility.

    Iterates on the neutral-axis depth c until Cc + C's = T (ACI 318-19 22.2.2.1).
    Compression-steel stress is capped at +/- fy. phi follows Table 21.2.2:
    0.90 for eps_t >= 0.005, 0.65 for eps_t <= eps_y, linear interpolation between.

    Returns (phi*Mn, Mn, eps_t).
    """
    if as_t <= 0.0:
        return 0.0, 0.0, 0.0
    eps_cu = 0.003
    eps_y = concrete.epsilon_y
    b1 = beta1(concrete.fc)
    tension = as_t * concrete.fy
    c = 0.45 * d  # initial guess inside the tension-controlled range
    for _ in range(100):
        cc = 0.85 * concrete.fc * b1 * c * b
        eps_sp = eps_cu * (c - d_prime) / c
        fs_p = min(max(concrete.es * eps_sp, -concrete.fy), concrete.fy)
        cs = as_c * fs_p
        res = cc + cs - tension
        if abs(res) < 1.0:
            break
        dcs_dc = as_c * concrete.es * eps_cu * d_prime / c**2 if -eps_y < eps_sp < eps_y else 0.0
        dc_dc = 0.85 * concrete.fc * b1 * b
        c -= res / (dc_dc + dcs_dc)
    a = b1 * c
    cc = 0.85 * concrete.fc * a * b
    eps_sp = eps_cu * (c - d_prime) / c
    fs_p = min(max(concrete.es * eps_sp, -concrete.fy), concrete.fy)
    cs = as_c * fs_p
    eps_t = eps_cu * (d - c) / c
    mn = cc * (d - a / 2.0) + cs * (d - d_prime)
    if eps_t >= 0.005:
        phi = PHI_FLEXURE
    elif eps_t <= eps_y:
        phi = 0.65
    else:
        phi = 0.65 + 0.25 * (eps_t - eps_y) / (0.005 - eps_y)
    return phi * mn, mn, eps_t


def select_bars(
    as_required: float, diameters: tuple[float, ...] = BAR_DIAMETERS_MM
) -> tuple[tuple[float, int], ...]:
    """Pick (diameter_mm, count) bars providing >= As with the fewest bars.

    Ties are broken toward the least excess steel.
    ponytail: no check that the bars fit in one layer within the member width;
    add a fit/clearance check when member geometry matters.
    """
    best_d = diameters[0]
    best_n = max(1, ceil(as_required / bar_area(best_d)))
    best_area = best_n * bar_area(best_d)
    for d in diameters[1:]:
        n = max(1, ceil(as_required / bar_area(d)))
        area = n * bar_area(d)
        if n < best_n or (n == best_n and area < best_area):
            best_d, best_n, best_area = d, n, area
    return ((best_d, best_n),)


@dataclass
class FlexureDesign:
    """Result of flexural design for a rectangular beam section.

    Forces in N (moments in N*mm), areas in mm^2, stresses in MPa.
    """

    doubly: bool
    as_required: float  # tension steel, mm^2
    as_compression_required: float  # compression steel, mm^2 (0 for singly)
    rho: float
    rho_min: float
    rho_max: float
    bars_tension: tuple[tuple[float, int], ...]  # (diameter_mm, count)
    bars_compression: tuple[tuple[float, int], ...]
    as_provided: float
    as_compression_provided: float
    phi_mn_provided: float  # N*mm
    mu_nmm: float
    ok: bool


def design_flexure(
    Mu_kNm: float, b: float, d: float, d_prime: float, concrete: Material
) -> FlexureDesign:
    """Design tension (and compression, if needed) steel for a rectangular beam.

    Tries a singly reinforced section first; when the required steel exceeds the
    tension-controlled limit rho_max, adds compression steel at c = 0.375 d
    (ACI 318-19 22.2.2; NSCP 2015 Sec 409.3 is the equivalent provision).
    The chosen bars are then verified by strain compatibility (phi*Mn >= Mu,
    eps_t >= 0.004 per ACI 318-19 9.3.3.1).

    Units: Mu in kN*m; b, d, d' in mm.
    """
    r_min, r_max = rho_min(concrete), rho_max(concrete)
    as_max = r_max * b * d
    try:
        as_singly = as_required_singly(Mu_kNm, b, d, concrete)
    except ValueError:
        as_singly = float("inf")
    doubly = as_singly > as_max
    if doubly:
        mn = Mu_kNm * 1e6 / PHI_FLEXURE
        as_req, as_c_req, _, _, _ = _design_doubly(mn, b, d, d_prime, concrete)
        as_req = max(as_req, r_min * b * d)
    else:
        as_req, as_c_req = as_singly, 0.0
    bars_t = select_bars(as_req)
    bars_c = select_bars(as_c_req) if as_c_req > 0.0 else ()
    as_prov = sum(n * bar_area(dm) for dm, n in bars_t)
    as_c_prov = sum(n * bar_area(dm) for dm, n in bars_c)
    phi_mn_v, _, eps_t = phi_mn(as_prov, as_c_prov, b, d, d_prime, concrete)
    ok = phi_mn_v >= Mu_kNm * 1e6 and eps_t >= 0.004  # 9.3.3.1
    return FlexureDesign(
        doubly=doubly,
        as_required=as_req,
        as_compression_required=as_c_req,
        rho=as_req / (b * d),
        rho_min=r_min,
        rho_max=r_max,
        bars_tension=bars_t,
        bars_compression=bars_c,
        as_provided=as_prov,
        as_compression_provided=as_c_prov,
        phi_mn_provided=phi_mn_v,
        mu_nmm=Mu_kNm * 1e6,
        ok=ok,
    )
