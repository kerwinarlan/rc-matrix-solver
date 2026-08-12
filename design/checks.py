"""Result packaging and beam-level orchestration for the design package."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt

from .column import design_column
from .flexure import FlexureDesign, design_flexure
from .materials import Material
from .shear import ShearDesign, design_shear


@dataclass
class BeamDesignResult:
    """Packaged flexure + shear design for a rectangular RC beam section.

    Forces in N (moments in N*mm), dimensions in mm, stresses in MPa.
    """

    mu_knm: float
    vu_kn: float
    b: float
    d: float
    d_prime: float
    fc: float
    fy: float
    flexure: FlexureDesign
    shear: ShearDesign
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when both flexure and shear checks pass."""
        return self.flexure.ok and self.shear.ok


def design_beam(
    Mu_kNm: float,
    Vu_kN: float,
    b: float,
    d: float,
    d_prime: float,
    fc: float,
    fy: float,
    es: float = 200_000.0,
    stirrup_diameter: float = 10.0,
    legs: int = 2,
    detailed_vc: bool = False,
    rho_w: float | None = None,
    mu_for_vc_knm: float | None = None,
) -> BeamDesignResult:
    """Design a rectangular beam section for flexure and shear (singly or doubly reinforced).

    Plain-argument input contract: the solver bridge calls this with Mu, Vu
    (kN*m, kN) and section/material values only; no solver object is required.

    Extension points: T-beams and columns need their own geometry handling
    (flange effective width, axial-load interaction) - the per-force functions
    design_flexure/design_shear already isolate the section logic.

    Units: Mu in kN*m, Vu in kN, dimensions in mm, stresses in MPa.
    """
    concrete = Material(fc=fc, fy=fy, es=es)
    flexure = design_flexure(Mu_kNm, b, d, d_prime, concrete)
    shear = design_shear(
        Vu_kN,
        concrete,
        b,
        d,
        stirrup_diameter=stirrup_diameter,
        legs=legs,
        detailed_vc=detailed_vc,
        rho_w=rho_w if rho_w is not None else flexure.rho,
        mu_knm=mu_for_vc_knm if mu_for_vc_knm is not None else Mu_kNm,
    )
    return BeamDesignResult(Mu_kNm, Vu_kN, b, d, d_prime, fc, fy, flexure, shear)


def _is_column(member: dict) -> bool:
    """True when a member is designed as a column: near-vertical (|dy| >= |dx|).

    Member dicts carry optional node coordinates i_x/i_y/j_x/j_y (added by
    bridge/run.py); without them every member is a beam, preserving the
    original behavior. Exact member-type selection from the model is future
    work; this orientation heuristic matches the demo L-frame.
    """
    if all(k in member for k in ("i_x", "i_y", "j_x", "j_y")):
        dx = member["j_x"] - member["i_x"]
        dy = member["j_y"] - member["i_y"]
        return abs(dy) >= abs(dx)
    return False


def _util(pu_kn: float, phi_pn_kn: float, mu_knm: float, phi_mn_knm: float) -> float:
    """Max demand/capacity ratio over the axial and moment checks."""
    axial = pu_kn / phi_pn_kn if phi_pn_kn > 0.0 else 0.0
    moment = mu_knm / phi_mn_knm if phi_mn_knm > 0.0 else 0.0
    return max(axial, moment)


# Default cover (mm) used when a section depth must be derived from A/I.
DEFAULT_COVER_MM: float = 60.0


