"""End-to-end orchestrator: template -> read inputs -> solver -> design -> write outputs.

Run: ``python3 bridge/run.py [--workbook rc_matrix_solver.xlsx]``

``solver/`` has landed and is consumed directly. ``design/`` is built in
parallel; its import is guarded, so a run without it still writes the analysis
outputs and reports design as pending. The solver/design API contract is pinned
in docs/excel-bridge-architecture.md (section "Solver/design API contract").
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
                                                  Dict[str, Any]]:
    """Plain-data models for design, plus materials. Design contract shapes:
    member dicts are {"id", "i_node", "j_node", "E", "A", "I"} with user ids."""
    members = [
        {"id": mid, "i_node": i_node, "j_node": j_node, "E": e, "A": a, "I": i_inertia}
        for mid, i_node, j_node, e, a, i_inertia in zip(
            inputs["MEMBER_ID"], inputs["MEMBER_I_NODE"], inputs["MEMBER_J_NODE"],
            inputs["MEMBER_E"], inputs["MEMBER_A"], inputs["MEMBER_I"],
        )
    ]
    materials = {
        "fc": inputs["MATERIAL_FC"][0] if inputs["MATERIAL_FC"] else 0.0,
        "fy": inputs["MATERIAL_FY"][0] if inputs["MATERIAL_FY"] else 0.0,
        "es": inputs["MATERIAL_ES"][0] if inputs["MATERIAL_ES"] else 0.0,
    }
    return members, materials


def _build_frame(inputs: InputData, solver: Any) -> Tuple[Any, List[int], List[int]]:
    """Build a solver.Frame from the flat input dict.

    Excel ids (NODE_ID / MEMBER_ID) are user ids; the solver indexes nodes and
    members by list position, so ids map to indices here. Row order is
    preserved, so output rows line up with input rows.
    """
    node_ids = inputs["NODE_ID"]
    node_index = {nid: i for i, nid in enumerate(node_ids)}
    nodes = [solver.Node(x=x, y=y) for x, y in zip(inputs["NODE_X"], inputs["NODE_Y"])]
    supports = {
        node_index[nid]: solver.Support(
            ux=bool(inputs["NODE_SUP_UX"][i]),
            uy=bool(inputs["NODE_SUP_UY"][i]),
            rz=bool(inputs["NODE_SUP_RZ"][i]),
        )
        for i, nid in enumerate(node_ids)
        if inputs["NODE_SUP_UX"][i] or inputs["NODE_SUP_UY"][i] or inputs["NODE_SUP_RZ"][i]
    }
    members = [
        solver.Member(
            node_index[i_node], node_index[j_node],
            solver.Section(E=e, A=a, I=i_inertia),
        )
        for i_node, j_node, e, a, i_inertia in zip(
            inputs["MEMBER_I_NODE"], inputs["MEMBER_J_NODE"],
            inputs["MEMBER_E"], inputs["MEMBER_A"], inputs["MEMBER_I"],
        )
    ]
    member_ids = inputs["MEMBER_ID"]
    member_index = {mid: i for i, mid in enumerate(member_ids)}
    nodal_loads = {
        node_index[nid]: solver.NodalLoad(fx=fx, fy=fy, mz=mz)
        for nid, fx, fy, mz in zip(
            inputs["LOAD_NODE"], inputs["LOAD_N_FX"], inputs["LOAD_N_FY"], inputs["LOAD_N_MZ"])
    }
    member_loads: Dict[int, List[Any]] = {}
    for mid, w in zip(inputs["LOAD_MEMBER"], inputs["LOAD_U_W"]):
        member_loads.setdefault(member_index[mid], []).append(solver.UDL(w=w))
    frame = solver.Frame(
        nodes=nodes, members=members, supports=supports,
        nodal_loads=nodal_loads, member_loads=member_loads,
    )
    return frame, node_ids, member_ids


def _assemble_outputs(node_ids: List[int], member_ids: List[int], solution: Any,
                      design_out: Optional[List[Dict[str, Any]]]) -> OutputData:
    """Flatten solver/design results into the named output dict the writer takes.

    solution.u is a flat (ux, uy, rz per node); reactions and member_forces are
    dicts keyed by index. design_out None -> design sheet left blank.
    """
    n = len(node_ids)
    displacements = [(float(solution.u[3 * i]), float(solution.u[3 * i + 1]),
                      float(solution.u[3 * i + 2])) for i in range(n)]
    reactions = [solution.reactions.get(i, (0.0, 0.0, 0.0)) for i in range(n)]
    forces = [solution.member_forces[i] for i in range(len(member_ids))]
    outputs: OutputData = {
        "OUT_DISP_NODE_ID": node_ids,
        "OUT_DISP_UX": [d[0] for d in displacements],
        "OUT_DISP_UY": [d[1] for d in displacements],
        "OUT_DISP_RZ": [d[2] for d in displacements],
        "OUT_REAC_NODE_ID": node_ids,
        "OUT_REAC_FX": [r[0] for r in reactions],
        "OUT_REAC_FY": [r[1] for r in reactions],
        "OUT_REAC_MZ": [r[2] for r in reactions],
        "OUT_MF_MEMBER_ID": member_ids,
        "OUT_MF_AXIAL": [float(f[0]) for f in forces],
        "OUT_MF_SHEAR": [float(f[1]) for f in forces],
        "OUT_MF_M_I": [float(f[2]) for f in forces],
        "OUT_MF_M_J": [float(f[5]) for f in forces],
    }
    if design_out is not None:
        outputs.update({
            "OUT_DES_MEMBER_ID": member_ids,
            "OUT_DES_AS_REQ": [d["as_req"] for d in design_out],
            "OUT_DES_AS_PROV": [d["as_prov"] for d in design_out],
            "OUT_DES_STIRRUP": [d["stirrup_spacing"] for d in design_out],
        })
    return outputs


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
    if not inputs.get("NODE_ID"):
        print("[bridge] no nodes in workbook - fill the Inputs sheets and re-run")
        return 0
    solver = _import_or_none("solver")
    if solver is None:
        print("[bridge] not ready: solver not built yet - no-op end-to-end run complete")
        return 0
    design = _import_or_none("design")
    if design is None:
        print("[bridge] design not built yet - writing analysis outputs, design skipped")

    members, materials = _inputs_to_models(inputs)
    try:
        frame, node_ids, member_ids = _build_frame(inputs, solver)
    except (AttributeError, TypeError) as exc:
        print(f"[bridge] solver API mismatch: {exc}\n"
              "expected contract in docs/excel-bridge-architecture.md")
        return 2
    try:
        solution = solver.solve(frame)
    except ValueError as exc:
        print(f"[bridge] solve failed: {exc}")
        return 1
    design_out = None
    if design is not None:
        try:
            design_out = design.design_members(materials, members,
                                               _design_forces(solution, member_ids))
        except (AttributeError, TypeError) as exc:
            print(f"[bridge] design API mismatch: {exc}\n"
                  "expected contract in docs/excel-bridge-architecture.md")
            return 2
    outputs = _assemble_outputs(node_ids, member_ids, solution, design_out)
    io.write_outputs(outputs)
    note = "" if design_out is not None else " (design pending)"
    print(f"[bridge] solved {len(node_ids)} node(s), {len(member_ids)} member(s); "
          f"outputs written to {path}{note}")
    return 0


def _design_forces(solution: Any, member_ids: List[int]) -> List[Tuple[float, float, float, float]]:
    """Slice solver 6-vectors [N,V,M_i,N,V,M_j] to the design contract (axial, shear, M_i, M_j)."""
    return [
        (float(solution.member_forces[i][0]), float(solution.member_forces[i][1]),
         float(solution.member_forces[i][2]), float(solution.member_forces[i][5]))
        for i in range(len(member_ids))
    ]


if __name__ == "__main__":
    sys.exit(main())
