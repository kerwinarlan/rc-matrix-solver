"""Step-by-step Direct Stiffness Method solution, LaTeX-ready.

Runs the real solver (solver.solve) on a Frame and documents every step the
course CE 152 Module 2 asks for by hand: element stiffness matrices (k_local,
k_global with the rotation T), the assembled global stiffness matrix, the load
vector, the reduced system after boundary conditions, the displacement
solution, and the support reactions. Each step carries a LaTeX string and a
plain-text twin, so the output works online (KaTeX) and offline.

Full matrices are rendered only for small frames (<= 12 global dofs, reduced
system <= 10x10); larger models keep the per-element matrices and solution
steps and note the matrix sizes instead.

Self-check:  python3 -m solver.steps   (re-verifies the demo L-frame steps
against the solver output).
"""
from __future__ import annotations

import numpy as np

from .model import Frame
from .solve import load_vector, solve
from .stiffness import element_geometry, k_global, k_local, transformation

_MAX_K = 12      # global dofs beyond which the full K matrix is not rendered
_MAX_RED = 10    # reduced-system size beyond which Kff is not rendered


def fmt(x: float, sig: int = 4) -> str:
    return f"{x:.{sig - 1}g}" if x else "0"


def tex_num(x: float) -> str:
    """LaTeX number: scientific with \\times 10^{...} for big/small values."""
    if x == 0:
        return "0"
    ax = abs(x)
    if ax >= 1e4 or ax < 1e-3:
        m, e = f"{x:.3e}".split("e")
        return rf"{m}\times 10^{{{int(e)}}}"
    return f"{x:.4g}"


def _bmatrix(m: np.ndarray) -> str:
    rows = " \\\\ ".join(" & ".join(tex_num(x) for x in row) for row in np.asarray(m))
    return rf"\begin{{bmatrix}} {rows} \end{{bmatrix}}"


def _step(title: str, latex: str, plain: str) -> dict:
    return {"title": title, "latex": latex, "plain": plain}


