# Excel Bridge Architecture

RC Matrix Solver and Design - Python-Excel bridge design and workbook layout.

Status: living document. The layout data in `bridge/workbook_layout.py` is the
single source of truth; this doc mirrors it. Change the data first, then this
doc.

## 1. Purpose

Excel is the frontend UI: the engineer types inputs into sheets and reads
results from sheets. Python does the heavy calculation: `solver/` (DSM frame
analysis) and `design/` (RC member checks), both built in parallel by other
workers. The `bridge/` package is the seam between the two.

```
+---------------------+        +------------------+        +-----------------+
|  Excel workbook     | <----> |  bridge/         | <----> |  solver/        |
|  (frontend UI)      |  xlsx  |  excel_io        |  API   |  design/        |
|  inputs + outputs   |        |  workbook_layout |        |  (heavy calc)   |
+---------------------+        +------------------+        +-----------------+
```

`bridge/` owns: the workbook layout (sheets, columns, named ranges), a thin
read/write layer with a swappable engine, template generation, and the
end-to-end orchestrator. It never owns engineering logic.

## 2. Engine choice: xlwings vs openpyxl

| Aspect | openpyxl | xlwings |
|---|---|---|
| Mode | Reads/writes `.xlsx` files headlessly | Drives a live Excel application |
| Excel install required | No | Yes (Windows/macOS with Office) |
| Excel formulas | Read as values or formula strings; never recalculates | Live; recalculation happens in Excel |
| Two-way sync while Excel is open | No (file-level only) | Yes, but a stale file/live-app clash is possible |
| User triggers | Any script, CI, cron, CLI | Button/macro in the workbook, or a UDF |
| Distribution | pip package only, runs anywhere | Needs Excel on the machine |
| Testing | Full automated round-trip in CI | Requires a desktop with Excel |
| License | MIT | Apache 2.0 (open source) |

**Recommendation: openpyxl is primary, xlwings is the fallback.**

Rationale:

- The default execution path is headless batch: fill the template, run
  `python3 bridge/run.py`, read the outputs. No Excel needed on the compute
  machine, fully scriptable and testable.
- Python owns the numbers. The workbook is a data container, not a formula
  engine. Recalculation is not part of the solve path, so openpyxl's lack of
  formula evaluation is not a limitation.
- openpyxl keeps CI meaningful: the bridge round-trip runs on any machine.

When to reach for xlwings (the fallback): an engineer wants to press a button
inside the workbook, have the current sheet state solved in place, and see
results update live without leaving Excel. That mode is designed for but not
implemented (see section 6 and the `XlwingsWorkbookIO` stub).

Both engines implement the same `WorkbookIO` interface (section 7), so the
swap is one argument to `open_workbook()`, and `run.py` never changes.

## 3. Repository layout

```
bridge/
  __init__.py          Public API re-exports
  workbook_layout.py   Sheet/named-range layout as pure data (source of truth)
  excel_io.py          WorkbookIO interface, openpyxl engine, xlwings stub,
                       build_template(), self-check
  run.py               End-to-end orchestrator (guarded solver/design imports)
docs/
  excel-bridge-architecture.md   This document
```

## 4. Workbook sheet layout

One header row per table; data starts on the next row. Inputs-Loads hosts two
tables stacked vertically (nodal loads at rows 1+, member UDLs at rows 6+).
Readers stop at the first blank row in the table band, so a user can add rows
freely; counts are Excel-side metadata only (section 5).

Units: SI-based but with forces in kN, moments in kN*m, stresses in kN/m^2
(1 MPa = 1000 kN/m^2) - the solver's unit contract; values pass through the
bridge unmodified. Restraint columns take 1 = fixed, 0 = free.

### Inputs-Node  (count: NODE_COUNT)

| Col | Header | Named range | Kind | Notes |
|---|---|---|---|---|
| A | Node ID | NODE_ID | id | Unique per row |
| B | X (m) | NODE_X | number | |
| C | Y (m) | NODE_Y | number | |
| D | Restraint UX (1=fixed) | NODE_SUP_UX | number | 1 = fixed, 0 = free |
| E | Restraint UY (1=fixed) | NODE_SUP_UY | number | |
| F | Restraint RZ (1=fixed) | NODE_SUP_RZ | number | |

### Inputs-Member  (count: MEMBER_COUNT)

| Col | Header | Named range | Kind |
|---|---|---|---|
| A | Member ID | MEMBER_ID | id |
| B | I-Node ID | MEMBER_I_NODE | id |
| C | J-Node ID | MEMBER_J_NODE | id |
| D | E (kN/m^2) | MEMBER_E | number |
| E | A (m^2) | MEMBER_A | number |
| F | I (m^4) | MEMBER_I | number |

`MEMBER_I` is the second moment of area, not the I-node. The id columns are
`MEMBER_I_NODE` / `MEMBER_J_NODE`, so there is no collision.

### Inputs-Loads  (two tables)

Nodal loads (count: LOAD_N_COUNT), header row 1:

