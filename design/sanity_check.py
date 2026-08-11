"""Runnable sanity check for the design package.

Verifies flexure and shear design against hand-computed values for a standard
rectangular beam (b=300, d=500, d'=60, fc'=28 MPa, fy=420 MPa, Es=200 GPa) -
the classic singly/doubly reinforced and stirrup-design cases.

Run from the repo root:
    python3 -m design.sanity_check
"""

from design.checks import design_beam, design_members
from design.flexure import design_flexure
from design.materials import Material, beta1
from design.shear import design_shear, vc_simplified

TOL = 0.01  # 1% relative tolerance on hand-computed values


def demo() -> None:
    c = Material(fc=28.0, fy=420.0)

    # --- Material helpers -------------------------------------------------
    assert beta1(28.0) == 0.85
    assert abs(beta1(35.0) - 0.80) < 1e-9
    assert beta1(55.0) == 0.65
    assert abs(vc_simplified(c, 300.0, 500.0) - 134_933.0) < TOL * 134_933.0

    # --- Flexure: singly reinforced (Mu = 300 kN*m) ------------------------
    # Hand solution: As_req = 1772 mm^2 (ACI 318-19 22.2.2.1, phi = 0.90).
    flex = design_flexure(300.0, 300.0, 500.0, 60.0, c)
    assert not flex.doubly
    assert abs(flex.as_required - 1772.0) < TOL * 1772.0, flex.as_required
    assert flex.as_provided >= flex.as_required
    assert flex.phi_mn_provided >= 300.0e6
    assert flex.ok

    # --- Flexure: doubly reinforced (Mu = 600 kN*m) ------------------------
    # Hand solution: As = 3729 mm^2, A's = 1049 mm^2 (compression steel does
    # not yield here: fs' = 408 MPa at c = 0.375 d).
    flex2 = design_flexure(600.0, 300.0, 500.0, 60.0, c)
    assert flex2.doubly
    assert abs(flex2.as_required - 3728.7) < TOL * 3728.7, flex2.as_required
    assert abs(flex2.as_compression_required - 1049.3) < TOL * 1049.3, flex2.as_compression_required
    assert flex2.phi_mn_provided >= 600.0e6
    assert flex2.ok

    # --- Shear: strength stirrups (Vu = 250 kN) ----------------------------
    # Hand solution: Av/s = 0.945 mm^2/mm; #10 2-leg stirrups -> s = 166 mm,
    # rounded down to 160 mm.
    sh = design_shear(250.0, c, 300.0, 500.0)
    assert sh.stirrups_required
    assert abs(sh.av_s_required - 0.9448) < TOL * 0.9448, sh.av_s_required
    assert sh.s_selected == 160.0, sh.s_selected
    assert sh.ok

    # --- Shear: minimum stirrups only (Vu = 80 kN) -------------------------
    sh2 = design_shear(80.0, c, 300.0, 500.0)
    assert sh2.stirrups_required
    assert sh2.vs == 0.0
    assert sh2.s_selected == 250.0, sh2.s_selected

    # --- Shear: none required (Vu = 40 kN) ---------------------------------
    sh3 = design_shear(40.0, c, 300.0, 500.0)
    assert not sh3.stirrups_required

    # --- Combined beam design ----------------------------------------------
    result = design_beam(Mu_kNm=300.0, Vu_kN=250.0, b=300.0, d=500.0, d_prime=60.0, fc=28.0, fy=420.0)
    assert result.ok
    assert result.flexure.as_required == flex.as_required
    assert result.shear.s_selected == 160.0

    # --- Bridge adapter (design_members, contract in docs/excel-bridge-architecture.md sec. 8) ---
    # A = 0.15 m^2, I = 0.003125 m^4 implies the 300x500 mm rectangle; materials
    # arrive in kN/m^2 (28 MPa = 28000 kN/m^2). Outputs must match design_beam
    # on the derived section (b=300, d=440, d'=60, cover=60).
    out = design_members(
        {"fc": 28_000.0, "fy": 420_000.0, "es": 200_000_000.0},
        [{"id": 1, "i_node": 1, "j_node": 2, "E": 2e10, "A": 0.15, "I": 0.003125}],
        [(0.0, 250.0, -300.0, 300.0)],
    )
    assert len(out) == 1
    expected = design_beam(Mu_kNm=300.0, Vu_kN=250.0, b=300.0, d=440.0, d_prime=60.0, fc=28.0, fy=420.0)
    assert abs(out[0]["as_req"] - expected.flexure.as_required) < 1e-9
    assert abs(out[0]["as_prov"] - expected.flexure.as_provided) < 1e-9
    assert abs(out[0]["stirrup_spacing"] - expected.shear.s_selected) < 1e-9
    # Invalid geometry yields zeros, never a raise.
    bad = design_members(
        {"fc": 28_000.0, "fy": 420_000.0, "es": 200_000_000.0},
        [{"id": 9, "i_node": 1, "j_node": 2, "E": 2e10, "A": 0.0, "I": 0.0}],
        [(0.0, 10.0, 5.0, 5.0)],
    )
    assert bad == [{"as_req": 0.0, "as_prov": 0.0, "stirrup_spacing": 0.0}]

    print("All design sanity checks passed.")


if __name__ == "__main__":
    demo()