def solve_steps(frame: Frame) -> dict:
    """Step-by-step DSM solution of the frame; JSON-safe result."""
    sol = solve(frame)
    steps: list[dict] = []
    n = len(frame.nodes)
    n_dof = 3 * n
    k = np.zeros((n_dof, n_dof))

    # ---- 1. model ---------------------------------------------------------
    node_lines = "\n".join(
        rf"{i}: ({tex_num(nd.x)}, {tex_num(nd.y)})\ \text{{dofs }} {3*i}, {3*i+1}, {3*i+2} \\"
        for i, nd in enumerate(frame.nodes)
    )
    steps.append(_step(
        "Model and degrees of freedom",
        rf"\begin{{array}}{{ll}} \text{{node}} & \text{{coordinates (m), dofs}} \\ {node_lines} \end{{array}}",
        "Nodes (x, y) and global dofs (ux, uy, rz):\n" +
        "\n".join(f"  {i}: ({fmt(nd.x)}, {fmt(nd.y)}), dofs {3*i}, {3*i+1}, {3*i+2}" for i, nd in enumerate(frame.nodes)),
    ))

    # ---- 2. element matrices ------------------------------------------------
    for midx, m in enumerate(frame.members):
        i, j = frame.nodes[m.i], frame.nodes[m.j]
        length, c, s = element_geometry(i, j)
        kl = k_local(m.section, length)
        kg = k_global(m.section, c, s, length)
        dofs = [i.ux, i.uy, i.rz, j.ux, j.uy, j.rz]
        for r, di in enumerate(dofs):
            for cc, dj in enumerate(dofs):
                k[di, dj] += kg[r, cc]
        udls = frame.member_loads.get(midx, [])
        ffe_latex = ""
        ffe_plain = ""
        if udls:
            from .member_forces import fixed_end_forces  # local import: keep steps light

            w = sum(u.w for u in udls)
            ffe = fixed_end_forces(m, udls, length)
            ffe_latex = (rf"\qquad f_{{fe}} = {_bmatrix(ffe.reshape(6, 1))}"
                         rf"\ \text{{(UDL }} w={tex_num(w)}\ \text{{kN/m)}}")
            ffe_plain = (f"\n  Fixed-end forces (UDL w = {fmt(w)} kN/m): "
                         f"[{', '.join(fmt(x) for x in ffe)}]")
        steps.append(_step(
            f"Element {midx} (nodes {m.i}-{m.j}) stiffness matrices",
            rf"L = {tex_num(length)}\ \text{{m, }} c = {tex_num(c)}, s = {tex_num(s)}"
            rf"\\[4pt] k_{{local}} = {_bmatrix(kl)}"
            rf"\\[4pt] k_{{global}} = T^T k_{{local}} T = {_bmatrix(kg)}"
            + ffe_latex,
            f"Element {midx} (nodes {m.i}->{m.j}): L = {fmt(length)} m, cos = {fmt(c)}, sin = {fmt(s)}"
            f"\n  k_local (6x6) = [{' '.join(fmt(x) for x in kl.ravel())}]"
            f"\n  k_global (6x6) = [{' '.join(fmt(x) for x in kg.ravel())}]"
            + ffe_plain,
        ))

    # ---- 3. global stiffness ------------------------------------------------
    if n_dof <= _MAX_K:
        steps.append(_step(
            "Assembled global stiffness matrix",
            rf"K = \sum k_{{global}}^{{(e)}} = {_bmatrix(k)}",
            f"K (global, {n_dof}x{n_dof}) = assembled from the element matrices above",
        ))
    else:
        steps.append(_step(
            "Assembled global stiffness matrix",
            rf"K \text{{ is }} {n_dof} \times {n_dof} \text{{ (omitted: too large to display)}}",
            f"K (global, {n_dof}x{n_dof}) assembled; matrix omitted (too large to display)",
        ))

    # ---- 4. load vector -----------------------------------------------------
    f = load_vector(frame)
    steps.append(_step(
        "Global load vector",
        rf"f = {_bmatrix(f.reshape(n_dof, 1))}",
        f"f (global load vector) = [{', '.join(fmt(x) for x in f)}]",
    ))

    # ---- 5. reduced system ---------------------------------------------------
    from .assembly import restrained_dofs

    restrained = set(restrained_dofs(frame).tolist())
    free = [d for d in range(n_dof) if d not in restrained]
    kff = k[np.ix_(free, free)]
    ff = f[free]
    u = sol.u
    if len(free) <= _MAX_RED:
        steps.append(_step(
            "Reduced system after boundary conditions",
            rf"\text{{Free dofs: }} {', '.join(str(d) for d in free)}"
            rf"\\[4pt] K_{{ff}} = {_bmatrix(kff)}"
            rf"\qquad f_f = {_bmatrix(ff.reshape(len(free), 1))}"
            rf"\\[4pt] \text{{Solve }} K_{{ff}} u_f = f_f \text{{ for }} u_f",
            f"Free dofs {free}; solve the reduced system Kff uf = ff "
            f"(Kff = [{', '.join(fmt(x) for x in kff.ravel())}], ff = [{', '.join(fmt(x) for x in ff)}])",
        ))
    else:
        steps.append(_step(
            "Reduced system after boundary conditions",
            rf"\text{{Free dofs ({len(free)}) omitted: too large to display. Solve }} K_{{ff}} u_f = f_f.",
            f"Free dofs {free}; reduced system Kff uf = ff solved numerically "
            f"({len(free)} dofs, matrix omitted)",
        ))

    # ---- 6. displacements -----------------------------------------------------
    per_node = "\n".join(
        rf"{i} & ({tex_num(u[3*i])}, {tex_num(u[3*i+1])}, {tex_num(u[3*i+2])}) \\"
        for i in range(n)
    )
    steps.append(_step(
        "Nodal displacements",
        rf"\begin{{array}}{{ll}} \text{{node}} & \text{{(ux m, uy m, rz rad)}} \\ {per_node} \end{{array}}",
        "Displacements per node (ux m, uy m, rz rad):\n" +
        "\n".join(f"  {i}: ({fmt(u[3*i])}, {fmt(u[3*i+1])}, {fmt(u[3*i+2])})" for i in range(n)),
    ))

    # ---- 7. reactions ----------------------------------------------------------
    r = k @ u - f
    sup_lines = "\n".join(
        rf"{nidx} & ({tex_num(r[frame.nodes[nidx].ux])}, {tex_num(r[frame.nodes[nidx].uy])}, {tex_num(r[frame.nodes[nidx].rz])}) \\"
        for nidx in sorted(frame.supports)
    )
    steps.append(_step(
        "Support reactions (r = K u - f)",
        rf"R = \begin{{array}}{{ll}} \text{{node}} & \text{{(Rx kN, Ry kN, Mz kN m)}} \\ {sup_lines} \end{{array}}",
        "Reactions per support node (Rx kN, Ry kN, Mz kN m):\n" +
        "\n".join(f"  {nidx}: ({fmt(r[frame.nodes[nidx].ux])}, {fmt(r[frame.nodes[nidx].uy])}, {fmt(r[frame.nodes[nidx].rz])})"
                  for nidx in sorted(frame.supports)),
    ))

    return {
        "title": "Direct Stiffness Method - step-by-step",
        "steps": steps,
        "n_nodes": n,
        "n_free": len(free),
        "u": [float(v) for v in u],
        "reactions": {k: [float(v) for v in vals] for k, vals in sol.reactions.items()},
    }


def demo() -> None:
    """Self-check: steps must match the solver for the demo L-frame."""
    from .model import Member, Node, Section, Support, UDL, NodalLoad

    frame = Frame(
        nodes=[Node(0.0, 0.0), Node(0.0, 5.0), Node(6.0, 5.0)],
        members=[
            Member(0, 1, Section(E=25e6, A=0.16, I=0.002133)),
            Member(1, 2, Section(E=25e6, A=0.15, I=0.003125)),
        ],
        supports={0: Support(ux=True, uy=True, rz=True), 2: Support(uy=True)},
        nodal_loads={1: NodalLoad(fx=30.0)},
        member_loads={1: [UDL(w=20.0)]},
    )
    out = solve_steps(frame)
    sol = solve(frame)
    assert len(out["steps"]) == 8, [s["title"] for s in out["steps"]]
    assert all(s["latex"] and s["plain"] for s in out["steps"])
    # The steps carry the same numbers the solver produces.
    assert all(abs(a - b) < 1e-9 for a, b in zip(out["u"], sol.u))
    assert out["reactions"][0][2] == sol.reactions[0][2]
    # Element 0 matrix spot check: column axial stiffness EA/L = 25e6*0.16/5.
    assert "8.000\\times 10^{5}" in out["steps"][1]["latex"]
    print("solver steps self-check OK (%d steps, %d free dofs)" % (len(out["steps"]), out["n_free"]))


if __name__ == "__main__":
    demo()