| Col | Header | Named range | Kind |
|---|---|---|---|
| A | Node ID | LOAD_NODE | id |
| B | Fx (kN) | LOAD_N_FX | number |
| C | Fy (kN) | LOAD_N_FY | number |
| D | Mz (kN*m) | LOAD_N_MZ | number |

Member UDLs (count: LOAD_U_COUNT), header row 6, data row 7:

| Col | Header | Named range | Kind |
|---|---|---|---|
| A | Member ID | LOAD_MEMBER | id |
| B | w (kN/m, downward +) | LOAD_U_W | number |

Row 5 is intentionally blank to separate the two tables. The solver implements
only full-span transverse UDLs (w positive downward), so there is a single
intensity column; extend the layout here if axial/partial loads are added.

### Inputs-Materials  (count: MATERIAL_COUNT, usually 1 row)

| Col | Header | Named range | Kind |
|---|---|---|---|
| A | fc' (kN/m^2) | MATERIAL_FC | number |
| B | fy (kN/m^2) | MATERIAL_FY | number |
| C | Es (kN/m^2) | MATERIAL_ES | number |

### Outputs-Displacements

| Col | Header | Named range | Kind |
|---|---|---|---|
| A | Node ID | OUT_DISP_NODE_ID | id |
| B | ux (m) | OUT_DISP_UX | number |
| C | uy (m) | OUT_DISP_UY | number |
| D | rz (rad) | OUT_DISP_RZ | number |

### Outputs-Reactions

| Col | Header | Named range | Kind |
|---|---|---|---|
| A | Node ID | OUT_REAC_NODE_ID | id |
| B | Fx (kN) | OUT_REAC_FX | number |
| C | Fy (kN) | OUT_REAC_FY | number |
| D | Mz (kN*m) | OUT_REAC_MZ | number |

### Outputs-MemberForces

| Col | Header | Named range | Kind |
|---|---|---|---|
| A | Member ID | OUT_MF_MEMBER_ID | id |
| B | Axial (kN) | OUT_MF_AXIAL | number |
| C | Shear (kN) | OUT_MF_SHEAR | number |
| D | Moment i-end (kN*m) | OUT_MF_M_I | number |
| E | Moment j-end (kN*m) | OUT_MF_M_J | number |

### Outputs-Design

| Col | Header | Named range | Kind |
|---|---|---|---|
| A | Member ID | OUT_DES_MEMBER_ID | id |
| B | As required (mm^2) | OUT_DES_AS_REQ | number |
| C | As provided (mm^2) | OUT_DES_AS_PROV | number |
| D | Stirrup spacing (mm) | OUT_DES_STIRRUP | number |

Row ordering rule: output row i always corresponds to input row i of the same
group (nodes in input order, members in input order). The id columns are there
for human verification in Excel, not for matching.

## 5. Named ranges convention

Python reads and writes by name, never by cell coordinates. The naming scheme:

- Inputs: `<GROUP>_<QUANTITY>` - `NODE_X`, `MEMBER_E`, `LOAD_N_FX`, `MATERIAL_FC`.
- Outputs: `OUT_<GROUP>_<QUANTITY>` - `OUT_DISP_UX`, `OUT_MF_AXIAL`, `OUT_DES_AS_REQ`.
- Row keys: `<GROUP>_ID` for node/member ids; output row ids are
  `OUT_<GROUP>_<ID>` (e.g. `OUT_DES_MEMBER_ID`).
- Counts: `<GROUP>_COUNT` - `NODE_COUNT`, `LOAD_U_COUNT`. Plain number in
  `count_cell` (I1 / I6), label one cell to its left. The user maintains the
  value for Excel-side formulas (XLOOKUP ranges, checks). The Python reader
  ignores counts and scans to the first blank row, so a stale count never loses
  data. The writer never touches counts.
- All column names are globally unique across the workbook (required because
  named ranges live at workbook scope); hence `OUT_MF_MEMBER_ID` vs
  `OUT_DES_MEMBER_ID`, never a shared `OUT_MEMBER_ID`.

Range spans: every named range covers `data_row .. 1000` statically, so any
cell written in the data band is in range. Blank cells are not saved to disk.
New rows beyond row 1000 require widening the range in `build_template` (and
`MAX_ROWS` in `workbook_layout.py`).

## 6. Execution flow

### Headless batch (primary)

```
python3 bridge/run.py [--workbook rc_matrix_solver.xlsx]
```

1. If the workbook does not exist, generate the starter template
   (`build_template` from `workbook_layout.py`).
2. `read_inputs()` - scan the four input tables to a flat dict keyed by
   named range, e.g. `{"NODE_X": [0.0, 5.0], ...}`.
3. Build the frame from the input dicts (`_build_frame`: user ids map to
   solver node/member indices) and call `solver.solve(frame)`.
4. If `design/` has landed, call `design.design_members(materials, members,
   member_forces)`; otherwise skip it and report design as pending.
