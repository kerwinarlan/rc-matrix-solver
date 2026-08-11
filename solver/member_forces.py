"""Recover member end forces in local coordinates from global displacements.

f_local = k_local @ T @ u_element + f_fe, where f_fe are the fixed-end forces
of the member loads. Reported forces act ON the member (the forces the joints
apply to it); flip the sign for forces the member exerts on the joints.
"""
from __future__ import annotations

import numpy as np

from .model import Frame, Member, UDL
from .stiffness import element_geometry, k_local, transformation


def fixed_end_forces(member: Member, loads: list[UDL], length: float) -> np.ndarray:
    """Fixed-end forces (on the member) of its loads, local coordinates.

    Only full-span transverse UDLs are implemented; w positive = downward
    (local -y). Extension point: partial UDLs, axial loads, point loads.
    """
    ffe = np.zeros(6)
    for ld in loads:
        if not isinstance(ld, UDL):
            raise NotImplementedError(
                f"unsupported member load: {type(ld).__name__}"
            )
        w, l = ld.w, length
        ffe += np.array([0.0, w * l / 2, w * l ** 2 / 12, 0.0, w * l / 2, -w * l ** 2 / 12])
    return ffe


def member_end_forces(frame: Frame, u: np.ndarray) -> dict[int, np.ndarray]:
    """Local end forces per member: [N_i, V_i, M_i, N_j, V_j, M_j] (on the member)."""
    out = {}
    for midx, m in enumerate(frame.members):
        i, j = frame.nodes[m.i], frame.nodes[m.j]
        length, c, s = element_geometry(i, j)
        ue = np.concatenate([u[[i.ux, i.uy, i.rz]], u[[j.ux, j.uy, j.rz]]])
        ul = transformation(c, s) @ ue
        ffe = fixed_end_forces(m, frame.member_loads.get(midx, []), length)
        out[midx] = k_local(m.section, length) @ ul + ffe
    return out
