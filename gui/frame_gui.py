"""FreeSimpleGUI frontend for the rc-matrix-solver frame engine.

Lets a user tweak the demo propped L-frame (column + beam, UDL + lateral
push), run the Direct Stiffness solver, and cross-check the results: base
reactions, member end forces, and a built-in equilibrium check (sum Fx, sum
Fy, sum M about the base - all ~0 when the model balances).

Follows the FreeSimpleGUI pattern from Engr. Jaydee's "Python GUI for
Engineers" blog (third_party/simple-beam-calculator): layout, read loop,
keyed inputs, popup_error on bad input.

Run:  python3 gui/frame_gui.py   (requires: pip install freesimplegui)

Self-check:  python3 gui/frame_gui.py --check
verifies solve_lframe against the demo workbook numbers headlessly (no window).
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from solver import Frame, Member, NodalLoad, Node, Section, Support, UDL, solve

#: Defaults = the demo L-frame (examples/rc_matrix_solver_demo.xlsx).
DEFAULTS = {
    "h": 5.0, "l": 6.0,                       # column height, beam span (m)
    "e": 25e6,                                 # kN/m^2 (fc'=28 MPa, Ec ~ 25 GPa)
    "a_col": 0.16, "i_col": 0.002133,         # 400x400 column (m^2, m^4)
    "a_beam": 0.15, "i_beam": 0.003125,       # 300x500 beam
    "w": 20.0, "fx": 30.0,                    # beam UDL (kN/m), lateral push (kN)
}


def solve_lframe(h: float, l: float, e: float, a_col: float, i_col: float,
                 a_beam: float, i_beam: float, w: float, fx: float) -> dict:
    """Solve the propped L-frame; return reactions, member forces, equilibrium.

    Geometry: N1 (0,0) fixed; column up to N2 (0,h); beam to N3 (l,h) roller.
    Loads: UDL w on the beam, lateral push fx at N2. Units: kN, m.
    """
    frame = Frame(
        nodes=[Node(0.0, 0.0), Node(0.0, h), Node(l, h)],
        members=[
            Member(0, 1, Section(E=e, A=a_col, I=i_col)),
            Member(1, 2, Section(E=e, A=a_beam, I=i_beam)),
        ],
        supports={0: Support(ux=True, uy=True, rz=True), 2: Support(uy=True)},
        nodal_loads={1: NodalLoad(fx=fx)},
        member_loads={1: [UDL(w=w)]},
    )
    sol = solve(frame)
    rx, ry, mz = sol.reactions[0]
    ry_roller = sol.reactions[2][1]
    n_col, v_col, m_col_i = sol.member_forces[0][0], sol.member_forces[0][1], sol.member_forces[0][2]
    m_beam_i, m_beam_j = sol.member_forces[1][2], sol.member_forces[1][5]
    # Equilibrium residuals (cross-check): sum Fx, sum Fy, sum M about N1.
    sum_fx = rx + fx
    sum_fy = ry + ry_roller - w * l
    sum_m = mz + ry_roller * l - fx * h - w * l * (l / 2.0)
    return {
        "rx": rx, "ry": ry, "mz": mz, "ry_roller": ry_roller,
        "n_col": n_col, "v_col": v_col, "m_col_i": m_col_i,
        "m_beam_i": m_beam_i, "m_beam_j": m_beam_j,
        "sum_fx": sum_fx, "sum_fy": sum_fy, "sum_m": sum_m,
        # For the web figure: original node coords + raw global displacements.
        "nodes": [(0.0, 0.0), (0.0, h), (l, h)],
        "u": [float(v) for v in sol.u],  # [ux1, uy1, rz1, ux2, uy2, rz2, ux3, uy3, rz3]
        "w": w, "fx": fx,
        # Generic-frame shape so the web figure renders both demo and custom models.
        "members": [[0, 1], [1, 2]],
        "supports": {0: [True, True, True], 2: [False, True, False]},
        "nodal_loads": {1: [fx, 0.0, 0.0]},
        "member_loads": {1: [w]},
        "reactions": {0: [rx, ry, mz], 2: [0.0, ry_roller, 0.0]},
        "eq": {"fx": sum_fx, "fy": sum_fy, "m": sum_m,
               "ok": bool(abs(sum_fx) < 1e-6 and abs(sum_fy) < 1e-6 and abs(sum_m) < 1e-6)},
    }


def _fmt(results: dict) -> str:
    """Format results for the GUI output pane."""
    return (
        f"Base reactions   Rx = {results['rx']:9.3f} kN\n"
        f"                 Ry = {results['ry']:9.3f} kN\n"
        f"                 Mz = {results['mz']:9.3f} kN*m\n"
        f"Roller reaction  Ry = {results['ry_roller']:9.3f} kN\n"
        f"Column  axial   N  = {results['n_col']:9.3f} kN\n"
        f"         base M    = {results['m_col_i']:9.3f} kN*m\n"
        f"Beam    end M at col = {results['m_beam_i']:9.3f} kN*m\n"
        f"         end M at roller = {results['m_beam_j']:9.3f} kN*m\n"
        f"------------------------------\n"
        f"Equilibrium (should be ~0)\n"
        f"  sum Fx = {results['sum_fx']:9.3e} kN\n"
        f"  sum Fy = {results['sum_fy']:9.3e} kN\n"
        f"  sum M  = {results['sum_m']:9.3e} kN*m"
    )


def main() -> int:
    try:
        import FreeSimpleGUI as sg
    except ImportError:
        print("FreeSimpleGUI is not installed; run `pip install freesimplegui`")
        return 1

    d = DEFAULTS
    layout = [
        [sg.Text("Column height", size=(16, 1)), sg.Input(str(d["h"]), key="-H-", size=(14, 1)), sg.Text("m")],
        [sg.Text("Beam span", size=(16, 1)), sg.Input(str(d["l"]), key="-L-", size=(14, 1)), sg.Text("m")],
        [sg.Text("E (all members)", size=(16, 1)), sg.Input(str(d["e"]), key="-E-", size=(14, 1)), sg.Text("kN/m^2")],
        [sg.Text("Column A", size=(16, 1)), sg.Input(str(d["a_col"]), key="-A_COL-", size=(14, 1)), sg.Text("m^2")],
        [sg.Text("Column I", size=(16, 1)), sg.Input(str(d["i_col"]), key="-I_COL-", size=(14, 1)), sg.Text("m^4")],
        [sg.Text("Beam A", size=(16, 1)), sg.Input(str(d["a_beam"]), key="-A_BEAM-", size=(14, 1)), sg.Text("m^2")],
        [sg.Text("Beam I", size=(16, 1)), sg.Input(str(d["i_beam"]), key="-I_BEAM-", size=(14, 1)), sg.Text("m^4")],
        [sg.Text("Beam UDL w", size=(16, 1)), sg.Input(str(d["w"]), key="-W-", size=(14, 1)), sg.Text("kN/m")],
        [sg.Text("Lateral push Fx at joint", size=(16, 1)), sg.Input(str(d["fx"]), key="-FX-", size=(14, 1)), sg.Text("kN")],
        [sg.Button("Solve", key="-SOLVE-")],
        [sg.Multiline("", key="-RESULTS-", size=(44, 12), disabled=True)],
    ]
    window = sg.Window("rc-matrix-solver - propped L-frame", layout)

    while True:
        event, values = window.read()
        if event in (sg.WIN_CLOSED, None):
            break
        if event == "-SOLVE-":
            try:
                results = solve_lframe(
                    h=float(values["-H-"]), l=float(values["-L-"]), e=float(values["-E-"]),
                    a_col=float(values["-A_COL-"]), i_col=float(values["-I_COL-"]),
                    a_beam=float(values["-A_BEAM-"]), i_beam=float(values["-I_BEAM-"]),
                    w=float(values["-W-"]), fx=float(values["-FX-"]),
                )
            except ValueError:
                sg.popup_error("Wrong inputs: enter numbers only.", title="Error")
                continue
            window["-RESULTS-"].update(_fmt(results))
    window.close()
    return 0


def _check() -> int:
    """Headless self-check: demo defaults must match the demo workbook."""
    r = solve_lframe(**{k: v for k, v in DEFAULTS.items()})
    tol = 1e-6
    checks = {
        "rx": -30.0, "ry": 53.38236501664918, "mz": 110.2941900998947,
        "ry_roller": 66.61763498335081,
    }
    for name, want in checks.items():
        assert abs(r[name] - want) <= tol * max(1.0, abs(want)), f"{name}: {r[name]} != {want}"
    assert abs(r["sum_fx"]) < 1e-9 and abs(r["sum_fy"]) < 1e-9 and abs(r["sum_m"]) < 1e-6
    print("gui self-check OK: solver matches demo workbook, equilibrium ~0")
    return 0


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(_check())
    sys.exit(main())
