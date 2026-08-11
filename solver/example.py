"""Runnable sanity check against hand-solvable frames.

Run from the repo root:  python3 solver/example.py

1. Propped cantilever: fixed at A, simple support at B, full-span UDL w.
   Hand values: theta_B = w L^3 / 48EI, R_A = 5 w L / 8, R_B = 3 w L / 8,
   M_A = w L^2 / 8.
2. Cantilever column: vertical member, lateral tip load P (ux = P L^3 / 3EI,
   rz = -P L^2 / 2EI) and axial tip load P (uy = P L / EA).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solver.model import Frame, Member, NodalLoad, Node, Section, Support, UDL
from solver.solve import solve


def _check(name: str, got: float, want: float, tol: float = 1e-6) -> None:
    rel = abs(got - want) / max(1.0, abs(want))
    assert rel <= tol, f"{name}: got {got}, want {want} (rel err {rel})"
    print(f"  {name:<10} {got:.10g}   (want {want:.10g})")


def propped_cantilever() -> None:
    L, w = 4.0, 10.0
    E, A, I = 2.0e8, 0.05, 2.0e-4
    frame = Frame(
        nodes=[Node(0.0, 0.0), Node(L, 0.0)],
        members=[Member(0, 1, Section(E, A, I))],
        supports={0: Support(ux=True, uy=True, rz=True), 1: Support(ux=True, uy=True)},
        member_loads={0: [UDL(w)]},
    )
    sol = frame.solve()
    print(f"propped cantilever: L = {L} m, w = {w} kN/m")
    _check("theta_B", sol.u[5], w * L ** 3 / (48 * E * I))
    _check("R_Ay", sol.reactions[0][1], 5 * w * L / 8)
    _check("R_By", sol.reactions[1][1], 3 * w * L / 8)
    _check("M_A", sol.reactions[0][2], w * L ** 2 / 8)
    _check("R_Bx", sol.reactions[1][0], 0.0)
    fe = sol.member_forces[0]
    _check("N_A", fe[0], 0.0)
    _check("V_A", fe[1], 5 * w * L / 8)
    _check("M_A(end)", fe[2], w * L ** 2 / 8)
    _check("V_B", fe[4], 3 * w * L / 8)
    _check("M_B(end)", fe[5], 0.0)
    # global equilibrium: sum F = 0, sum M about A = 0
    assert abs(sol.reactions[0][1] + sol.reactions[1][1] - w * L) < 1e-9
    assert abs(sol.reactions[0][2] + sol.reactions[1][1] * L - w * L ** 2 / 2) < 1e-9


def cantilever_column() -> None:
    H, P = 3.0, 10.0
    E, A, I = 2.0e8, 0.05, 2.0e-4
    frame = Frame(
        nodes=[Node(0.0, 0.0), Node(0.0, H)],
        members=[Member(0, 1, Section(E, A, I))],
        supports={0: Support(ux=True, uy=True, rz=True)},
        nodal_loads={1: NodalLoad(fx=P)},
    )
    sol = solve(frame)
    print(f"cantilever column, lateral tip load P = {P} kN (vertical member)")
    _check("tip ux", sol.u[3], P * H ** 3 / (3 * E * I))
    _check("tip rz", sol.u[5], -P * H ** 2 / (2 * E * I))
    _check("base rx", sol.reactions[0][0], -P)
    _check("base mz", sol.reactions[0][2], P * H)  # -P*H about base, reaction +P*H
    frame.nodal_loads = {1: NodalLoad(fy=P)}
    sol = solve(frame)
    print(f"cantilever column, axial tip load P = {P} kN")
    _check("tip uy", sol.u[4], P * H / (E * A))


def diagonal_member() -> None:
    """Fixed-base member along (3, 4); axial tip load along its axis.
    Checks the rotation matrix with both cos and sin nonzero."""
    c, s, L = 0.6, 0.8, 5.0
    P, E, A = 10.0, 2.0e8, 0.05
    frame = Frame(
        nodes=[Node(0.0, 0.0), Node(3.0, 4.0)],
        members=[Member(0, 1, Section(E, A, I=1e-4))],
        supports={0: Support(ux=True, uy=True, rz=True)},
        nodal_loads={1: NodalLoad(fx=P * c, fy=P * s)},
    )
    sol = solve(frame)
    print(f"diagonal member (c = {c}, s = {s}), axial tip load P = {P} kN")
    _check("tip ux", sol.u[3], P * L / (E * A) * c)
    _check("tip uy", sol.u[4], P * L / (E * A) * s)
    _check("tip rz", sol.u[5], 0.0)


if __name__ == "__main__":
    propped_cantilever()
    cantilever_column()
    diagonal_member()
    print("all sanity checks passed")
