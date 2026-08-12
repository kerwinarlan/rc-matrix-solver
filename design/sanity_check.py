"""Runnable sanity check for the design package.

Verifies flexure, shear and column design against hand-computed values for
standard sections (b=300, d=500, d'=60, fc'=28 MPa, fy=420 MPa, Es=200 GPa
beams; 400x400 columns) - the classic singly/doubly reinforced, stirrup,
and P-M interaction cases.

Run from the repo root:
    python3 -m design.sanity_check
"""

from design.checks import design_beam, design_members
from design.column import axial_capacity, design_column, nominal_point
from design.flexure import bar_area, design_flexure
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

    # --- Column: pure axial, stocky short column (ACI 318-19 22.4.2.2) -----
    # 8-25 mm bars: Ast = 3927 mm^2. Po = 0.85*28*(160000-3927) + 420*3927
    # = 5363.9 kN; phi*Pn,max = 0.80 * 0.65 * Po = 2789.2 kN (tied column).
    ast8 = 8.0 * bar_area(25.0)
    assert abs(ast8 - 3926.99) < TOL * 3926.99, ast8
    assert abs(axial_capacity(ast8, 400.0, 400.0, 28.0, 420.0) - 2789.2e3) < TOL * 2789.2e3

    # --- Column: one interaction point (tension-controlled limit) -----------
    # c = 0.375 d = 127.5 mm -> eps_t = 0.005, phi = 0.90. Hand solution by
    # strain compatibility (ACI 318-19 22.2.2.1, Table 21.2.2):
    # Pn = 784.0 kN, Mn = 346.7 kN*m, so phi*Pn = 705.6 kN, phi*Mn = 312.0 kN*m.
    pn, mn, phi = nominal_point(ast8, 400.0, 400.0, 60.0, c, 0.375 * 340.0)
    assert abs(phi - 0.90) < 1e-9, phi
    assert abs(pn - 784.0e3) < TOL * 784.0e3, pn
    assert abs(mn - 346.7e6) < TOL * 346.7e6, mn

    # --- Column: design (Pu = 2500 kN, Mu = 100 kN*m) -----------------------
    # Needs 4-32 mm (3217 mm^2): smaller configs fail the axial check
    # (phi*Pn,max = 2385 kN for 4-25 mm < 2500 kN).
    col = design_column(2500.0, 100.0, 400.0, 400.0, 28.0, 420.0)
    assert col.ok
    assert col.bars == ((32.0, 4),), col.bars
    assert col.ast_provided >= 0.01 * 400.0 * 400.0
    assert col.bars[0][1] % 2 == 0 and col.bars[0][1] >= 4
    assert col.tie_spacing <= 16.0 * col.bars[0][0]
    assert col.phi_pn_max >= 2500.0e3 and col.phi_mn_at_pu >= 100.0e6
    assert col.util <= 1.0
    # Axial over-capacity fails even at maximum steel (Pu = 5000 kN > 4609 kN).
    assert not design_column(5000.0, 100.0, 400.0, 400.0, 28.0, 420.0).ok
    # Moment over-capacity fails at maximum steel (Mu = 800 kN*m > 698 kN*m).
    assert not design_column(0.0, 800.0, 400.0, 400.0, 28.0, 420.0).ok

    # --- Bridge adapter: column member (design_members contract) ------------
    # Vertical member 1 (0,0) -> (0,5), 400x400 (A = 0.16 m^2, I = 0.002133
    # m^4), Pu = 53.4 kN compression, Mu = 110.3 kN*m: designed as a column
    # with 4-25 mm bars; the horizontal member stays a beam.
    out2 = design_members(
        {"fc": 28_000.0, "fy": 420_000.0, "es": 200_000_000.0},
        [
            {"id": 1, "i_node": 1, "j_node": 2, "E": 2e10, "A": 0.16, "I": 0.002133,
             "i_x": 0.0, "i_y": 0.0, "j_x": 0.0, "j_y": 5.0},
            {"id": 2, "i_node": 2, "j_node": 3, "E": 2e10, "A": 0.15, "I": 0.003125,
             "i_x": 0.0, "i_y": 5.0, "j_x": 6.0, "j_y": 5.0},
        ],
        [(53.3824, 30.0, 110.2942, 39.7058), (0.0, 53.3824, -39.7058, 0.0)],
    )
    assert out2[0]["type"] == "COLUMN" and out2[0]["ok"]
    assert out2[0]["as_prov"] == 4.0 * bar_area(25.0)
    # Section derived from A/I is 400.0 x 399.97 mm, so the tie spacing
    # (least of 16 d_b, 48 d_tie, least dimension) rounds to 390-400 mm.
    assert 390.0 <= out2[0]["stirrup_spacing"] <= 400.0
    assert out2[0]["phi_pn_kn"] >= out2[0]["pu_kn"]
    assert out2[0]["util"] <= 1.0
    assert out2[1]["type"] == "BEAM" and out2[1]["ok"]
    # Beam governed by rho_min on the 300x500 equivalent section: 440 mm^2.
    assert abs(out2[1]["as_req"] - 440.0) < TOL * 440.0
    assert out2[1]["stirrup_spacing"] > 0.0

    # fy at es*EPS_CU (600 MPa) would make the strain-compatibility curve
    # degenerate (eps_y = eps_cu): rejected as ValueError, never a divide by
    # zero, and the bridge fallback row stays labeled COLUMN.
    try:
        design_column(1000.0, 50.0, 400.0, 400.0, 28.0, 600.0)
        raise AssertionError("fy = 600 MPa must raise ValueError")
    except ValueError:
        pass
    bad_col = design_members(
        {"fc": 28_000.0, "fy": 600_000.0, "es": 200_000_000.0},
        [{"id": 1, "i_node": 1, "j_node": 2, "E": 2e10, "A": 0.16, "I": 0.002133,
          "i_x": 0.0, "i_y": 0.0, "j_x": 0.0, "j_y": 5.0}],
        [(100.0, 10.0, 20.0, 20.0)],
    )
    assert bad_col[0]["type"] == "COLUMN" and not bad_col[0]["ok"]
    assert bad_col[0]["as_req"] == 0.0 and bad_col[0]["phi_pn_kn"] == 0.0

    print("All design sanity checks passed.")


if __name__ == "__main__":
    demo()
