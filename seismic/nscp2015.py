"""NSCP 2015 Section 208.5 equivalent lateral force (ELF) procedure.

Implements the course procedure from CE 152 Module 1: the nine seismic
parameters (S, Z, Na/Nv, Ca/Cv, I, R, T), the design base shear with the
two spectrum branches and the code minimums, the vertical distribution of
story forces, and the seismic load combinations. Every step carries a LaTeX
string and a plain-text twin so the output doubles as a reviewer.

Code references: NSCP 2015 7th Edition Section 208 (Table 208-1/2/3/5/6/7/8,
Table 208-11B, Eq. 208-8..208-15). The near-source tables match UBC-97
Tables 16-S/16-T, which NSCP 2015 adopts for Seismic Zone 4.

Units: Z, Na, Nv, Ca, Cv, I, R, Ct dimensionless; hn in m; weights W in kN;
T in s; forces in kN.

Self-check:  python3 -m seismic.nscp2015   (verifies the lecture's worked
example: Muntinlupa City, V = 2407 kN, F = [461, 1032, 914] kN).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

#: Table 208-2: soil profile types (description, type).
SOILS = {
    "SA": "Hard rock",
    "SB": "Rock",
    "SC": "Very dense soil",
    "SD": "Stiff soil",
    "SE": "Soft soil",
    "SF": "Weak soil (prohibited, needs site-specific)",
}
#: Table 208-3: seismic zone factor by zone.
ZONES = {2: 0.2, 4: 0.4}
#: Table 208-1: seismic importance factor by occupancy.
IMPORTANCE = {"Standard": 1.0, "Essential": 1.25, "Hazardous": 1.5}
#: Table 208-11B: common systems (R) with Eq. 208-12 period coefficient Ct.
SYSTEMS = {
    "RC special moment-resisting frame": (8.5, 0.0731),
    "RC intermediate moment-resisting frame": (5.5, 0.0731),
    "Steel special moment-resisting frame": (8.5, 0.0853),
    "Steel moment frame (lecture example)": (3.5, 0.0853),
    "RC shear wall": (5.5, 0.0488),
}
#: Zone 4 near-source factors (Tables 208-5/208-6, = UBC-97 16-S/16-T).
#: (distance_km, Na) rows per source type; beyond the last row the factor is 1.0.
NEAR_NA = {"A": [(2.0, 1.5), (5.0, 1.2), (10.0, 1.0)], "B": [(2.0, 1.3), (5.0, 1.0)], "C": []}
NEAR_NV = {
    "A": [(2.0, 2.0), (5.0, 1.6), (10.0, 1.2), (15.0, 1.0)],
    "B": [(2.0, 1.6), (5.0, 1.2), (10.0, 1.0)],
    "C": [(2.0, 1.2), (5.0, 1.0)],
}
#: Table 208-7: Ca by soil profile and zone factor (Z rows: 0.075..0.4).
CA = {
    "SA": [0.06, 0.12, 0.16, 0.24, 0.32],
    "SB": [0.08, 0.15, 0.20, 0.30, 0.40],
    "SC": [0.09, 0.18, 0.24, 0.33, 0.40],
    "SD": [0.12, 0.22, 0.28, 0.36, 0.44],
    "SE": [0.19, 0.30, 0.34, 0.36, 0.36],
    "SF": [0.0, 0.0, 0.0, 0.0, 0.0],
}
#: Table 208-8: Cv by soil profile and zone factor.
CV = {
    "SA": [0.06, 0.12, 0.16, 0.24, 0.32],
    "SB": [0.08, 0.15, 0.20, 0.30, 0.40],
    "SC": [0.13, 0.25, 0.32, 0.45, 0.56],
    "SD": [0.18, 0.32, 0.40, 0.54, 0.64],
    "SE": [0.26, 0.50, 0.64, 0.84, 0.96],
    "SF": [0.0, 0.0, 0.0, 0.0, 0.0],
}
Z_ROW = [0.075, 0.15, 0.2, 0.3, 0.4]


def fmt(x: float, sig: int = 4) -> str:
    """Short readable number (e.g. 2407, 0.7758)."""
    return f"{x:.{sig - 1}g}" if x else "0"


def _fmtn(x: float) -> str:
    """LaTeX number: scientific notation with \\times 10^{...} for big/small."""
    if x == 0:
        return "0"
    ax = abs(x)
    if ax >= 1e4 or ax < 1e-3:
        m, e = f"{x:.3e}".split("e")
        return rf"{m}\times 10^{{{int(e)}}}"
    return f"{x:.4g}"


def _near(factor_rows: list[tuple[float, float]], distance: float, default: float) -> float:
    for km, val in factor_rows:
        if distance <= km:
            return val
    return default


def _step(title: str, latex: str, plain: str) -> dict:
    return {"title": title, "latex": latex, "plain": plain}


@dataclass
class SeismicInputs:
    """All inputs of the ELF procedure (see elf() for defaults)."""

    zone: int = 4                    # seismic zone (2 or 4)
    soil: str = "SD"                 # soil profile type SA..SF
    source: str = "A"                # seismic source type A/B/C (Zone 4 only)
    distance: float = 2.0            # distance to the fault (km)
    importance: float = 1.0          # I, Table 208-1
    r: float = 8.5                   # R, Table 208-11B
    ct: float = 0.0731               # Ct, Eq. 208-12 (RC special MRF)
    hn: float = 9.3                  # height above the base to the roof (m)
    weights: list = None             # story weights wx, bottom to top (kN)
    heights: list = None             # story heights hx above base, bottom to top (m)
    t: float = None                  # actual/computed period override (s)


def elf(inp: SeismicInputs) -> dict:
    """Run the NSCP 2015 equivalent lateral force procedure, step by step.

    Returns a JSON-safe dict: params, base shear (both branches + minimums),
    vertical force distribution, load combinations, spectrum points for the
    plot, and a human-readable "steps" list with LaTeX + plain twins.
    """
    steps: list[dict] = []

    def num(x, name, lo=0.0):
        if x is None:
            raise ValueError(f"{name} is required")
        x = float(x)
        if not math.isfinite(x) or x <= lo:
            raise ValueError(f"{name} must be a positive number")
        return x

    zone = int(inp.zone)
    if zone not in ZONES:
        raise ValueError("zone must be 2 or 4")
    z = ZONES[zone]
    soil = inp.soil.upper().strip()
    if soil not in SOILS:
        raise ValueError(f"soil must be one of {', '.join(SOILS)}")
    if soil == "SF":
        raise ValueError("Soil Profile Type SF is not permitted; site-specific geotech required")
    source = inp.source.upper().strip()
    if source not in ("A", "B", "C"):
        raise ValueError("source must be A, B or C")
    distance = num(inp.distance, "distance", lo=0.0)
    i = num(inp.importance, "importance")
    r = num(inp.r, "R")
    ct = num(inp.ct, "Ct")
    hn = num(inp.hn, "hn")
    weights = [num(w, "weight") for w in inp.weights]
    heights = [num(h, "height") for h in inp.heights]
    if len(weights) != len(heights) or not weights:
        raise ValueError("weights and heights must have the same non-zero length")
    w_total = sum(weights)

    # ---- 1. parameters ---------------------------------------------------
    rows = [
        ("I", "Seismic importance factor", "Table 208-1", i),
        ("S", "Soil profile type", "Table 208-2", f"{soil} ({SOILS[soil]})"),
        ("Z", "Seismic zone factor", "Table 208-3", z),
        ("R", "Response modification coefficient", "Table 208-11B", r),
        ("Ct", "Period coefficient", "Eq. 208-12", ct),
    ]
    tex_rows = "\n".join(rf"{a} & \text{{{b}}} & \text{{{c}}} & {d} \\" for a, b, c, d in rows)
    plain_rows = "\n".join(f"  {a}: {b} ({c}) = {d}" for a, b, c, d in rows)
    steps.append(_step(
        "Seismic parameters",
        rf"\begin{{array}}{{llll}} {tex_rows} \end{{array}}",
        "Seismic parameters (NSCP 2015):\n" + plain_rows,
    ))

    # ---- 2. near-source factors ------------------------------------------
    if zone == 4:
        na = _near(NEAR_NA[source], distance, 1.0)
        nv = _near(NEAR_NV[source], distance, 1.0)
        na_row = next((f"{v}" for km, v in NEAR_NA[source] if distance <= km), "1.0")
        nv_row = next((f"{v}" for km, v in NEAR_NV[source] if distance <= km), "1.0")
        steps.append(_step(
            "Near-source factors (Zone 4, Tables 208-5/208-6)",
            rf"N_a = {na_row} \quad N_v = {nv_row} \quad \text{{(source {source}, distance {fmt(distance)} km)}}",
            f"Na = {na}, Nv = {nv} (source type {source}, distance {fmt(distance)} km from the fault)",
        ))
    else:
        na, nv = 1.0, 1.0
        steps.append(_step(
            "Near-source factors",
            r"N_a = N_v = 1.0 \quad \text{(Tables 208-5/208-6 apply to Zone 4 only)}",
            "Na = Nv = 1.0 (near-source factors apply to Zone 4 only)",
        ))

    # ---- 3. seismic coefficients ------------------------------------------
    ca_tab, cv_tab = CA[soil][Z_ROW.index(z)], CV[soil][Z_ROW.index(z)]
    ca, cv = ca_tab * na, cv_tab * nv
    steps.append(_step(
        "Seismic response coefficients (Tables 208-7/208-8)",
        rf"C_a = {fmt(ca_tab)} \times N_a = {fmt(ca_tab)} \times {fmt(na)} = {fmt(ca)}"
        rf"\qquad C_v = {fmt(cv_tab)} \times N_v = {fmt(cv_tab)} \times {fmt(nv)} = {fmt(cv)}",
        f"Ca = {ca_tab} x Na = {ca_tab} x {na} = {ca};  Cv = {cv_tab} x Nv = {cv_tab} x {nv} = {cv}",
    ))

    # ---- 4. natural period ------------------------------------------------
    t = inp.t if inp.t is not None else ct * hn ** 0.75
    t = num(t, "T")
    steps.append(_step(
        "Structure period (Eq. 208-12)",
        rf"T = C_t h_n^{{3/4}} = {fmt(ct)} \times {fmt(hn)}^{{0.75}} = {fmt(t)}\ \text{{s}}"
        if inp.t is None else
        rf"T = {fmt(t)}\ \text{{s (given or computed by dynamic analysis)}}",
        f"T = {ct} x {hn}^0.75 = {fmt(t)} s" if inp.t is None else f"T = {fmt(t)} s (given)",
    ))

    # ---- 5. transition period + branch -------------------------------------
    ts = cv / (2.5 * ca)
    plateau = t <= ts
    steps.append(_step(
        "Transition period and governing branch",
        rf"T_s = \frac{{C_v}}{{2.5 C_a}} = \frac{{{fmt(cv)}}}{{2.5 \times {fmt(ca)}}} = {fmt(ts)}\ \text{{s}}"
        rf"\quad\Rightarrow\quad T ({fmt(t)}\ \text{{s}}) \le T_s \text{{: short-period plateau }} 2.5C_a \text{{ controls}}"
        if plateau else
        rf"T_s = \frac{{C_v}}{{2.5 C_a}} = \frac{{{fmt(cv)}}}{{2.5 \times {fmt(ca)}}} = {fmt(ts)}\ \text{{s}}"
        rf"\quad\Rightarrow\quad T ({fmt(t)}\ \text{{s}}) > T_s \text{{: }}{{C_v}}/{{T}} \text{{ branch controls}}",
        f"Ts = Cv / (2.5 Ca) = {cv} / {2.5 * ca} = {fmt(ts)} s;  "
        f"T = {fmt(t)} s {'<=' if plateau else '>'} Ts so the "
        f"{'2.5Ca plateau' if plateau else 'Cv/T branch'} governs",
    ))

    # ---- 6. base shear branches ---------------------------------------------
    v_ca = 2.5 * ca * i * w_total / r
    v_cv = cv * i * w_total / (r * t)
    v_branch = min(v_ca, v_cv)
    steps.append(_step(
        "Design base shear branches (Eqs. 208-8/208-9)",
        rf"V_{{2.5C_a}} = \frac{{2.5 C_a I W}}{{R}} = \frac{{2.5({fmt(ca)})({fmt(i)})({fmt(w_total)})}}{{{fmt(r)}}} = {fmt(v_ca)}\ \text{{kN}}"
        rf"\qquad V_{{C_v/T}} = \frac{{C_v I W}}{{R T}} = \frac{{{fmt(cv)}({fmt(i)})({fmt(w_total)})}}{{{fmt(r)} \times {fmt(t)}}} = {fmt(v_cv)}\ \text{{kN}}"
        rf"\qquad V = \min({fmt(v_ca)}, {fmt(v_cv)}) = {fmt(v_branch)}\ \text{{kN}}",
        f"V(2.5Ca) = 2.5 x {ca} x {i} x {w_total} / {r} = {fmt(v_ca)} kN;  "
        f"V(Cv/T) = {cv} x {i} x {w_total} / ({r} x {t}) = {fmt(v_cv)} kN;  min = {fmt(v_branch)} kN",
    ))

    # ---- 7. minimums ---------------------------------------------------------
    v_min1 = 0.11 * ca * i * w_total
    v_min2 = 0.8 * z * nv * i * w_total / r if zone == 4 else 0.0
    mins = [v_min1] + ([v_min2] if zone == 4 else [])
    latex_min = (
        rf"V \ge 0.11 C_a I W = 0.11({fmt(ca)})({fmt(i)})({fmt(w_total)}) = {fmt(v_min1)}\ \text{{kN}}"
        + (rf"\qquad V \ge \frac{{0.8 Z N_v I W}}{{R}} = "
           rf"\frac{{0.8({fmt(z)})({fmt(nv)})({fmt(i)})({fmt(w_total)})}}{{{fmt(r)}}} = {fmt(v_min2)}\ \text{{kN (Zone 4)}}"
           if zone == 4 else "")
    )
    plain_min = (
        f"V >= 0.11 Ca I W = 0.11 x {ca} x {i} x {w_total} = {fmt(v_min1)} kN"
        + (f";  V >= 0.8 Z Nv I W / R = 0.8 x {z} x {nv} x {i} x {w_total} / {r} = {fmt(v_min2)} kN (Zone 4)" if zone == 4 else "")
    )
    steps.append(_step("Code minimum base shears (Eqs. 208-10/208-11)", latex_min, plain_min))

    # ---- 8. design base shear --------------------------------------------------
    v = max(v_branch, *mins)
    steps.append(_step(
        "Design base shear",
        rf"V = \max({fmt(v_branch)}, {', '.join(fmt(m) for m in mins)}) = {fmt(v)}\ \text{{kN}}",
        f"V = max({fmt(v_branch)}, {', '.join(fmt(m) for m in mins)}) = {fmt(v)} kN",
    ))

    # ---- 9. top force -------------------------------------------------------------
    ft = 0.07 * t * v if t > 0.7 else 0.0
    steps.append(_step(
        "Concentrated force at the top (Sec. 208.5.2.3)",
        rf"F_t = 0.07 T V = 0.07({fmt(t)})({fmt(v)}) = {fmt(ft)}\ \text{{kN}}"
        if t > 0.7 else
        r"F_t = 0 \quad \text{(T} \le 0.7 \text{ s: no concentrated top force)}",
        f"Ft = 0.07 x {t} x {v} = {fmt(ft)} kN" if t > 0.7 else "Ft = 0 (T <= 0.7 s)",
    ))

    # ---- 10. vertical distribution ------------------------------------------------
    wh = [wx * hx for wx, hx in zip(weights, heights)]
    s_wh = sum(wh)
    levels = []
    for k, (hx, wx, wxhx) in enumerate(zip(heights, weights, wh)):
        fx = (v - ft) * wxhx / s_wh
        levels.append({"hx": hx, "wx": wx, "wxhx": wxhx, "frac": wxhx / s_wh, "fx": fx})
    tex_rows = "\n".join(
        rf"{fmt(hx)} & {fmt(wx)} & {fmt(wxhx)} & {fmt(fx)} \\"
        for hx, wx, wxhx, fx in ((l["hx"], l["wx"], l["wxhx"], l["fx"]) for l in levels)
    )
    steps.append(_step(
        "Vertical distribution of seismic force (Eq. 208-15)",
        rf"F_x = (V - F_t)\, \frac{{w_x h_x}}{{\sum w_i h_i}}"
        rf"\qquad \sum w_i h_i = {fmt(s_wh)}\ \text{{kN m}}"
        rf"\\[4pt] \begin{{array}}{{cccc}} \text{{hx (m)}} & \text{{wx (kN)}} & \text{{wx*hx}} & \text{{Fx (kN)}} \\ {tex_rows} \end{{array}}",
        "Fx = (V - Ft) wx hx / sum(wi hi) = (V - Ft) wx hx / " + fmt(s_wh) + "\n" +
        "\n".join(f"  hx={fmt(l['hx'])} m, wx={fmt(l['wx'])} kN, wx*hx={fmt(l['wxhx'])}, Fx={fmt(l['fx'])} kN" for l in levels),
    ))

    # ---- 11. load combinations -------------------------------------------------------
    ev = 0.5 * ca * i
    u1, u2 = 1.2 + ev, 0.9 - ev
    steps.append(_step(
        "Seismic load combinations (E = rho*Eh + Ev)",
        rf"E_v = 0.5 C_a I D = 0.5({fmt(ca)})({fmt(i)})D = {fmt(ev)}D"
        rf"\\[2pt] U_1 = (1.2 + 0.5 C_a I)D + \rho E_h + f_1 L = {fmt(u1)}D + \rho E_h + f_1 L"
        rf"\\[2pt] U_2 = (0.9 - 0.5 C_a I)D + \rho E_h + 1.6 H = {fmt(u2)}D + \rho E_h + 1.6 H",
        f"Ev = 0.5 Ca I D = 0.5 x {ca} x {i} D = {fmt(ev)} D\n"
        f"U1 = (1.2 + {fmt(ev)})D + rho Eh + f1 L = {fmt(u1)}D + rho Eh + f1 L\n"
        f"U2 = (0.9 - {fmt(ev)})D + rho Eh + 1.6 H = {fmt(u2)}D + rho Eh + 1.6 H",
    ))

    # ---- spectrum points for the plot -----------------------------------------------
    spectrum = []
    for tpt in [i * 0.05 for i in range(61)]:  # 0 .. 3.0 s
        sa = 2.5 * ca if tpt <= ts else cv / tpt
        spectrum.append({"t": round(tpt, 2), "sa": round(sa, 4)})

    return {
        "params": {
            "soil": soil, "soil_desc": SOILS[soil], "zone": zone, "z": z,
            "source": source, "distance": distance, "na": na, "nv": nv,
            "ca": ca, "cv": cv, "i": i, "r": r, "ct": ct, "hn": hn,
            "t": t, "ts": ts, "w_total": w_total, "n_levels": len(levels),
        },
        "base_shear": {"v": v, "v_ca": v_ca, "v_cv": v_cv, "v_min1": v_min1,
                       "v_min2": v_min2, "ft": ft, "branch": "2.5 Ca plateau" if plateau else "Cv/T"},
        "levels": levels,
        "combos": {"ev": ev, "u1": u1, "u2": u2},
        "spectrum": spectrum,
        "steps": steps,
    }


def demo() -> None:
    """Self-check against the CE 152 Module 1 worked example (Muntinlupa City)."""
    inp = SeismicInputs(
        zone=4, soil="SD", source="A", distance=2.0,
        importance=1.0, r=8.5, ct=0.0731, hn=9.3,
        weights=[4400.0, 5000.0, 3000.0], heights=[3.2, 6.3, 9.3],
    )
    out = elf(inp)
    p = out["params"]
    # Lecture values: Na=1.5, Nv=2.0, Ca=0.66, Cv=1.28, T=0.39 s, V=2407 kN.
    assert p["na"] == 1.5 and p["nv"] == 2.0
    assert abs(p["ca"] - 0.66) < 1e-12 and abs(p["cv"] - 1.28) < 1e-12
    assert abs(p["t"] - 0.389) < 0.005
    v = out["base_shear"]["v"]
    assert abs(v - 2407.06) < 0.1, f"V = {v}, expected ~2407"
    fx = [l["fx"] for l in out["levels"]]
    assert abs(fx[0] - 461.2) < 1.0 and abs(fx[1] - 1031.9) < 1.0 and abs(fx[2] - 913.9) < 1.0, fx
    # Story forces sum back to V (no Ft since T < 0.7 s).
    assert abs(sum(fx) - v) < 1e-6
    assert out["base_shear"]["ft"] == 0.0
    # Combos: Ev = 0.33D, U1 = 1.53D, U2 = 0.57D.
    assert abs(out["combos"]["ev"] - 0.33) < 1e-12
    assert abs(out["combos"]["u1"] - 1.53) < 1e-12 and abs(out["combos"]["u2"] - 0.57) < 1e-12
    # Steps: every step has LaTeX and plain twins; spectrum covers the plateau.
    assert len(out["steps"]) == 11
    assert all(s["latex"] and s["plain"] for s in out["steps"])
    assert abs(out["spectrum"][0]["sa"] - 2.5 * p["ca"]) < 1e-6
    print("seismic self-check OK: V = %.1f kN, F = [%s] kN" % (v, ", ".join("%.0f" % f for f in fx)))


if __name__ == "__main__":
    demo()
