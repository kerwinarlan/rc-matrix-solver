"""Global stiffness matrix assembly, 3 dof per node (ux, uy, rz).

Node n owns global dofs 3n (ux), 3n+1 (uy), 3n+2 (rz); assign_dofs writes
those indices onto each Node.

Extension point: member end releases (pinned ends) are not yet handled.
Implement them by static condensation of the released dof inside
assemble_global_stiffness, or with a penalty spring on the released rotation.
"""
from __future__ import annotations

import numpy as np

from .model import Frame
from .stiffness import element_geometry, k_global


def assign_dofs(frame: Frame) -> None:
    """Number the 3 dofs of every node in place: ux, uy, rz = 3n, 3n+1, 3n+2."""
    for n, node in enumerate(frame.nodes):
        node.ux, node.uy, node.rz = 3 * n, 3 * n + 1, 3 * n + 2


def restrained_dofs(frame: Frame) -> np.ndarray:
    """Global indices of all dofs fixed by a Support."""
    inds = []
    for n, sup in frame.supports.items():
        node = frame.nodes[n]
        for dof, flag in ((node.ux, sup.ux), (node.uy, sup.uy), (node.rz, sup.rz)):
            if flag:
                inds.append(dof)
    return np.array(inds, dtype=int)


def assemble_global_stiffness(frame: Frame) -> np.ndarray:
    """Assemble and return the 3n x 3n global stiffness matrix K."""
    assign_dofs(frame)
    n = len(frame.nodes)
    k = np.zeros((3 * n, 3 * n))
    for m in frame.members:
        i, j = frame.nodes[m.i], frame.nodes[m.j]
        length, c, s = element_geometry(i, j)
        ke = k_global(m.section, c, s, length)
        dofs = [i.ux, i.uy, i.rz, j.ux, j.uy, j.rz]
        for r, di in enumerate(dofs):
            for cc, dj in enumerate(dofs):
                k[di, dj] += ke[r, cc]
    return k
