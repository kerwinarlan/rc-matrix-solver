"""rc-matrix-solver: 2D frame Direct Stiffness Method core.

Workflow: build a Frame (nodes, members, sections, supports, loads), call
solve(frame), and read Solution.u (nodal displacements), Solution.reactions
(support reactions), and Solution.member_forces (local end forces per member).

Units contract: kN and m; E in kN/m^2 (1 MPa = 1000 kN/m^2), A in m^2,
I in m^4, UDL intensity in kN/m. Requires numpy.
"""
from .assembly import assemble_global_stiffness
from .member_forces import fixed_end_forces, member_end_forces
from .model import Frame, Member, NodalLoad, Node, Section, Support, UDL
from .solve import Solution, solve
from .stiffness import k_global, k_local, transformation

__all__ = [
    "Node",
    "Section",
    "Member",
    "Support",
    "NodalLoad",
    "UDL",
    "Frame",
    "k_local",
    "transformation",
    "k_global",
    "assemble_global_stiffness",
    "solve",
    "Solution",
    "member_end_forces",
    "fixed_end_forces",
]
