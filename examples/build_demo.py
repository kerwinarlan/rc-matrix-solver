"""Build examples/rc_matrix_solver_demo.xlsx: template + sample inputs, then
run the full pipeline (read -> solve -> design -> write outputs) on it.

Run from the repo root:
    python3 examples/build_demo.py

The workbook is committed, so this script is only needed to regenerate it.
All cell positions come from bridge/workbook_layout.py (the layout source of
truth); no hand-edited XML. Inputs are a 2-member propped L-frame:

    N1 (0,0) fixed - column 400x400 up to N2 (0,5) - beam 300x500 to N3 (6,5)
    roller. Loads: UDL 20 kN/m down on the beam, 30 kN lateral push at N2.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge import build_template  # noqa: E402
from bridge.workbook_layout import TABLES  # noqa: E402

import openpyxl  # noqa: E402

DEMO = Path(__file__).resolve().parent / "rc_matrix_solver_demo.xlsx"

# Inputs keyed by column name; rows share position across columns of a table.
INPUTS: Dict[str, List[Any]] = {
    # Nodes: id, x, y, ux, uy, rz
    "NODE_ID": [1, 2, 3],
    "NODE_X": [0.0, 0.0, 6.0],
    "NODE_Y": [0.0, 5.0, 5.0],
    "NODE_SUP_UX": [1, 0, 0],
    "NODE_SUP_UY": [1, 0, 1],
    "NODE_SUP_RZ": [1, 0, 0],
    # Members: id, i-node, j-node, E (kN/m^2), A (m^2), I (m^4)
    "MEMBER_ID": [1, 2],
    "MEMBER_I_NODE": [1, 2],
    "MEMBER_J_NODE": [2, 3],
    "MEMBER_E": [25e6, 25e6],          # fc'=28 MPa concrete, Ec ~ 25 GPa
    "MEMBER_A": [0.16, 0.15],          # 400x400 column, 300x500 beam
    "MEMBER_I": [0.002133, 0.003125],
    # Nodal loads: node, fx, fy, mz
    "LOAD_NODE": [2],
    "LOAD_N_FX": [30.0],
    "LOAD_N_FY": [0.0],
    "LOAD_N_MZ": [0.0],
    # Member UDLs: member, w (kN/m, downward +)
    "LOAD_MEMBER": [2],
    "LOAD_U_W": [20.0],
    # Materials: fc' (kN/m^2), fy, Es
    "MATERIAL_FC": [28000.0],
    "MATERIAL_FY": [420000.0],
    "MATERIAL_ES": [2e8],
}


def write_inputs(path: Path) -> None:
    """Fill the template's input tables from INPUTS via the layout tables."""
    wb = openpyxl.load_workbook(path)
    for table in TABLES:
        if table.direction != "in":
            continue
        cols = [(i, c) for i, c in enumerate(table.columns) if c.name in INPUTS]
        count = max(len(INPUTS[c.name]) for _, c in cols)
        for index, column in cols:
            for offset, value in enumerate(INPUTS[column.name]):
                wb[table.sheet].cell(table.data_row + offset, table.start_col + index, value)
        if table.count_name:
            wb[table.sheet][table.count_cell] = count
    wb.save(path)


def main() -> int:
    print(f"[demo] generating {DEMO}")
    build_template(DEMO)
    write_inputs(DEMO)

    from bridge.run import main as run_main
    return run_main(["--workbook", str(DEMO)])


if __name__ == "__main__":
    sys.exit(main())
