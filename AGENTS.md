# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

- Add durable project-specific notes here as they are discovered through real work.

## Solver core (solver/)

- Calculation core: 2D frame Direct Stiffness Method, 3 dof per node (ux, uy, rz).
- API contract: build a `Frame` (nodes, members, sections, supports, loads), call `solve(frame)`, read `Solution.u` (displacements), `.reactions` (dict node -> (rx, ry, mz)), `.member_forces` (local end forces, acting ON the member).
- Units contract (mandatory): forces kN, lengths m, E in kN/m^2 (1 MPa = 1000 kN/m^2), A in m^2, I in m^4, UDL in kN/m. See solver/__init__.py.
- UDL w is positive downward (local -y). Member end forces reported are forces on the member; flip sign for forces on joints.
- Sanity check: `python3 solver/example.py` (propped cantilever, cantilever column, diagonal member), all assertions at 1e-6 relative tolerance.

## Excel bridge (bridge/)

- Frontend is Excel, calculation is Python: run `python3 bridge/run.py [--workbook ...]` (generates a starter template on first run).
- Layout source of truth: `bridge/workbook_layout.py` (sheets, columns, named ranges); full design in `docs/excel-bridge-architecture.md`.
- Engine: openpyxl primary, xlwings documented stub, swappable behind `WorkbookIO` in `bridge/excel_io.py`.
- Design contract (design worker): `design.design_members(materials, members, member_forces) -> [{"as_req", "as_prov", "stirrup_spacing"}]`; `member_forces` are `(axial, shear, m_i, m_j)` sliced from solver 6-vectors in `bridge/run.py`.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
