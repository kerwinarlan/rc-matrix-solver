# Demo workbook: rc_matrix_solver_demo.xlsx

A committed, pre-filled workbook for the end-to-end pipeline: read inputs ->
solve (2D frame DSM) -> design (ACI 318 / NSCP 2015 beam + column) -> write
outputs.

## Quickstart

```bash
python3 -m pip install -r requirements.txt
python3 bridge/run.py --workbook examples/rc_matrix_solver_demo.xlsx
```

The run prints a one-line summary and rewrites the Outputs sheets. Regenerate
the workbook from scratch (template + sample inputs + fresh run):

```bash
python3 examples/build_demo.py
```

## The demo frame

A 2-member propped L-frame, 3 nodes, hand-checkable:

| Node | X (m) | Y (m) | Support |
|------|-------|-------|---------|
| 1    | 0     | 0     | fixed (ux, uy, rz) |
| 2    | 0     | 5     | free |
| 3    | 6     | 5     | roller (uy) |

| Member | From | To | Section | E (kN/m^2) |
|--------|------|----|---------|------------|
| 1      | 1    | 2   | column 400x400 (A=0.16 m^2, I=0.002133 m^4) | 25e6 |
| 2      | 2    | 3   | beam 300x500 (A=0.15 m^2, I=0.003125 m^4) | 25e6 |

Loads: UDL 20 kN/m downward on member 2; 30 kN lateral (+x) at node 2.
Materials: fc' = 28 MPa, fy = 420 MPa, Es = 200 GPa.

Sanity targets after a run:

- Reaction sum = applied loads: Fy total 120 kN, Fx total 30 kN.
- Moment balance about node 1: 510 kN*m.
- Beam 2 is governed by rho_min: as_req = 440 mm^2 (300x500, d = 440).
- Column 1 (near-vertical) is designed per P-M interaction: 4-25 mm bars
  (Ast = 1963 mm^2), 10 mm ties at 390 mm; utilization ~0.85.

## Sheet mapping

Inputs sheets (fill these to run your own model): Inputs-Node (geometry +
supports), Inputs-Member (E, A, I), Inputs-Loads (nodal loads and member
UDLs), Inputs-Materials (fc', fy, Es). Inputs cells are also Excel named
ranges (NODE_X, MEMBER_I, ...) - see `bridge/workbook_layout.py`, the layout
source of truth, and `docs/excel-bridge-architecture.md`.

Outputs sheets (rewritten on every run): Outputs-Displacements (ux, uy, rz
per node), Outputs-Reactions, Outputs-MemberForces (local end forces: axial,
shear, i-end/j-end moment), Outputs-Design (design type, as_req, as_prov,
stirrup/tie spacing, Pu, phi*Pn, phi*Mn, utilization).

Units: forces kN, lengths m, E kN/m^2, moments kN*m - the solver contract.
