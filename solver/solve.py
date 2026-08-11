"""Apply boundary conditions and solve K u = f.

Boundary conditions use the reduced-system method: restrained dofs are
removed, the reduced system is solved, and reactions come from
r = K u - f. This is exact (no penalty parameter to tune) and is the
textbook standard. The penalty method is the drop-in alternative if a
reduced system ever becomes inconvenient.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .assembly import assemble_global_stiffness, restrained_dofs
from .member_forces import fixed_end_forces, member_end_forces
from .model import Frame, NodalLoad, UDL
from .stiffness import element_geometry, transformation


def load_vector(frame: Frame) -> np.ndarray:
    """Assemble the global load vector f.

    Nodal loads land directly on their dofs. Member loads contribute the
    equivalent nodal loads f_eq = -T^T f_fe (negative of the fixed-end forces).
    """
    n = len(frame.nodes)
    f = np.zeros(3 * n)
    for nidx, load in frame.nodal_loads.items():
        node = frame.nodes[nidx]
        f[node.ux] += load.fx
        f[node.uy] += load.fy
        f[node.rz] += load.mz
    for midx, loads in frame.member_loads.items():
        m = frame.members[midx]
        i, j = frame.nodes[m.i], frame.nodes[m.j]
        length, c, s = element_geometry(i, j)
        t = transformation(c, s)
        ffe = fixed_end_forces(m, loads, length)
        f[[i.ux, i.uy, i.rz, j.ux, j.uy, j.rz]] -= t.T @ ffe
    return f


@dataclass
class Solution:
    """Result of a frame analysis.

    u: full nodal displacement vector (ux, uy, rz per node, in node order);
       restrained dofs are zero.
    reactions: node index -> (rx, ry, mz) for every node with a Support.
    member_forces: member index -> local end forces [N_i, V_i, M_i, N_j, V_j, M_j]
       acting on the member (see member_forces.member_end_forces).
    """

    u: np.ndarray
    reactions: dict[int, tuple[float, float, float]]
    member_forces: dict[int, np.ndarray]


def solve(frame: Frame) -> Solution:
    """Analyze the frame: displacements, reactions, and member end forces."""
    if any(not (0 <= m.i < len(frame.nodes) and 0 <= m.j < len(frame.nodes)) for m in frame.members):
        raise ValueError("member references a node index outside the node list")
    k = assemble_global_stiffness(frame)
    f = load_vector(frame)
    restrained = restrained_dofs(frame)
    free = np.setdiff1d(np.arange(k.shape[0]), restrained)
    if free.size == 0:
        raise ValueError("no free dofs: nothing to solve")
    try:
        uf = np.linalg.solve(k[np.ix_(free, free)], f[free])
    except np.linalg.LinAlgError as exc:
        raise ValueError("singular stiffness matrix: check supports (mechanism)") from exc
    u = np.zeros(k.shape[0])
    u[free] = uf
    r = k @ u - f
    reactions = {}
    for nidx in sorted(frame.supports):
        node = frame.nodes[nidx]
        reactions[nidx] = (r[node.ux], r[node.uy], r[node.rz])
    return Solution(u=u, reactions=reactions, member_forces=member_end_forces(frame, u))
