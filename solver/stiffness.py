"""Local and global stiffness matrices for a 2D frame element.

Element local axes: local x runs from node i to node j, local y is 90 deg CCW
from it. Local dofs and forces: [u_i, v_i, theta_i, u_j, v_j, theta_j].

The global element stiffness is k_global = T^T k_local T, where T maps global
dofs to local dofs (local = T @ global).

Units contract: length in m, E in kN/m^2 (1 MPa = 1000 kN/m^2), A in m^2,
I in m^4; stiffness entries come out in kN/m, kN, and kN*m.
"""
from __future__ import annotations

import numpy as np

from .model import Node, Section


def element_geometry(i: Node, j: Node) -> tuple[float, float, float]:
    """Return (length, cos, sin) of the direction from node i to node j."""
    dx, dy = j.x - i.x, j.y - i.y
    length = float(np.hypot(dx, dy))
    if length == 0.0:
        raise ValueError("member has zero length")
    return length, dx / length, dy / length


def k_local(sec: Section, length: float) -> np.ndarray:
    """Local 6x6 stiffness of a 2D frame element (axial + flexural)."""
    ea_l = sec.E * sec.A / length
    ei = sec.E * sec.I
    l2, l3 = length ** 2, length ** 3
    return np.array(
        [
            [ea_l, 0, 0, -ea_l, 0, 0],
            [0, 12 * ei / l3, 6 * ei / l2, 0, -12 * ei / l3, 6 * ei / l2],
            [0, 6 * ei / l2, 4 * ei / length, 0, -6 * ei / l2, 2 * ei / length],
            [-ea_l, 0, 0, ea_l, 0, 0],
            [0, -12 * ei / l3, -6 * ei / l2, 0, 12 * ei / l3, -6 * ei / l2],
            [0, 6 * ei / l2, 2 * ei / length, 0, -6 * ei / l2, 4 * ei / length],
        ]
    )


def transformation(c: float, s: float) -> np.ndarray:
    """6x6 rotation matrix T with local = T @ global (c = cos, s = sin)."""
    return np.array(
        [
            [c, s, 0, 0, 0, 0],
            [-s, c, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0],
            [0, 0, 0, c, s, 0],
            [0, 0, 0, -s, c, 0],
            [0, 0, 0, 0, 0, 1],
        ]
    )


def k_global(sec: Section, c: float, s: float, length: float) -> np.ndarray:
    """Global 6x6 element stiffness: k_global = T^T k_local T."""
    t = transformation(c, s)
    return t.T @ k_local(sec, length) @ t
