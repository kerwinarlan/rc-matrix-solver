# RC Matrix Solver

An Excel-driven Reinforced Concrete Matrix Solver and Design tool. Excel is the
frontend for inputs and outputs. Python is the calculation engine: a 2D frame
Direct Stiffness Method (DSM) structural analysis, followed by reinforced
concrete beam design to NSCP 2015 / ACI 318.

```
┌─────────────────────────────────────────────┐
│  Excel workbook (.xlsx)                     │
│  Inputs sheets: nodes, members, loads,      │
│  materials                                  │
└──────────────────────┬──────────────────────┘
                       ▼
┌─────────────────────────────────────────────┐
│  Python bridge (bridge/)                    │
│  reads named ranges, builds the model       │
└──────────────────────┬──────────────────────┘
                       ▼
┌─────────────────────────────────────────────┐
│  solver/ ──────────►  design/               │
│  2D frame DSM          ACI 318 / NSCP 2015  │
│  displacements         beam flexure + shear │
│  reactions             column P-M interact. │
│  member forces         required rebar,      │
│                        stirrups, ties       │
└──────────────────────┬──────────────────────┘
                       ▼
┌─────────────────────────────────────────────┐
│  Excel workbook (.xlsx)                     │
│  Outputs sheets: displacements, reactions,  │
│  member forces, design                      │
└─────────────────────────────────────────────┘
```

---

## Project Overview

The tool solves a 2D frame, then designs its concrete members - a complete
analysis-and-design loop from one Excel file.

