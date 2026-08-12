# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

- Add durable project-specific notes here as they are discovered through real work.

## Solver core (solver/)

- Calculation core: 2D frame Direct Stiffness Method, 3 dof per node (ux, uy, rz).
- API contract: build a `Frame` (nodes, members, sections, supports, loads), call `solve(frame)`, read `Solution.u` (displacements), `.reactions` (dict node -> (rx, ry, mz)), `.member_forces` (local end forces, acting ON the member).
- Units contract (mandatory): forces kN, lengths m, E in kN/m^2 (1 MPa = 1000 kN/m^2), A in m^2, I in m^4, UDL in kN/m. See solver/__init__.py.
- UDL w is positive downward (local -y). Member end forces reported are forces on the member; flip sign for forces on joints.
- Sanity check: `python3 solver/example.py` (propped cantilever, cantilever column, diagonal member), all assertions at 1e-6 relative tolerance.

## GUIs (gui/)

- `frame_gui.py`: FreeSimpleGUI desktop frontend for the demo propped L-frame; `solve_lframe()` is the single source of truth for that frame model and returns reactions, member forces, node coords, raw displacements, w, fx.
- `web_app.py`: browser frontend (stdlib http.server only, embedded HTML/SVG/JS) reusing `solve_lframe`; two tabs - demo L-frame inputs and a generic JSON model (`solve_model`: any nodes/members/supports/loads, returns a JSON-safe result with a global equilibrium check; UDL total force = w*(dy,-dx)); `--check` runs both paths through the real HTTP handler headlessly.

## Excel bridge (bridge/)

- Frontend is Excel, calculation is Python: run `python3 bridge/run.py [--workbook ...]` (generates a starter template on first run).
- End-to-end demo: `python3 bridge/run.py --workbook examples/rc_matrix_solver_demo.xlsx` (committed pre-filled workbook; regenerate with `python3 examples/build_demo.py`). Quickstart in `examples/README.md` and the main README.
- Layout source of truth: `bridge/workbook_layout.py` (sheets, columns, named ranges); full design in `docs/excel-bridge-architecture.md`.
- Engine: openpyxl primary, xlwings documented stub, swappable behind `WorkbookIO` in `bridge/excel_io.py`.
- Design contract (design worker): `design.design_members(materials, members, member_forces) -> [{"as_req", "as_prov", "stirrup_spacing"}]`; `member_forces` are `(axial, shear, m_i, m_j)` sliced from solver 6-vectors in `bridge/run.py`.

## Design package conventions (design/)

- All units are SI: MPa, mm, N (kN*m, kN for Mu/Vu inputs).
- Codes: ACI 318-19 provisions are cited per function; NSCP 2015 is ACI 318-08/11 lineage, so its section numbers differ (equivalences noted in comments).
- `design_beam(Mu_kNm, Vu_kN, b, d, d_prime, fc, fy, ...)` is the plain-value entry point; the solver/bridge never passes objects into design.
- `design_members(materials, members, member_forces)` is the bridge adapter matching the pinned contract in docs/excel-bridge-architecture.md sec. 8: materials arrive in kN/m^2 (divide by 1000 to get MPa), and the section is derived from the member's A/I as the equivalent rectangle (h = sqrt(12I/A), b = A/h) with default cover 60 mm. Member dicts may carry node coordinates (i_x/i_y/j_x/j_y, added by bridge/run.py): near-vertical members (|dy| >= |dx|) are then designed as columns via `design.column`, everything else as beams; without coordinates every member is a beam (backward compatible).
- Column design (`design/column.py`): tied rectangular columns, symmetric steel on two faces (Ast/2 at d' from each face; side bars count toward Ast only), P-M interaction by strain compatibility per ACI 318-19 22.2.2.1/Table 21.2.2 (phi 0.90 tension-controlled / 0.65 compression-controlled with linear transition). Design check: Pu <= phi*Pn,max = 0.80 phi Po (22.4.2.2, tied) and Mu <= phi*Mn(Pu) by interpolation on the phi-reduced curve; smallest bar config (even count >= 4, 1%..8% Ag) that passes wins. The phi-reduced curve is single-valued in phi*Pn but phi*Mn is NOT monotone (bump near the balanced point) - bracket by phi*Pn. Explicitly out of scope: biaxial bending, slenderness/P-delta, spirals, tension members. Solver axial at member i-end is compression positive, which is the Pu sign `design_column` expects.
- Rebar table is SI diameters (10-36 mm) in `design/flexure.py:BAR_DIAMETERS_MM`.
- Python 3.9: no `X | None` annotations without `from __future__ import annotations`; builtin generics (`tuple[...]`) are fine.
- Sanity check: `python3 -m design.sanity_check` from the repo root.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.

## Third-party submodules (third_party/)

- `third_party/` holds git submodules forked from Engr. Jaydee Lucero's talk repos (PythonAsia 2026): `truss_analyzer` (2D truss FEM, numpy/matplotlib, no license stated) and `midasgennx_2d_truss_example` (MIDAS Gen NX 2026 API, MIT). Provenance and license notes: `third_party/README.md`. Neither is imported by solver/design/bridge; fetch with `git submodule update --init`.
