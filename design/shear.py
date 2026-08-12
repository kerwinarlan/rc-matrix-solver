"""Shear design (stirrups) of RC beams per ACI 318-19 Ch. 22.

NSCP 2015 Sec 411 is the equivalent chapter (ACI 318-08/11 lineage); per-formula
equivalences are noted in comments.
"""

from dataclasses import dataclass, field
from math import sqrt

from .flexure import bar_area
from .materials import Material, PHI_SHEAR


def vc_simplified(concrete: Material, bw: float, d: float) -> float:
    """Nominal concrete shear strength Vc (N), simplified method, ACI 318-19 22.5.5.1.

    NSCP 2015 Sec 411.4.1 (ACI 318-11 11.2.1.1) has the identical formula.
    Units: bw, d in mm; fc' in MPa -> Vc in N.
    """
    return 0.17 * sqrt(concrete.fc) * bw * d


def vc_detailed(concrete: Material, bw: float, d: float, rho_w: float, vu_n: float, mu_nmm: float) -> float:
    """Nominal concrete shear strength Vc (N), detailed method.

    NSCP 2015 Sec 411.4.2.2 (ACI 318-11 11.2.2.1):
        Vc = (0.16*sqrt(fc') + 17*rho_w*Vu*d/Mu) * bw * d  <=  0.29*sqrt(fc')*bw*d
    ACI 318-19 replaced this with 22.5.5.2 / 22.5.6 (MCFT-based methods); the
    older formula is kept here for NSCP 2015 compatibility. The Nu term is
    omitted (beams with no axial load).
    Units: vu_n in N, mu_nmm in N*mm.
    """
    if mu_nmm <= 0.0:
        # Mu -> 0 makes the Vu*d/Mu term unbounded, so the 0.29*sqrt(fc') cap governs.
        return 0.29 * sqrt(concrete.fc) * bw * d
    vc = (0.16 * sqrt(concrete.fc) + 17.0 * rho_w * vu_n * d / mu_nmm) * bw * d
    return min(vc, 0.29 * sqrt(concrete.fc) * bw * d)


def _av_s_min(concrete: Material, bw: float) -> float:
    """Minimum stirrup area per unit length (mm^2/mm), ACI 318-19 9.6.4.1.

    NSCP 2015 Sec 411.6.5.3 (ACI 318-11 11.6.3) has the identical formula.
    """
    return max(0.062 * sqrt(concrete.fc) * bw / concrete.fy, 0.35 * bw / concrete.fy)


@dataclass
class ShearDesign:
    """Result of shear design (stirrups) for a beam section.

    Forces in N, areas per length in mm^2/mm, spacings in mm.
    """

    vu: float  # factored shear, N
    phi_vc: float  # design concrete contribution, N
    stirrups_required: bool
    vs: float  # required stirrup contribution, N (0 when only minimum stirrups)
    vs_max: float  # limit per ACI 318-19 22.5.1.2, N
    av_s_required: float  # mm^2/mm
    av_s_min: float  # mm^2/mm
    s_max: float  # mm
    s_selected: float  # mm (0 when none required)
    stirrup_diameter: float  # mm
    legs: int
    av: float  # mm^2, stirrup area per spacing
    ok: bool
    notes: list[str] = field(default_factory=list)


def design_shear(
    Vu_kN: float,
    concrete: Material,
    bw: float,
    d: float,
    stirrup_diameter: float = 10.0,
    legs: int = 2,
    detailed_vc: bool = False,
    rho_w: float = 0.0,
    mu_knm: float = 0.0,
) -> ShearDesign:
    """Design stirrups for a beam section per ACI 318-19 Ch. 22 / NSCP 2015 Sec 411.

    - Vu <= 0.5*phi*Vc: no stirrups required (9.6.4.1 / NSCP 2015 Sec 411.6.5.1).
    - 0.5*phi*Vc < Vu <= phi*Vc: minimum stirrups only.
    - Vu > phi*Vc: Vs = Vu/phi - Vc, spacing s = Av/(Vs/(fy d))
      (22.5.10.5.3), rounded down to a 10 mm increment and capped at the max
      spacing of 9.7.6.2.2 (NSCP 2015 Sec 411.6.6.2). Vs is also checked
      against 0.66*sqrt(fc')*bw*d (22.5.1.2).

    Units: Vu in kN; bw, d in mm; stresses in MPa.
    """
    vu = Vu_kN * 1e3
    if detailed_vc:
        vc = vc_detailed(concrete, bw, d, rho_w, vu, mu_knm * 1e6)
    else:
        vc = vc_simplified(concrete, bw, d)
    phi_vc = PHI_SHEAR * vc
    av = legs * bar_area(stirrup_diameter)
    av_min = _av_s_min(concrete, bw)
    vs_max = 0.66 * sqrt(concrete.fc) * bw * d  # 22.5.1.2: concrete crushing limit

    if vu <= 0.5 * phi_vc:
        return ShearDesign(
            vu=vu, phi_vc=phi_vc, stirrups_required=False, vs=0.0, vs_max=vs_max,
            av_s_required=0.0, av_s_min=av_min, s_max=min(d / 2.0, 600.0),
            s_selected=0.0, stirrup_diameter=stirrup_diameter, legs=legs, av=av, ok=True,
        )

    if vu <= phi_vc:
        # Minimum stirrups only, ACI 318-19 9.6.4.1 / NSCP 2015 Sec 411.6.5.1.
        s_max = min(d / 2.0, 600.0)
        s = min(av / av_min, s_max)
        s = int(s // 10) * 10.0
        ok = s > 0.0
        notes = [] if ok else ["section too small for the chosen stirrup bar"]
        return ShearDesign(
            vu=vu, phi_vc=phi_vc, stirrups_required=True, vs=0.0, vs_max=vs_max,
            av_s_required=av_min, av_s_min=av_min, s_max=s_max, s_selected=s,
            stirrup_diameter=stirrup_diameter, legs=legs, av=av, ok=ok, notes=notes,
        )

    vs = vu / PHI_SHEAR - vc
    av_s_req = max(vs / (concrete.fy * d), av_min)  # 22.5.10.5.3 + 9.6.4.1
    # Max spacing, ACI 318-19 9.7.6.2.2 / NSCP 2015 Sec 411.6.6.2.
    s_max = min(d / 2.0, 600.0) if vs <= 0.33 * sqrt(concrete.fc) * bw * d else min(d / 4.0, 300.0)
    s = min(av / av_s_req, s_max)
    s = int(s // 10) * 10.0
    ok = vs <= vs_max and s > 0.0
    notes = []
    if vs > vs_max:
        notes.append("Vs exceeds 0.66*sqrt(fc')*bw*d (22.5.1.2): enlarge the section.")
    if s <= 0.0:
        notes.append("Required spacing below one 10 mm increment: enlarge section or stirrup bar.")
    return ShearDesign(
        vu=vu, phi_vc=phi_vc, stirrups_required=True, vs=vs, vs_max=vs_max,
        av_s_required=av_s_req, av_s_min=av_min, s_max=s_max, s_selected=s,
        stirrup_diameter=stirrup_diameter, legs=legs, av=av, ok=ok, notes=notes,
    )