def design_members(
    materials: dict,
    members: list[dict],
    member_forces: list[tuple],
    cover_mm: float = DEFAULT_COVER_MM,
) -> list[dict]:
    """Bridge adapter: design every member from solver member forces.

    Matches the contract pinned in docs/excel-bridge-architecture.md sec. 8:
    materials ``{"fc", "fy", "es"}`` in kN/m^2 (converted to MPa here, /1000);
    members ``[{"id", "i_node", "j_node", "E", "A", "I"}]``; member_forces
    ``(axial, shear, m_i, m_j)`` in kN, kN, kN*m, kN*m per member, input order.
    Returns one dict per member, input order: the pinned beam keys
    ``{"as_req", "as_prov", "stirrup_spacing"}`` plus ``{"type", "pu_kn",
    "phi_pn_kn", "phi_mn_knm", "util", "ok"}``: for a column, as_req/as_prov
    are the longitudinal steel and stirrup_spacing the tie spacing; for a
    beam they are the flexure steel and stirrup spacing.

    The section is derived from the member's A (m^2) and I (m^4) as the
    equivalent rectangle b x h (h = sqrt(12*I/A), b = A/h), with d = h - cover
    and d' = cover. Mu = max(|m_i|, |m_j|), Vu = |shear|, Pu = axial
    (compression positive, solver local axes). Near-vertical members (|dy| >=
    |dx| from the optional i_x/i_y/j_x/j_y keys) are designed as columns per
    design.column; the rest as beams. Members with no valid A/I yield zeros -
    the workbook has no section-dimension columns yet.

    ponytail: axial force is ignored for beams (flexure only); the column
    path covers axial load + uniaxial moment. T-beams need flange geometry,
    not derivable from A/I alone. Biaxial bending, slenderness and spiral
    columns are documented future work in design/column.py.
    """
    fc = materials.get("fc", 0.0) / 1000.0
    fy = materials.get("fy", 0.0) / 1000.0
    es = materials.get("es", 200_000_000.0) / 1000.0
    out: list[dict] = []
    for member, forces in zip(members, member_forces):
        a_m2 = float(member.get("A", 0.0))
        i_m4 = float(member.get("I", 0.0))
        mu = max(abs(forces[2]), abs(forces[3]))  # kN*m
        vu = abs(forces[1])  # kN
        if a_m2 <= 0.0 or i_m4 <= 0.0 or fc <= 0.0 or fy <= 0.0:
            out.append({"as_req": 0.0, "as_prov": 0.0, "stirrup_spacing": 0.0})
            continue
        h_mm = sqrt(12.0 * i_m4 / a_m2) * 1000.0  # rectangle depth, mm
        b_mm = a_m2 / (h_mm / 1000.0) * 1000.0
        if h_mm <= 2.0 * cover_mm:
            out.append({"as_req": 0.0, "as_prov": 0.0, "stirrup_spacing": 0.0})
            continue
        if _is_column(member):
            try:
                result = design_column(
                    pu_kn=forces[0], mu_knm=mu, b=b_mm, h=h_mm,
                    fc=fc, fy=fy, es=es, d_prime=cover_mm,
                )
            except ValueError:
                out.append({
                    "as_req": 0.0, "as_prov": 0.0, "stirrup_spacing": 0.0,
                    "type": "COLUMN", "pu_kn": forces[0], "phi_pn_kn": 0.0,
                    "phi_mn_knm": 0.0, "util": 0.0, "ok": False,
                })
                continue
            phi_pn_kn = result.phi_pn_max / 1e3
            phi_mn_knm = result.phi_mn_at_pu / 1e6
            out.append({
                "as_req": result.ast_required,
                "as_prov": result.ast_provided,
                "stirrup_spacing": result.tie_spacing,
                "type": "COLUMN",
                "pu_kn": result.pu_kn,
                "phi_pn_kn": phi_pn_kn,
                "phi_mn_knm": phi_mn_knm,
                "util": _util(result.pu_kn, phi_pn_kn, result.mu_knm, phi_mn_knm),
                "ok": result.ok,
            })
            continue
        try:
            result = design_beam(
                Mu_kNm=mu, Vu_kN=vu, b=b_mm, d=h_mm - cover_mm,
                d_prime=cover_mm, fc=fc, fy=fy, es=es,
            )
        except ValueError:
            # Section geometry or load makes a valid design impossible.
            out.append({"as_req": 0.0, "as_prov": 0.0, "stirrup_spacing": 0.0})
            continue
        phi_mn_knm = result.flexure.phi_mn_provided / 1e6
        out.append({
            "as_req": result.flexure.as_required,
            "as_prov": result.flexure.as_provided,
            "stirrup_spacing": result.shear.s_selected,
            "type": "BEAM",
            "pu_kn": forces[0],
            "phi_pn_kn": 0.0,
            "phi_mn_knm": phi_mn_knm,
            "util": _util(forces[0], 0.0, mu, phi_mn_knm),
            "ok": result.ok,
        })
    return out
