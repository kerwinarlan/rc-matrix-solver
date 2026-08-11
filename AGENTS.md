# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

- Add durable project-specific notes here as they are discovered through real work.

## Solver core (solver/)

- Calculation core: 2D frame Direct Stiffness Method, 3 dof per node (ux, uy, rz).
- API contract: build a `Frame` (nodes, members, sections, supports, loads), call `solve(frame)`, read `Solution.u` (displacements), `.reactions` (dict node -> (rx, ry, mz)), `.member_forces` (local end forces, acting ON the member).
- Units contract (mandatory): forces kN, lengths m, E in kN/m^2 (1 MPa = 1000 kN/m^2), A in m^2, I in m^4, UDL in kN/m. See solver/__init__.py.
- UDL w is positive downward (local -y). Member end forces reported are forces on the member; flip sign for forces on joints.
- Sanity check: `python3 solver/example.py` (propped cantilever, cantilever column, diagonal member), all assertions at 1e-6 relative tolerance.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