5. `write_outputs({...})` - flatten results into named output dicts; the
   writer clears the output band first so a shorter run never leaves stale
   numbers.

If `solver/` is missing, the run prints "not ready" and completes as a no-op;
if only `design/` is missing, the analysis outputs are still written. This is
why `python3 bridge/run.py` never crashes while the parallel workers land.

The solve runs as a batch script: open the workbook, solve, save, close. The
user then opens/reloads the workbook to see outputs. This is the openpyxl path.

### Interactive Excel (fallback, xlwings)

Designed but not implemented (`XlwingsWorkbookIO` is a documented stub):

- A button on a control sheet runs an xlwings macro (`RunPython`) that loads
  the active workbook, calls the same solver/design functions, and writes
  results back through the same named ranges; Excel recalcs and the user sees
  live results without leaving the app.
- Optional xlwings UDF for on-demand single-cell queries (e.g. an
  `@xw.func` returning member design ratios).

The button/UDF layer is out of scope for now. When it lands, it reuses
`WorkbookIO` and `workbook_layout.py` unchanged; only the file/session handling
differs (live `xlwings.Book` vs `openpyxl.load_workbook`).

### Where the trigger lives

| Path | Trigger | Engine |
|---|---|---|
| CLI / CI / cron | shell: `python3 bridge/run.py` | openpyxl (implemented) |
| Inside Excel | button/macro or UDF | xlwings (stub) |

## 7. WorkbookIO interface

`bridge/excel_io.py` defines the engine-neutral contract. `run.py` depends only
on this.

```python
class WorkbookIO(Protocol):
    def read_inputs(self) -> InputData: ...      # {"NODE_X": [0.0, 5.0], ...}
    def write_outputs(self, outputs: OutputData) -> None: ...
```

- `open_workbook(path, engine="openpyxl")` - factory; `engine="xlwings"`
  raises NotImplementedError with a pointer to this doc.
- `OpenpyxlWorkbookIO` - implemented. Reads values with `data_only=True`,
  coerces `id` columns to int and `number` columns to float.
- `XlwingsWorkbookIO` - stub raising NotImplementedError; constructor
  documents the intended design (live `xlwings.Book`, same named ranges).
- `build_template(path)` - writes the starter workbook: headers (bold),
  freeze panes at the header row, count cells, and all named ranges.
- Self-check: `python3 -m bridge.excel_io` builds a template and asserts a
  full read/write round-trip.

## 8. Solver/design API contract

### solver (module `solver`, in `solver/`) - landed, consumed directly

```python
frame = solver.Frame(
    nodes=[solver.Node(x, y), ...],                       # x, y in m
    members=[solver.Member(i, j, solver.Section(E, A, I)), ...],  # indices, not ids
    supports={node_index: solver.Support(ux=True, uy=True, rz=True), ...},
    nodal_loads={node_index: solver.NodalLoad(fx, fy, mz), ...},    # kN, kN*m
    member_loads={member_index: [solver.UDL(w=w)], ...},            # kN/m, downward +
)
solution = solver.solve(frame)
```

Units: kN, m, kN/m^2 (1 MPa = 1000 kN/m^2). Node and member ids in the
workbook are user ids; the bridge maps them to list indices when building the
frame (`_build_frame` in `run.py`).

- `solution.u`: flat numpy array, (ux, uy, rz) per node in node order;
  restrained dofs are zero.
- `solution.reactions`: `{node_index: (rx, ry, mz)}`, supported nodes only.
- `solution.member_forces`: `{member_index: [N_i, V_i, M_i, N_j, V_j, M_j]}`,
  local end forces on the member.

### design (module `design`, in `design/`) - contract to match

```python
def design_members(materials: dict, members: list[dict],
                   member_forces: list[tuple]) -> list[dict]
```

- `materials`: `{"fc": float, "fy": float, "es": float}` (kN/m^2).
- `members`: `[{"id": int, "i_node": int, "j_node": int,
  "E": float, "A": float, "I": float}, ...]` (user ids).
- `member_forces`: per member, input order, `(axial, shear, m_i, m_j)` sliced
  from the solver's 6-vector by `_design_forces` in `run.py`.
- Returns one dict per member, input order:
  `{"as_req": float, "as_prov": float, "stirrup_spacing": float}`
  (mm^2, mm^2, mm).

## 9. Open items and reconciliation notes

- Count cells are user-maintained and ignored by the reader by design. If a
  future engine (xlwings) wants live counts, write them back after solving.
- Output row ordering is positional (row i in = row i out). If solver/design
  ever reorder or filter rows, the id columns become the join key; update
  `_assemble_outputs` accordingly.
- `run.py` treats `AttributeError`/`TypeError` from the solver/design calls as
  API mismatches (exit 2) and `ValueError` from the solve as a model error
  (exit 1). Revisit once `design/` lands and the contracts stabilize.
- Excel-side polish (number formats, conditional formatting for
  over-utilization) is deferred; `build_template` keeps headers and freeze
  panes only.
