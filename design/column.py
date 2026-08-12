"""Axial-load and uniaxial-moment (P-M interaction) design of RC columns.

Implements the ACI 318-19 strain-compatibility capacity method for tied,
symmetrically reinforced rectangular columns. NSCP 2015 uses the same
formulas through its ACI 318-08/11 lineage; where NSCP 2015 section numbers
differ the equivalence is stated in a comment, never silently substituted.

Scope: tied rectangular columns under axial compression + uniaxial moment.
Explicitly out of scope (documented, not implemented): biaxial bending,
slenderness / P-delta amplification, spiral reinforcement, tension members,
column shear design (ties are sized for confinement only; phi*Vc is not
checked).

Units: Pu in kN, Mu in kN*m, dimensions in mm, stresses in MPa; forces come
out in N, moments in N*mm.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .flexure import BAR_DIAMETERS_MM, bar_area
from .materials import Material, PHI_COMPRESSION, PHI_FLEXURE, beta1

# Extreme-compression-fiber strain, ACI 318-19 22.2.2.1
# (NSCP 2015 Sec 409.3.1 is the equivalent provision).
EPS_CU = 0.003

# Longitudinal steel limits, ACI 318-19 10.6.1.1 (NSCP 2015 Sec 410.6.2.1,
# ACI 318-08/11 10.9.1): 1% to 8% of gross area, minimum 4 bars.
RHO_MIN_COLUMN: float = 0.01
RHO_MAX_COLUMN: float = 0.08

# Interaction curve resolution: neutral-axis depth samples from the
# pure-flexure point to the pure-axial point.
_CURVE_N = 200


def axial_capacity(ast: float, b: float, h: float, fc: float, fy: float) -> float:
    """Design axial strength phi*Pn,max (N) of a tied column.

    phi*Pn,max = 0.80 * phi * Po with Po = 0.85 fc (Ag - Ast) + fy Ast,
    ACI 318-19 22.4.2.2 (NSCP 2015 Sec 410.3.5.2, ACI 318-08/11 10.3.6.2).
    The 0.80 factor is for tied columns; spirals (0.85) are out of scope.
    """
    po = 0.85 * fc * (b * h - ast) + fy * ast
    return 0.80 * PHI_COMPRESSION * po


def nominal_point(
    ast: float, b: float, h: float, d_prime: float, concrete: Material, c: float
) -> tuple[float, float, float]:
    """Nominal strength (Pn, Mn) in N / N*mm and phi at neutral-axis depth c (mm).

    Steel is symmetric: Ast/2 on each face perpendicular to the moment axis,
    at d' from the face (side bars count toward Ast but not flexure - the
    standard hand-calculation simplification). Pn and Mn are positive for
    compression and bending that compresses the near face.

    Pn = Cc + Cs' + Ts, Mn = Cc (h/2 - a/2) + (h/2 - d') (Cs' - Ts) with
    Cc = 0.85 fc a b (Whitney block, ACI 318-19 22.2.2.1), Cs' net of the
    displaced concrete. phi follows Table 21.2.2 (NSCP 2015 Sec 409.3.2 uses
    the same values): 0.90 for eps_t >= 0.005, 0.65 for eps_t <= eps_y,
    linear interpolation between.
    """
    d = h - d_prime
    half = ast / 2.0
    eps_t = EPS_CU * (c - d) / c  # extreme tension-face steel, + = compression
    eps_sp = EPS_CU * (c - d_prime) / c
    fs_t = min(max(concrete.es * eps_t, -concrete.fy), concrete.fy)
    fs_p = min(max(concrete.es * eps_sp, -concrete.fy), concrete.fy)
    a = min(beta1(concrete.fc) * c, h)
    cc = 0.85 * concrete.fc * a * b
    cs = half * (fs_p - 0.85 * concrete.fc)  # compression steel, net of concrete
    t = half * fs_t
    pn = cc + cs + t
    mn = cc * (h / 2.0 - a / 2.0) + (h / 2.0 - d_prime) * (cs - t)
    eps_y = concrete.epsilon_y
    eps_tt = -eps_t  # net tensile strain, tension positive (ACI 318-19 21.2.2)
    if eps_tt >= 0.005:
        phi = PHI_FLEXURE
    elif eps_tt <= eps_y:
        phi = PHI_COMPRESSION
    else:
        phi = PHI_COMPRESSION + 0.25 * (eps_tt - eps_y) / (0.005 - eps_y)
    return pn, mn, phi


def _interaction_curve(
    ast: float, b: float, h: float, d_prime: float, concrete: Material
) -> list[tuple[float, float]]:
    """Phi-reduced interaction curve: (phi*Pn, phi*Mn) pairs, N and N*mm.

    Sampled from the pure-flexure point (Pn ~ 0) to the pure-axial point
    (all steel at fy, Pn = Po). Single-valued in phi*Pn; phi*Mn is not
    monotone (it peaks near the balanced point, then falls toward zero at
    pure axial) - interpolation must bracket by phi*Pn, which it does. The
    top of the curve is not capped here (the 0.80 phi Po cap is applied by
    axial_capacity for design checks).
    """
    d = h - d_prime
    c_hi = max(h / beta1(concrete.fc), d / (1.0 - concrete.epsilon_y / EPS_CU))
    c_lo = 0.05 * d
    pts: list[tuple[float, float]] = []
    for i in range(_CURVE_N + 1):
        c = c_lo + (c_hi - c_lo) * i / _CURVE_N
        pn, mn, phi = nominal_point(ast, b, h, d_prime, concrete, c)
        if pn >= 0.0:
            pts.append((phi * pn, phi * mn))
    return pts


def phi_mn_at_pu(
    ast: float, b: float, h: float, d_prime: float, concrete: Material, pu_n: float
) -> float:
    """Design moment capacity phi*Mn (N*mm) at factored axial load Pu (N, +).

    Linear interpolation on the phi-reduced interaction curve. Below the
    pure-flexure point (Pu <= 0) the pure-flexure capacity is returned;
    tension members are therefore checked at Pu = 0 (explicit tie design is
    future work).
    """
    curve = _interaction_curve(ast, b, h, d_prime, concrete)
    if not curve:
        return 0.0
    if pu_n <= curve[0][0]:
        return curve[0][1]
    for (p1, m1), (p2, m2) in zip(curve, curve[1:]):
        if p1 <= pu_n <= p2:
            frac = (pu_n - p1) / (p2 - p1)
            return m1 + frac * (m2 - m1)
    return curve[-1][1]


def _bar_configs(ast_min: float, ast_max: float) -> list[tuple[float, int]]:
    """(diameter, count) pairs with even count >= 4 and area in [ast_min, ast_max].

    Sorted by bar count then area, so the first config that passes the
    capacity check is the fewest bars (ties: least excess steel), matching
    the beam select_bars convention. Even counts keep the symmetric two-face
    layout (count/2 bars per face); small diameters drop out naturally at
    high counts.
    """
    out: list[tuple[float, int]] = []
    for dm in BAR_DIAMETERS_MM:
        n = 4
        while True:
            area = n * bar_area(dm)
            if area > ast_max:
                break
            if area >= ast_min:
                out.append((dm, n))
            n += 2
    return sorted(out, key=lambda cfg: (cfg[1], cfg[1] * bar_area(cfg[0])))


def tie_spacing(diameter: float, tie_diameter: float, b: float, h: float) -> float:
    """Vertical tie spacing (mm): least of 16 d_b, 48 d_tie, least dimension.

    ACI 318-19 25.7.2.1 (NSCP 2015 Sec 415, ACI 318-08/11 7.10.5 is the
    equivalent provision), rounded down to a 10 mm increment.
    """
    s = min(16.0 * diameter, 48.0 * tie_diameter, min(b, h))
    return int(s // 10) * 10.0


@dataclass
class ColumnDesignResult:
    """Packaged axial + uniaxial-moment design for a tied rectangular column.

    Forces in N (moments in N*mm), areas in mm^2, stresses in MPa.
    """

    pu_kn: float
    mu_knm: float
    b: float
    h: float
    fc: float
    fy: float
    ast_required: float  # longitudinal steel, mm^2 (equals ast_provided)
    ast_provided: float  # mm^2
    bars: tuple[tuple[float, int], ...]  # (diameter_mm, count), symmetric 2-face
    rho: float
    tie_diameter: float
    tie_spacing: float
    phi_pn_max: float  # N, 0.80 phi Po for the tied column
    phi_mn_at_pu: float  # N*mm, moment capacity at the design axial load
    mu_nmm: float
    ok: bool
    notes: list[str] = field(default_factory=list)

    @property
    def rho_min(self) -> float:
        """Minimum longitudinal ratio, ACI 318-19 10.6.1.1."""
        return RHO_MIN_COLUMN

    @property
    def rho_max(self) -> float:
        """Maximum longitudinal ratio, ACI 318-19 10.6.1.1."""
        return RHO_MAX_COLUMN

    @property
    def util(self) -> float:
        """Max demand/capacity ratio over the axial and moment checks."""
        axial = self.pu_kn * 1e3 / self.phi_pn_max if self.phi_pn_max > 0.0 else 0.0
        moment = self.mu_nmm / self.phi_mn_at_pu if self.phi_mn_at_pu > 0.0 else 0.0
        return max(axial, moment)


def design_column(
    pu_kn: float,
    mu_knm: float,
    b: float,
    h: float,
    fc: float,
    fy: float,
    es: float = 200_000.0,
    d_prime: float = 60.0,
    tie_diameter: float = 10.0,
) -> ColumnDesignResult:
    """Design a tied rectangular column for axial load + uniaxial moment.

    Selects the smallest bar configuration (even count >= 4, area between
    1% and 8% of Ag) whose phi-reduced interaction curve contains the demand
    point: Pu <= phi*Pn,max and Mu <= phi*Mn(Pu), with strains and phi per
    ACI 318-19 22.2.2.1 / Table 21.2.2. When no configuration fits, the
    largest one is returned with ok=False and a note.

    Pu compression positive (kN); Mu in kN*m; b, h, d' in mm; stresses in MPa.
    Raises ValueError when the section is too small for the minimum steel or
    when d' leaves no room for the bars (h <= 2 d').

    ponytail: no check that count/2 bars of the chosen diameter fit across
    the face with ACI 318-19 25.2.1 clear spacing; add a fit/clearance check
    when member geometry matters (same limitation as beam select_bars).
    """
    if b <= 0.0 or h <= 0.0:
        raise ValueError(f"invalid column section {b} x {h}")
    if h <= 2.0 * d_prime or b <= 2.0 * d_prime:
        raise ValueError("d' is too large for the column section")
    if fy <= 0.0 or fy >= es * EPS_CU:
        raise ValueError(
            f"invalid fy {fy} MPa (0 < fy < es*EPS_CU = {es * EPS_CU:.0f} MPa)")
    concrete = Material(fc=fc, fy=fy, es=es)
    ag = b * h
    configs = _bar_configs(RHO_MIN_COLUMN * ag, RHO_MAX_COLUMN * ag)
    if not configs:
        raise ValueError("column section too small for the minimum 4-bar reinforcement")
    pu_n = pu_kn * 1e3
    mu_nmm = mu_knm * 1e6
    for dm, n in configs:
        ast = n * bar_area(dm)
        phi_pn_max = axial_capacity(ast, b, h, fc, fy)
        phi_mn = phi_mn_at_pu(ast, b, h, d_prime, concrete, pu_n)
        if pu_n <= phi_pn_max and mu_nmm <= phi_mn:
            return ColumnDesignResult(
                pu_kn=pu_kn, mu_knm=mu_knm, b=b, h=h, fc=fc, fy=fy,
                ast_required=ast, ast_provided=ast, bars=((dm, n),),
                rho=ast / ag, tie_diameter=tie_diameter,
                tie_spacing=tie_spacing(dm, tie_diameter, b, h),
                phi_pn_max=phi_pn_max, phi_mn_at_pu=phi_mn, mu_nmm=mu_nmm,
                ok=True,
            )
    # No configuration fits: report the maximum-steel configuration with the
    # failing checks so the workbook shows the best achievable capacity.
    dm, n = max(configs, key=lambda cfg: cfg[1] * bar_area(cfg[0]))
    ast = n * bar_area(dm)
    phi_pn_max = axial_capacity(ast, b, h, fc, fy)
    phi_mn = phi_mn_at_pu(ast, b, h, d_prime, concrete, pu_n)
    notes = []
    if pu_n > phi_pn_max:
        notes.append(
            f"Pu {pu_kn:.0f} kN exceeds phi*Pn,max {phi_pn_max / 1e3:.0f} kN "
            "even at maximum steel: enlarge the section."
        )
    if mu_nmm > phi_mn:
        notes.append(
            f"Mu {mu_knm:.0f} kN*m exceeds phi*Mn {phi_mn / 1e6:.0f} kN*m at "
            "Pu even at maximum steel: enlarge the section."
        )
    return ColumnDesignResult(
        pu_kn=pu_kn, mu_knm=mu_knm, b=b, h=h, fc=fc, fy=fy,
        ast_required=ast, ast_provided=ast, bars=((dm, n),),
        rho=ast / ag, tie_diameter=tie_diameter,
        tie_spacing=tie_spacing(dm, tie_diameter, b, h),
        phi_pn_max=phi_pn_max, phi_mn_at_pu=phi_mn, mu_nmm=mu_nmm,
        ok=False, notes=notes,
    )
