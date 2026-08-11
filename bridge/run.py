"""End-to-end orchestrator: template -> read inputs -> solver -> design -> write outputs.

Run: ``python3 bridge/run.py [--workbook rc_matrix_solver.xlsx]``

``solver/`` and ``design/`` are built in parallel by other workers; imports are
guarded, so this script completes as a documented no-op before they land. The
assumed solver/design public API is pinned in docs/excel-bridge-architecture.md
(section "Assumed solver/design API") - reconcile mismatches there.
"""

import argparse
import importlib
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge import InputData, OutputData, build_template, open_workbook


def _import_or_none(name: str) -> Optional[Any]:
    """Import a module, or None if it does not exist yet (parallel build)."""
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


def _inputs_to_models(inputs: InputData) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]],
                                                  Dict[str, List[Dict[str, Any]]], Dict[str, Any]]:
    """Assemble plain-data models from the flat input dict (documented contract).

    Row order is preserved everywhere: output rows line up with input rows.
    """
    nodes = [
        {"id": i, "x": x, "y": y, "sup_ux": ux, "sup_uy": uy, "sup_rz": rz}
        for i, x, y, ux, uy, rz in zip(
            inputs["NODE_ID"], inputs["NODE_X"], inputs["NODE_Y"],
            inputs["NODE_SUP_UX"], inputs["NODE_SUP_UY"], inputs["NODE_SUP_RZ"],
        )
    ]
    members = [
        {"id": mid, "i_node": i_node, "j_node": j_node, "E": e, "A": a, "I": i_inertia}
        for mid, i_node, j_node, e, a, i_inertia in zip(
            inputs["MEMBER_ID"], inputs["MEMBER_I_NODE"], inputs["MEMBER_J_NODE"],
            inputs["MEMBER_E"], inputs["MEMBER_A"], inputs["MEMBER_I"],
        )
    ]
    loads = {
        "nodal": [
            {"node": nid, "fx": fx, "fy": fy, "mz": mz}
            for nid, fx, fy, mz in zip(
                inputs["LOAD_NODE"], inputs["LOAD_N_FX"], inputs["LOAD_N_FY"], inputs["LOAD_N_MZ"],
            )
        ],
        "udl": [
            {"member": mid, "wx": wx, "wy": wy}
            for mid, wx, wy in zip(inputs["LOAD_MEMBER"], inputs["LOAD_U_WX"], inputs["LOAD_U_WY"])
        ],
    }
    materials = {
        "fc": inputs["MATERIAL_FC"][0] if inputs["MATERIAL_FC"] else 0.0,
        "fy": inputs["MATERIAL_FY"][0] if inputs["MATERIAL_FY"] else 0.0,
        "es": inputs["MATERIAL_ES"][0] if inputs["MATERIAL_ES"] else 0.0,
    }
    return nodes, members, loads, materials


def _assemble_outputs(nodes, members, solution, design_out) -> OutputData:
    """Flatten solver/design results into the named output dict the writer takes."""
    displacements = solution.displacements   # per node, input order: (ux, uy, rz)
    reactions = solution.reactions           # per node, input order: (fx, fy, mz)
    member_forces = solution.member_forces   # per member: (axial, shear, m_i, m_j)
    return {
        "OUT_DISP_NODE_ID": [n["id"] for n in nodes],
        "OUT_DISP_UX": [d[0] for d in displacements],
        "OUT_DISP_UY": [d[1] for d in displacements],
        "OUT_DISP_RZ": [d[2] for d in displacements],
        "OUT_REAC_NODE_ID": [n["id"] for n in nodes],
        "OUT_REAC_FX": [r[0] for r in reactions],
        "OUT_REAC_FY": [r[1] for r in reactions],
        "OUT_REAC_MZ": [r[2] for r in reactions],
        "OUT_MF_MEMBER_ID": [m["id"] for m in members],
        "OUT_MF_AXIAL": [f[0] for f in member_forces],
        "OUT_MF_SHEAR": [f[1] for f in member_forces],
        "OUT_MF_M_I": [f[2] for f in member_forces],
        "OUT_MF_M_J": [f[3] for f in member_forces],
        "OUT_DES_MEMBER_ID": [m["id"] for m in members],
        "OUT_DES_AS_REQ": [d["as_req"] for d in design_out],
        "OUT_DES_AS_PROV": [d["as_prov"] for d in design_out],
        "OUT_DES_STIRRUP": [d["stirrup_spacing"] for d in design_out],
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="RC Matrix Solver and Design - Excel bridge run")
    parser.add_argument("--workbook", default="rc_matrix_solver.xlsx",
                        help="path to the .xlsx workbook (created as a template if missing)")
    args = parser.parse_args(argv)
    path = Path(args.workbook)

    try:
        if not path.exists():
            print(f"[bridge] template missing - generating {path}")
            build_template(path)
        io = open_workbook(path)
    except RuntimeError as exc:  # openpyxl not installed
        print(f"[bridge] {exc}")
        return 0

    inputs = io.read_inputs()
    solver = _import_or_none("solver")
    design = _import_or_none("design")
    if solver is None or design is None:
        missing = ", ".join(name for name, module in
                            (("solver", solver), ("design", design)) if module is None)
        print(f"[bridge] not ready: {missing} not built yet - no-op end-to-end run complete")
        return 0

    nodes, members, loads, materials = _inputs_to_models(inputs)
    try:
        frame = solver.build_frame(nodes, members, loads)
        solution = solver.solve_frame(frame)
        design_out = design.design_members(materials, members, solution.member_forces)
    except AttributeError as exc:
        print(f"[bridge] solver/design API mismatch: {exc}\n"
              "expected contract in docs/excel-bridge-architecture.md")
        return 2

    outputs = _assemble_outputs(nodes, members, solution, design_out)
    io.write_outputs(outputs)
    print(f"[bridge] solved {len(nodes)} node(s), {len(members)} member(s); "
          f"outputs written to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
