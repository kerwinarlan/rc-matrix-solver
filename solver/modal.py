"""Undamped free-vibration mode shapes (lumped masses, Guyan condensation).

Units follow the solver contract (kN, m): density is in t/m^3 (1 t = 1000 kg,
so concrete is 2.4 and steel is 7.85). Lumped translational mass is half of
each member's rho*A*L at each end node. Rotational dofs carry no mass and are
statically condensed (Guyan reduction), which keeps the reduced mass matrix
positive definite for np.linalg.eigh. Frequencies come back in Hz.

This is the classic textbook approximation: consistent-mass and rotary-inertia
effects are out of scope (ponytail: lumped masses, add consistent mass when a
frequency needs better than ~5% accuracy).
"""
from __future__ import annotations

import numpy as np

from .assembly import assemble_global_stiffness, restrained_dofs
from .model import Frame
from .stiffness import element_geometry


def lumped_mass(frame: Frame, density: float) -> np.ndarray:
    """Per-dof lumped translational masses (translations only, t)."""
    n = len(frame.nodes)
    m = np.zeros(3 * n)
    for mem in frame.members:
        i, j = frame.nodes[mem.i], frame.nodes[mem.j]
        length, _, _ = element_geometry(i, j)
        half = 0.5 * density * mem.section.A * length
        m[3 * mem.i] += half
        m[3 * mem.i + 1] += half
        m[3 * mem.j] += half
        m[3 * mem.j + 1] += half
    return m


def mode_shapes(frame: Frame, density: float = 2.4, nmodes: int = 3):
    """Lowest free-vibration modes as [(freq_hz, full_dof_vector), ...].

    Each vector is normalized so its largest component is 1 and includes the
    statically recovered joint rotations (drives the web UI's deformed shape).
    """
    k = assemble_global_stiffness(frame)
    mass = lumped_mass(frame, density)
    restrained = set(restrained_dofs(frame).tolist())
    n = k.shape[0]
    trans = [d for d in range(n) if d % 3 < 2 and d not in restrained]
    rot = [d for d in range(n) if d % 3 == 2 and d not in restrained]
    if not trans:
        raise ValueError("no free translational dofs: nothing to vibrate")
    ktt = k[np.ix_(trans, trans)]
    if rot:
        krr = k[np.ix_(rot, rot)]
        ktr = k[np.ix_(trans, rot)]
        reduced = ktt - ktr @ np.linalg.solve(krr, ktr.T)
    else:
        krr, ktr = None, None
        reduced = ktt
    mred = np.diag([mass[d] for d in trans])
    if any(mass[d] <= 0 for d in trans):
        raise ValueError("every free node needs a member for mass")
    # Standard form: K phi = w^2 M phi, M = L L^T -> (L^-1 K L^-1) psi = w^2 psi.
    l = np.sqrt(np.diag(mred))
    linv = np.diag(1.0 / l)
    std = linv @ reduced @ linv
    w2, psi = np.linalg.eigh(std)  # ascending w^2
    out = []
    u = np.zeros(n)
    for wi, ps in zip(w2, psi.T):
        if wi <= 1e-10:  # rigid-body modes (mechanism): skip
            continue
        vt = linv @ ps
        u[:] = 0.0
        u[trans] = vt
        if rot:
            u[rot] = -np.linalg.solve(krr, ktr.T @ vt)
        u /= float(np.max(np.abs(u)))
        out.append((float(np.sqrt(wi) / (2.0 * np.pi)), u.copy()))
        if len(out) == nmodes:
            break
    return out


def demo() -> None:
    """Self-check against exact cantilever / simply-supported frequencies."""
    sec = Section(E=25e6, A=0.15, I=0.003125)
    beam = Frame(
        nodes=[Node(0.0, 0.0), Node(6.0, 0.0)],
        members=[Member(0, 1, sec)],
        supports={0: Support(ux=True, uy=True, rz=True)},
    )
    ei = sec.E * sec.I
    m = 2.4 * sec.A  # t/m
    # Lumped-model closed forms (half the member mass at each end):
    # cantilever tip mass M/2 -> f = sqrt(3EI/((M/2) L^3))/(2 pi)
    f_cant = (3.0 * ei / ((m * 6.0 / 2.0) * 6.0 ** 3)) ** 0.5 / (2.0 * np.pi)
    modes = mode_shapes(beam)
    assert len(modes) == 2, "cantilever: one sway + one axial mode"
    assert abs(modes[0][0] - f_cant) / f_cant < 1e-9, f"cantilever f1 off: {modes[0][0]}"
    # Mode 1 of a cantilever: max deflection at the free end (node 1).
    assert abs(modes[0][1][3 + 1]) > 0.8, "free-end sway should dominate mode 1"

    # 3-node SS beam: the midspan node carries the bending mass (a 2-node
    # lumped model would lump all bending mass onto the restrained supports).
    ss = Frame(
        nodes=[Node(0.0, 0.0), Node(3.0, 0.0), Node(6.0, 0.0)],
        members=[Member(0, 1, sec), Member(1, 2, sec)],
        supports={0: Support(ux=True, uy=True), 2: Support(uy=True)},
    )
    # SS beam: midspan lumped mass M/2, k = 48EI/L^3.
    f_ss = (48.0 * ei / ((m * 6.0 / 2.0) * 6.0 ** 3)) ** 0.5 / (2.0 * np.pi)
    modes_ss = mode_shapes(ss)
    assert abs(modes_ss[0][0] - f_ss) / f_ss < 1e-9, f"SS beam f1 off: {modes_ss[0][0]}"
    # Mode 1 symmetric: midspan (node 1) sags most.
    assert abs(modes_ss[0][1][4]) > 0.8, "midspan should dominate mode 1"
    print("modal self-check OK (cantilever %.2f Hz, SS beam %.2f Hz)" % (modes[0][0], modes_ss[0][0]))


if __name__ == "__main__":
    from .model import Member, Node, Section, Support

    demo()