- **Excel frontend.** All inputs live in named sheets: `Inputs-Node`
  (coordinates, support restraints), `Inputs-Member` (E, A, I per member),
  `Inputs-Loads` (nodal forces, member UDLs), `Inputs-Materials` (fc', fy, Es).
  Results are written back to `Outputs-Displacements`, `Outputs-Reactions`,
  `Outputs-MemberForces`, and `Outputs-Design`. Cells use Excel named ranges,
  so the Python bridge never depends on fragile cell coordinates.
- **Python backend, structural analysis** (`solver/`). 2D frame Direct
  Stiffness Method, 3 degrees of freedom per node (ux, uy, rz): local
  stiffness and transformation matrices, global stiffness assembly, boundary
  condition application, solve, and member end forces. Units are kN and m.
- **Python backend, RC design** (`design/`). Beam flexure design for singly
  and doubly reinforced sections, shear design with stirrups, column design
  for axial load + uniaxial moment (P-M strain-compatibility interaction
  with the tension/compression-controlled phi transition), and the ACI 318
  strength-reduction framework, aligned with NSCP 2015 (an SI code family
  where section numbers differ; equivalences are noted in the source). Units
  are mm, MPa, kN.
- **Excel bridge** (`bridge/`). A swappable read/write layer. openpyxl is the
  primary engine for headless batch runs. xlwings is the optional interactive
  engine for live Excel sessions. The workbook layout and named-range scheme
  are defined once in `bridge/workbook_layout.py`, the single source of truth.

### Repository layout

```
rc-matrix-solver/
├── solver/          2D frame Direct Stiffness Method core
├── design/          RC member design (beam + column) per ACI 318 / NSCP 2015
├── bridge/          Excel read/write layer, layout, end-to-end runner
├── docs/            excel-bridge-architecture.md (design contract)
├── examples/        demo workbook + build script + walkthrough
├── requirements.txt runtime dependencies
└── AGENTS.md        project memory for agentic development
```

---

## Setup & Usage

### 1. Install dependencies

```bash
python3 -m pip install -r requirements.txt
```

`requirements.txt` declares the runtime dependencies: `numpy` (matrix
operations in the solver) and `openpyxl` (headless .xlsx read/write).

For **interactive Excel use** (xlwings engine - optional), also install:

```bash
python3 -m pip install xlwings
```

xlwings requires Microsoft Excel to be installed. Without it the tool still
runs headlessly through openpyxl.

### 2. Run the demo

The repo ships a pre-filled demo workbook: a hand-checkable propped L-frame.

```bash
python3 bridge/run.py --workbook examples/rc_matrix_solver_demo.xlsx
```

The run reads the Inputs sheets, solves the frame, designs the members, and
rewrites the Outputs sheets. It prints a one-line summary. Walkthrough and
sheet mapping: `examples/README.md`.

### 3. Run your own model

```bash
python3 bridge/run.py            # generates rc_matrix_solver.xlsx template
```

Fill the `Inputs-*` sheets (nodes, members, loads, materials), then re-run:

```bash
python3 bridge/run.py
```

### 4. Regenerate the demo workbook

```bash
python3 examples/build_demo.py
```

Rebuilds the template, writes the sample frame inputs, runs the pipeline, and
writes the outputs - the full loop in one command.

### 5. Run the module sanity checks

```bash
python3 solver/example.py          # 3 hand-solvable frame cases
python3 -m design.sanity_check     # ACI/NSCP worked-example beam and column
```

---

## Units and code provisions

- Structural analysis: kN, m, kN/m^2 for E, kN/m for UDL, kN*m for moments.
- RC design: mm, MPa, kN; SI rebar diameters (10-36 mm).
- Design provisions follow ACI 318 with NSCP 2015 equivalences documented in
  `design/` docstrings: tension/compression-controlled strain limits,
  rho_min/rho_max, phi = 0.9 flexure / 0.75 shear / 0.65 compression
  (columns), stirrup and tie spacing limits.

---

## The Agentic Workflow

This project is not only a structural tool - it is also a demonstration of a
multi-agent software build. The entire repository was developed by an
orchestrated team of AI agents, with no hand-written code from a human
developer.

### Orchestration

The build was orchestrated by **firstmate**, the captain's AI fleet
coordinator. Every task, from the first commit to the final integration, was
dispatched to workers running on the **Pi agent with the `deepseek-v4-flash`
model at `xhigh` thinking** - a standing dispatch rule configured before any
code was written.

The workflow:

1. **Project intake.** A local repository was created with a placeholder
   README and an initial commit.
2. **Module decomposition.** The chief-engineer layer broke the tool into
   three non-overlapping modules and defined the public API contract between
   them.
3. **Parallel dispatch.** Three sub-agents were launched simultaneously, each
   in its own isolated tab, each working from an identical starting point on
   its own branch. They never edited the same file.
4. **Sequential landing.** Each finished branch was verified as a clean
   fast-forward and merged into `main` in dependency-safe order.
5. **Integration proof.** A final agent ran the whole pipeline end to end and
   committed the demo workbook and quickstart.

### The three sub-agents

| Agent | Track | Deliverable | Verification |
|-------|-------|-------------|--------------|
| **Solver** | 2D frame Direct Stiffness Method | `solver/` package: model, stiffness, assembly, solve, member forces | 3 hand-solvable frame cases, asserted at 1e-6 tolerance |
| **Designer** | RC beam design | `design/` package: flexure (singly/doubly reinforced), shear, ACI 318 provisions | Worked-example sanity check with tolerance |
| **Interface** | Python-Excel bridge | `bridge/` package + `docs/excel-bridge-architecture.md` | End-to-end runner, layout as code |

The Interface agent documented the assumed solver and design APIs as a
contract for the parallel workers. When the Solver landed, the Interface agent
was steered to rebase and reconcile its code against the actual solver API.
The Designer agent did the same, merging its project-memory notes with the
Solver's so the repository keeps one shared `AGENTS.md`.

### Execution log (summary)

```
1. Project created: local repo, placeholder README, initial commit.
2. Dispatch rule set: Pi agent, deepseek-v4-flash, xhigh thinking.
3. Solver, Designer, Interface dispatched in parallel tabs.
   - Solver: solver/ package, 3 verified frame cases.
   - Designer: design/ package, ACI 318 / NSCP 2015 flexure + shear.
   - Interface: bridge/ package + architecture doc.
4. Branches landed sequentially as clean fast-forwards.
   - Solver landed first (core API).
   - Interface rebased onto the landed solver, reconciled its API contract.
   - Designer rebased, merged project memory (AGENTS.md) with the solver's.
5. Integration agent proved the end-to-end pipeline.
   - Demo L-frame: reactions balance applied loads (Fx 30 kN, Fy 120 kN,
     moment 510 kN*m about the base).
   - Beam governed by rho_min: as_req = 440 mm^2 (300x500, d = 440).
   - Column: as_req ~ 912 mm^2, stirrups from shear.
   - requirements.txt, quickstart, build_demo.py committed.
```

Every branch was reviewed before landing, every worker was cleaned up after
its task, and the queue was kept current throughout. The result is a fully
functional repository whose history records the whole agentic process.

---

## Status

Local repository, complete analysis-and-design scaffold with a proven
end-to-end run covering beam flexure, beam shear, and column axial-load
interaction. Natural next steps: member end releases, T-beam geometry,
biaxial column bending, slenderness/P-delta amplification, spiral columns,
and a live xlwings workbook with Excel formulas.
