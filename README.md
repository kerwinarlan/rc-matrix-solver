# RC Matrix Solver

2D frame Direct Stiffness Method solver (`solver/`, kN/m units) + ACI 318 /
NSCP 2015 RC beam design (`design/`, SI mm/MPa) + Excel bridge (`bridge/`,
openpyxl).

Excel bridge design: `docs/excel-bridge-architecture.md`.

## Quickstart

```bash
python3 -m pip install -r requirements.txt
python3 bridge/run.py --workbook examples/rc_matrix_solver_demo.xlsx
```

The demo workbook ships pre-filled with a small propped L-frame; the run
reads its Inputs sheets, solves, designs, and rewrites the Outputs sheets.
Walkthrough and sheet mapping: `examples/README.md`.

Start your own model from a blank template:

```bash
python3 bridge/run.py            # generates rc_matrix_solver.xlsx
# fill the Inputs-* sheets (nodes, members, loads, materials), then re-run
python3 bridge/run.py
```
