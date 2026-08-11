"""Data model for a 2D frame.

Units contract: coordinates in m, forces in kN, moments in kN*m, E in kN/m^2
(1 MPa = 1000 kN/m^2), A in m^2, I in m^4, UDLs in kN/m. Loads act in global
axes; positive moments and rotations are counter-clockwise.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Node:
    """A joint at (x, y) in m. Dof indices (ux, uy, rz) are assigned by assembly."""

    x: float
    y: float
    ux: Optional[int] = None
    uy: Optional[int] = None
    rz: Optional[int] = None


@dataclass
class Section:
    """Cross-section properties: E (kN/m^2), A (m^2), I (m^4, bending about z)."""

    E: float
    A: float
    I: float


@dataclass
class Member:
    """Element from node i to node j; local x runs i -> j."""

    i: int
    j: int
    section: Section

    @property
    def E(self) -> float:
        return self.section.E

    @property
    def A(self) -> float:
        return self.section.A

    @property
    def I(self) -> float:
        return self.section.I


@dataclass
class Support:
    """Restraint per dof at a node. True = that dof is fixed (zero displacement)."""

    ux: bool = False
    uy: bool = False
    rz: bool = False


@dataclass
class NodalLoad:
    """Concentrated load at a node: fx, fy in kN; mz in kN*m (CCW positive)."""

    fx: float = 0.0
    fy: float = 0.0
    mz: float = 0.0


@dataclass
class UDL:
    """Full-span transverse UDL on a member: w in kN/m, positive = downward (local -y)."""

    w: float


@dataclass
class Frame:
    """A 2D frame model: nodes, members, supports, loads. Call solve() to analyze.

    Example:
        frame = Frame(
            nodes=[Node(0, 0), Node(4, 0)],
            members=[Member(0, 1, Section(E=2e8, A=0.05, I=2e-4))],
            supports={0: Support(ux=True, uy=True, rz=True)},
            nodal_loads={1: NodalLoad(fy=-10)},
        )
        sol = frame.solve()   # or solve(frame)
    """

    nodes: list[Node]
    members: list[Member]
    supports: dict[int, Support] = field(default_factory=dict)
    nodal_loads: dict[int, NodalLoad] = field(default_factory=dict)
    member_loads: dict[int, list[UDL]] = field(default_factory=dict)

    def solve(self) -> "Solution":
        """Analyze the frame; equivalent to solve.solve(self)."""
        from .solve import solve

        return solve(self)
