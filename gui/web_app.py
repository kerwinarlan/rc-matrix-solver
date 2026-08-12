"""Browser frontend for the rc-matrix-solver frame engine.

Serves one page (embedded HTML) with two tabs:

- Demo L-frame: the familiar quick inputs (reuses gui/frame_gui.solve_lframe).
- Custom model (JSON): any 2D frame - nodes, members (E/A/I), supports,
  nodal loads, member UDLs - solved by the Direct Stiffness Method.

Both render the same way: loading animation, deformed-shape figure (SVG,
drawn animated, displacements magnified), reaction/member-force cards, and a
global equilibrium cross-check. The web server itself uses only the Python
standard library; the frame solver may have its own numerical dependencies.

Run:  python3 gui/web_app.py        (opens http://127.0.0.1:8000)
Self-check:  python3 gui/web_app.py --check   (headless, no browser)
"""

import argparse
import json
import math
import sys
import threading
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from gui.frame_gui import DEFAULTS, solve_lframe
except ModuleNotFoundError as exc:
    # Also support running these two frontend files from the same directory.
    if exc.name != "gui":
        raise
    from frame_gui import DEFAULTS, solve_lframe
from solver import Frame, Member, NodalLoad, Node, Section, Support, UDL, solve

#: Input keys in the same order/signature as solve_lframe.
FIELDS = [
    ("h", "Column height (m)"),
    ("l", "Beam span (m)"),
    ("e", "E (kN/m^2)"),
    ("a_col", "Column A (m^2)"),
    ("i_col", "Column I (m^4)"),
    ("a_beam", "Beam A (m^2)"),
    ("i_beam", "Beam I (m^4)"),
    ("w", "Beam UDL (kN/m, down)"),
    ("fx", "Lateral push at joint (kN)"),
]


def solve_model(model: dict) -> dict:
    """Solve an arbitrary 2D frame from the JSON model spec; JSON-safe result.

    Spec: {"nodes": [[x,y]...], "members": [{"i","j","E","A","I"}...],
    "supports": {i: [ux,uy,rz]}, "nodal_loads": {i: [fx,fy,mz]},
    "member_loads": {i: [w...]}}  (units kN, m as in the solver).
    """
    if not isinstance(model, dict):
        raise ValueError("model must be a JSON object")

    def finite(value, name):
        try:
            out = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be a number") from exc
        if not math.isfinite(out):
            raise ValueError(f"{name} must be finite")
        return out

    raw_nodes = model.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise ValueError("model needs at least one node")
    nodes = []
    for ni, xy in enumerate(raw_nodes):
        if not isinstance(xy, (list, tuple)) or len(xy) != 2:
            raise ValueError(f"node {ni} must be [x, y]")
        nodes.append(Node(finite(xy[0], f"node {ni} x"), finite(xy[1], f"node {ni} y")))

    raw_members = model.get("members")
    if not isinstance(raw_members, list) or not raw_members:
        raise ValueError("model needs at least one member")
    members = []
    for mi, m in enumerate(raw_members):
        if not isinstance(m, dict):
            raise ValueError(f"member {mi} must be an object")
        i, j = int(m["i"]), int(m["j"])
        if not (0 <= i < len(nodes) and 0 <= j < len(nodes) and i != j):
            raise ValueError(f"bad member indices {i}->{j} (have {len(nodes)} nodes)")
        if nodes[i].x == nodes[j].x and nodes[i].y == nodes[j].y:
            raise ValueError(f"member {mi} has zero length")
        e = finite(m["E"], f"member {mi} E")
        a = finite(m["A"], f"member {mi} A")
        inertia = finite(m["I"], f"member {mi} I")
        if e <= 0 or a <= 0 or inertia <= 0:
            raise ValueError(f"member {mi} E, A, I must be positive")
        members.append(Member(i, j, Section(E=e, A=a, I=inertia)))

    supports = {}
    for k, v in model.get("supports", {}).items():
        idx = int(k)
        if not 0 <= idx < len(nodes):
            raise ValueError(f"support at unknown node {idx}")
        if not isinstance(v, (list, tuple)) or len(v) > 3:
            raise ValueError(f"support at node {idx} must be [ux, uy, rz]")
        try:
            dofs = [x if isinstance(x, bool) else bool(int(x)) for x in v]
        except (TypeError, ValueError) as exc:
            raise ValueError(f"support at node {idx} must contain booleans or 0/1") from exc
        while len(dofs) < 3:
            dofs.append(False)
        supports[idx] = Support(*dofs)
    if not supports:
        raise ValueError("model needs at least one support")

    nodal = {}
    for k, v in model.get("nodal_loads", {}).items():
        idx = int(k)
        if not 0 <= idx < len(nodes):
            raise ValueError(f"load at unknown node {idx}")
        if not isinstance(v, (list, tuple)) or len(v) > 3:
            raise ValueError(f"load at node {idx} must be [fx, fy, mz]")
        vals = [finite(f, f"load at node {idx}") for f in v]
        vals.extend([0.0] * (3 - len(vals)))
        nodal[idx] = NodalLoad(*vals)

    member_l = {}
    for k, v in model.get("member_loads", {}).items():
        idx = int(k)
        if not 0 <= idx < len(members):
            raise ValueError(f"UDL on unknown member {idx}")
        if not isinstance(v, (list, tuple)):
            raise ValueError(f"UDLs on member {idx} must be a list")
        member_l[idx] = [UDL(w=finite(w, f"UDL on member {idx}")) for w in v]

    sol = solve(Frame(nodes, members, supports, nodal, member_l))

    # Global equilibrium: reactions + nodal loads + UDL resultants, with
    # moments about the origin. UDL total force is w*(dy, -dx) for a member
    # from i to j (positive w acts in local -y).
    ex = ey = em = 0.0
    for idx, (rx, ry, mz) in sol.reactions.items():
        ex += rx
        ey += ry
        em += mz + nodes[idx].x * ry - nodes[idx].y * rx
    for idx, ld in nodal.items():
        ex += ld.fx
        ey += ld.fy
        em += ld.mz + nodes[idx].x * ld.fy - nodes[idx].y * ld.fx
    for mi, udls in member_l.items():
        i, j = members[mi].i, members[mi].j
        dx = nodes[j].x - nodes[i].x
        dy = nodes[j].y - nodes[i].y
        w = sum(u.w for u in udls)
        fx, fy = w * dy, -w * dx   # positive w acts in local -y = (dy, -dx)/L
        xm = (nodes[i].x + nodes[j].x) / 2.0
        ym = (nodes[i].y + nodes[j].y) / 2.0
        ex += fx
        ey += fy
        em += xm * fy - ym * fx

    return {
        "nodes": [[n.x, n.y] for n in nodes],
        "u": [float(v) for v in sol.u],
        "members": [[m.i, m.j] for m in members],
        "supports": {k: [s.ux, s.uy, s.rz] for k, s in supports.items()},
        "nodal_loads": {k: [l.fx, l.fy, l.mz] for k, l in nodal.items()},
        "member_loads": {k: [u.w for u in udls] for k, udls in member_l.items()},
        "reactions": {k: [float(v) for v in vals] for k, vals in sol.reactions.items()},
        "member_forces": {k: [float(v) for v in vals] for k, vals in sol.member_forces.items()},
        "eq": {"fx": ex, "fy": ey, "m": em, "ok": bool(abs(ex) < 1e-6 and abs(ey) < 1e-6 and abs(em) < 1e-6)},
    }


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>rc-matrix-solver</title>
<style>
  :root { --ink:#1c2733; --mut:#5b6b7a; --line:#d8dfe6; --bg:#f4f6f8; --acc:#2563eb; --ok:#16a34a; --bad:#dc2626; }
  * { box-sizing: border-box; }
  body { margin:0; font-family: -apple-system, "Segoe UI", Roboto, sans-serif; color:var(--ink); background:var(--bg); }
  header { padding:18px 28px; background:#fff; border-bottom:1px solid var(--line); }
  header h1 { margin:0; font-size:18px; }
  header p { margin:4px 0 0; color:var(--mut); font-size:13px; }
  main { display:flex; flex-wrap:wrap; gap:20px; padding:20px 28px; align-items:flex-start; }
  .card { background:#fff; border:1px solid var(--line); border-radius:10px; padding:16px; }
  .side { width:320px; }
  .tabs { display:flex; gap:6px; margin-bottom:14px; }
  .tab { flex:1; padding:8px; font-size:13px; border-radius:8px; border:1px solid var(--line); background:#fff; cursor:pointer; color:var(--mut); }
  .tab.active { background:var(--acc); color:#fff; border-color:var(--acc); font-weight:600; }
  .panel { display:none; }
  .panel.active { display:block; }
  .panel label { display:block; font-size:12px; color:var(--mut); margin:9px 0 2px; }
  .panel input { width:100%; padding:7px 9px; font-size:14px; border:1px solid var(--line); border-radius:6px; font-variant-numeric: tabular-nums; }
  .panel input:focus, .panel textarea:focus { outline:2px solid var(--acc); border-color:transparent; }
  .panel textarea { width:100%; height:280px; font-family:ui-monospace, Menlo, monospace; font-size:12px; border:1px solid var(--line); border-radius:6px; padding:8px; resize:vertical; }
  .row { display:flex; gap:8px; margin-top:14px; }
  button { flex:1; padding:9px; font-size:14px; border-radius:6px; border:1px solid var(--line); background:#fff; cursor:pointer; }
  button#solve { background:var(--acc); color:#fff; border-color:var(--acc); font-weight:600; }
  button:active { transform:translateY(1px); }
  .stage { flex:1 1 560px; min-width:340px; }
  .figwrap { position:relative; }
  svg { display:block; width:100%; height:auto; }
  .spinner { position:absolute; inset:0; display:none; align-items:center; justify-content:center; flex-direction:column;
             background:rgba(255,255,255,.82); border-radius:10px; gap:12px; }
  .spinner.show { display:flex; }
  .ring { width:38px; height:38px; border-radius:50%; border:4px solid var(--line); border-top-color:var(--acc); animation:spin .8s linear infinite; }
  @keyframes spin { to { transform:rotate(360deg); } }
  @keyframes draw { to { stroke-dashoffset:0; } }
  .deformed { stroke-dasharray:1200; stroke-dashoffset:1200; animation:draw .9s ease-out forwards; }
  .fade { animation:fadein .5s ease-out both; }
  @keyframes fadein { from { opacity:0; } }
  .results { margin-top:16px; display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:10px; }
  .res { background:var(--bg); border-radius:8px; padding:8px 12px; font-size:13px; }
  .res .k { color:var(--mut); font-size:11px; }
  .res .v { font-size:14px; font-weight:600; font-variant-numeric:tabular-nums; }
  .eq { margin-top:10px; padding:8px 12px; border-radius:8px; font-size:13px; }
  .eq.ok { background:#f0fdf4; border:1px solid #bbf7d0; }
  .eq.bad { background:#fef2f2; border:1px solid #fecaca; }
  .cap { font-size:12px; color:var(--mut); margin-top:8px; }
  .err { color:var(--bad); font-size:13px; margin-top:8px; min-height:16px; }
</style>
</head>
<body>
<header>
  <h1>rc-matrix-solver - 2D frame analysis</h1>
  <p>Direct Stiffness Method, kN/m units. Tweak inputs (or paste a model), press Solve, watch the frame deform.</p>
</header>
<main>
  <div class="card side">
    <div class="tabs">
      <button id="tab-demo" class="tab active">Demo L-frame</button>
      <button id="tab-json" class="tab">Custom model (JSON)</button>
    </div>
    <div class="panel active" id="panel-demo">
      <div id="inputs"></div>
      <div class="row">
        <button id="solve">Solve</button>
        <button id="reset">Reset</button>
      </div>
    </div>
    <div class="panel" id="panel-json">
      <textarea id="model" spellcheck="false"></textarea>
      <div class="row">
        <button id="load-demo">Load demo</button>
        <button id="solve-json">Solve</button>
      </div>
      <div class="cap">nodes: [[x,y], ...] - members: {"i","j","E","A","I"} -
        supports/loads: {node: [ux,uy,rz]} / {node: [fx,fy,mz]} -
        member UDLs: {member: [w, ...]}, w positive downward.</div>
    </div>
    <div class="err" id="err"></div>
  </div>
  <div class="stage">
    <div class="card figwrap">
      <div class="spinner" id="spin"><div class="ring"></div><div>Solving frame...</div></div>
      <svg id="fig" viewBox="0 0 640 420" role="img" aria-label="frame figure"></svg>
    </div>
    <div class="cap" id="cap"></div>
    <div class="results" id="results"></div>
    <div class="eq" id="eq" hidden></div>
  </div>
</main>
<script>
const FIELDS = [["h","Column height (m)"],["l","Beam span (m)"],["e","E (kN/m^2)"],
  ["a_col","Column A (m^2)"],["i_col","Column I (m^4)"],["a_beam","Beam A (m^2)"],
  ["i_beam","Beam I (m^4)"],["w","Beam UDL (kN/m, down)"],["fx","Lateral push at joint (kN)"]];
const DEFAULTS = {h:5.0,l:6.0,e:25e6,a_col:0.16,i_col:0.002133,a_beam:0.15,i_beam:0.003125,w:20.0,fx:30.0};
const DEMO_MODEL = {nodes:[[0,0],[0,5],[6,5]], members:[
  {i:0,j:1,E:25e6,A:0.16,I:0.002133},
  {i:1,j:2,E:25e6,A:0.15,I:0.003125}],
  supports:{0:[true,true,true], 2:[false,true,false]},
  nodal_loads:{1:[30,0,0]}, member_loads:{1:[20]}};
const NS = "http://www.w3.org/2000/svg";
const fig = document.getElementById("fig");
const W = 640, H = 420, PAD = 46;

function el(name, attrs, parent) {
  const n = document.createElementNS(NS, name);
  for (const k in attrs) n.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(n);
  return n;
}
function arrowHead(parent) {
  const defs = el("defs", {}, parent);
  el("marker", {id:"ah", viewBox:"0 0 10 10", refX:"8", refY:"5", markerWidth:"7", markerHeight:"7", orient:"auto-start-reverse"},
    defs);
  el("path", {d:"M0,0 L10,5 L0,10 z", fill:"#1c2733"}, defs);
}
function arrow(x1,y1,x2,y2,parent,cls) {
  const a = el("line", {x1,y1,x2,y2,stroke:"#1c2733","stroke-width":2.5,markerEnd:"url(#ah)"}, parent);
  if (cls) a.setAttribute("class", cls);
  return a;
}
function momentArrow(px, py, val, parent, cls) {
  // Curly arrow for a moment about z: 270-degree arc. Positive Mz (model
  // CCW) appears clockwise on screen because the y axis is flipped.
  const r = 15, sw = val >= 0 ? 1 : 0, ey = py + (sw ? -r : r);
  const a = el("path", {d:`M${px+r},${py} A${r},${r} 0 1 ${sw} ${px},${ey}`,
    fill:"none", stroke:"#1c2733", "stroke-width":2.5, markerEnd:"url(#ah)"}, parent);
  if (cls) a.setAttribute("class", cls);
  return a;
}
function drawFixed(p, parent) {   // fixed base: hatch + triangle
  const g = el("g", {"class":"fade"}, parent);
  el("line", {x1:p.x-14, y1:p.y, x2:p.x-14, y2:p.y-16, stroke:"#5b6b7a", "stroke-width":2}, g);
  el("line", {x1:p.x,   y1:p.y, x2:p.x,   y2:p.y-16, stroke:"#5b6b7a", "stroke-width":2}, g);
  el("line", {x1:p.x-14,y1:p.y-8, x2:p.x, y2:p.y-8, stroke:"#5b6b7a", "stroke-width":2}, g);
  el("path", {d:"M-16,0 L16,0 L0,10 Z", fill:"#fff", stroke:"#5b6b7a", "stroke-width":2, transform:`translate(${p.x},${p.y})`}, g);
}
function drawPin(p, parent) {     // pin: triangle only
  const g = el("g", {"class":"fade"}, parent);
  el("path", {d:"M-12,0 L12,0 L0,9 Z", fill:"#fff", stroke:"#5b6b7a", "stroke-width":2, transform:`translate(${p.x},${p.y})`}, g);
}
function drawRoller(p, parent) {  // vertical roller: restrains uy
  const g = el("g", {"class":"fade"}, parent);
  el("line", {x1:p.x-22, y1:p.y+18, x2:p.x+22, y2:p.y+18, stroke:"#5b6b7a", "stroke-width":2}, g);
  el("path", {d:"M-12,0 L12,0 L0,9 Z", fill:"#fff", stroke:"#5b6b7a", "stroke-width":2, transform:`translate(${p.x},${p.y})`}, g);
  el("circle", {cx:p.x-6, cy:p.y+13, r:3.5, fill:"#fff", stroke:"#5b6b7a", "stroke-width":2}, g);
  el("circle", {cx:p.x+6, cy:p.y+13, r:3.5, fill:"#fff", stroke:"#5b6b7a", "stroke-width":2}, g);
}

function drawOtherSupport(p, dofs, parent) {
  const g = el("g", {"class":"fade"}, parent);
  el("rect", {x:p.x-7, y:p.y-7, width:14, height:14, rx:2, fill:"#fff", stroke:"#5b6b7a", "stroke-width":2}, g);
  const locked = ["ux","uy","rz"].filter((_, i) => dofs[i]).join(",");
  label(p.x + 11, p.y + 4, locked || "free", g, null, "start");
}
function label(x, y, txt, parent, cls, anchor) {
  const t = el("text", {x, y, "font-size":12, fill:"#5b6b7a", "text-anchor": anchor || "start"}, parent);
  if (cls) t.setAttribute("class", cls);
  t.textContent = txt;
  return t;
}
function fmt(v) { return Number(v).toLocaleString(undefined, {maximumFractionDigits: 3}); }

function render(res) {
  fig.innerHTML = "";
  arrowHead(fig);
  const nodes = res.nodes, u = res.u;
  const xs = nodes.map(n => n[0]), ys = nodes.map(n => n[1]);
  const xmin = Math.min(...xs), xmax = Math.max(...xs), ymin = Math.min(...ys), ymax = Math.max(...ys);
  const s = Math.min((W - 2*PAD) / Math.max(xmax - xmin, 1e-9), (H - 2*PAD) / Math.max(ymax - ymin, 1e-9));
  const X = (x, y) => PAD + (x - xmin) * s, Y = (x, y) => H - PAD - (y - ymin) * s;
  const P = nodes.map(n => ({x: X(n[0], n[1]), y: Y(n[0], n[1])}));

  // displacement magnification: biggest |ux|,|uy| maps to ~30% of the smaller span
  const dmax = Math.max(...nodes.map((n, i) => Math.max(Math.abs(u[3*i]), Math.abs(u[3*i+1]))), 1e-30);
  const mag = dmax > 1e-12 ? 0.3 * Math.min(xmax - xmin || 1, ymax - ymin || 1) / dmax : 0;
  const D = nodes.map((n, i) => ({
    x: P[i].x + s * mag * u[3*i],
    y: P[i].y - s * mag * u[3*i+1]
  }));

  // members: soft base, dashed centerline, animated deformed
  const members = res.members;
  for (const [i,j] of members) el("line", {x1:P[i].x,y1:P[i].y,x2:P[j].x,y2:P[j].y,stroke:"#c3ccd5","stroke-width":6}, fig);
  for (const [i,j] of members) el("line", {x1:P[i].x,y1:P[i].y,x2:P[j].x,y2:P[j].y,stroke:"#94a3b8","stroke-width":1.5,"stroke-dasharray":"6 4"}, fig);
  // deformed shape: cubic Bezier per member, end tangents rotated by rz
  for (const [i,j] of members) {
    const l = Math.hypot(P[j].x - P[i].x, P[j].y - P[i].y) || 1;
    const dx = (P[j].x - P[i].x) / l, dy = (P[j].y - P[i].y) / l;
    const rot = (c, r) => ({x: c.x*Math.cos(r) - c.y*Math.sin(r), y: c.x*Math.sin(r) + c.y*Math.cos(r)});
    const ri = -(u[3*i+2] || 0), rj = -(u[3*j+2] || 0);  // screen y flip
    const ti = rot({x: dx, y: dy}, ri), tj = rot({x: dx, y: dy}, rj);
    const k3 = l / 3;
    const c1 = {x: D[i].x + k3*ti.x, y: D[i].y + k3*ti.y};
    const c2 = {x: D[j].x - k3*tj.x, y: D[j].y - k3*tj.y};
    el("path", {d:`M${D[i].x},${D[i].y} C${c1.x},${c1.y} ${c2.x},${c2.y} ${D[j].x},${D[j].y}`,
      fill:"none", stroke:"#2563eb", "stroke-width":4, class:"deformed"}, fig);
  }
  for (const p of P) el("circle", {cx:p.x, cy:p.y, r:5, fill:"#fff", stroke:"#1c2733", "stroke-width":2}, fig);

  // supports
  for (const k in res.supports) {
    const [ux, uy, rz] = res.supports[k];
    if (ux && uy && rz) drawFixed(P[+k], fig);
    else if (ux && uy && !rz) drawPin(P[+k], fig);
    else if (!ux && uy && !rz) drawRoller(P[+k], fig);
    else drawOtherSupport(P[+k], [ux, uy, rz], fig);
  }

  // member UDLs: arrows along the local -y side (positive w = downward)
  for (const mi in res.member_loads) {
    const [i,j] = members[+mi];
    const wsum = res.member_loads[mi].reduce((a,b) => a + b, 0);
    const dx = nodes[j][0] - nodes[i][0], dy = nodes[j][1] - nodes[i][1], L = Math.hypot(dx, dy) || 1;
    const vx = -dy/L, vy = dx/L;             // model-space local -y
    // rays plus a line joining their tails (standard distributed-load diagram)
    const tails = [];
    for (let k = 1; k <= 5; k++) {
      const t = k/6, mx = nodes[i][0] + t*dx, my = nodes[i][1] + t*dy;
      const bx = X(mx, my), by = Y(mx, my);
      const ax = X(mx + vx, my + vy) - bx, ay = Y(mx + vx, my + vy) - by;
      const al = Math.hypot(ax, ay) || 1;
      const tail = {x: bx + ax/al*34, y: by + ay/al*34};
      tails.push(tail);
      arrow(tail.x, tail.y, bx + ax/al*14, by + ay/al*14, fig, "fade");
    }
    el("polyline", {points: tails.map(t => `${t.x},${t.y}`).join(" "),
      fill:"none", stroke:"#1c2733", "stroke-width":1.5, class:"fade"}, fig);
    const mx = nodes[i][0] + dx/2, my = nodes[i][1] + dy/2;
    const bx = X(mx, my), by = Y(mx, my);
    const ax = X(mx + vx, my + vy) - bx, ay = Y(mx + vx, my + vy) - by;
    const al = Math.hypot(ax, ay) || 1;
    label(bx + ax/al*46, by + ay/al*46, `w = ${fmt(wsum)} kN/m`, fig, "fade", "middle");
  }

  // nodal loads: arrows in the sign direction
  for (const k in res.nodal_loads) {
    const [fx, fy, mz] = res.nodal_loads[k];
    const p = P[+k];
    if (fx) {
      const d = fx > 0 ? 1 : -1;
      arrow(p.x + d*18, p.y - 20, p.x + d*44, p.y - 20, fig, "fade");
      label(p.x + d*50, p.y - 16, `Fx=${fmt(fx)}`, fig, "fade", d > 0 ? "start" : "end");
    }
    if (fy) {
      const d = fy > 0 ? 1 : -1;
      arrow(p.x + 20, p.y - d*18, p.x + 20, p.y - d*44, fig, "fade");
      label(p.x + 26, p.y - d*50, `Fy=${fmt(fy)}`, fig, "fade");
    }
    if (mz) {
      momentArrow(p.x - 30, p.y - 28, mz, fig, "fade");
      label(p.x - 30, p.y - 50, `Mz=${fmt(mz)}`, fig, "fade", "middle");
    }
  }

  // reactions at supported nodes
  for (const k in res.reactions) {
    const [rx, ry, mz] = res.reactions[k];
    const p = P[+k];
    if (rx) {
      const d = rx > 0 ? 1 : -1;
      arrow(p.x + d*24, p.y - 46, p.x + d*44, p.y - 46, fig, "fade");
      label(p.x + d*50, p.y - 42, `Rx=${fmt(rx)}`, fig, "fade", d > 0 ? "start" : "end");
    }
    if (ry) {
      const d = ry > 0 ? 1 : -1;
      arrow(p.x + 46, p.y - d*24, p.x + 46, p.y - d*44, fig, "fade");
      label(p.x + 52, p.y - d*50, `Ry=${fmt(ry)}`, fig, "fade");
    }
    if (mz) {
      momentArrow(p.x - 26, p.y - 4, mz, fig, "fade");
      label(p.x - 60, p.y + 4, `Mz=${fmt(mz)} kN*m`, fig, "fade", "end");
    }
  }

  // node indices
  nodes.forEach((n, i) => label(P[i].x + 7, P[i].y - 7, String(i), fig, null, "start"));

  // result cards
  const cards = [];
  for (const k in res.reactions) {
    const [rx, ry, mz] = res.reactions[k];
    cards.push([`Rx @ node ${k}`, fmt(rx) + " kN"], [`Ry @ node ${k}`, fmt(ry) + " kN"], [`Mz @ node ${k}`, fmt(mz) + " kN*m"]);
  }
  for (const k in (res.member_forces || {})) {
    const f = res.member_forces[k];
    cards.push([`Mbr ${k}: axial`, fmt(f[0]) + " kN"], [`Mbr ${k}: shear`, fmt(f[1]) + " kN"],
      [`Mbr ${k}: M i-end`, fmt(f[2]) + " kN*m"], [`Mbr ${k}: M j-end`, fmt(f[5]) + " kN*m"]);
  }
  const out = document.getElementById("results");
  out.innerHTML = "";
  for (const [k, v] of cards) {
    const d = document.createElement("div");
    d.className = "res fade";
    const kd = document.createElement("div"); kd.className = "k"; kd.textContent = k;
    const vd = document.createElement("div"); vd.className = "v"; vd.textContent = v;
    d.appendChild(kd); d.appendChild(vd);
    out.appendChild(d);
  }
  const ok = res.eq.ok;
  const eq = document.getElementById("eq");
  eq.hidden = false;
  eq.className = "eq " + (ok ? "ok" : "bad");
  eq.textContent = (ok ? "OK - " : "NOT BALANCED - ") +
    `equilibrium: sum Fx = ${res.eq.fx.toExponential(2)}, sum Fy = ${res.eq.fy.toExponential(2)}, sum M = ${res.eq.m.toExponential(2)}`;
  document.getElementById("cap").textContent =
    `Blue = deformed shape, ${mag > 0 ? "deformation scale x" + fmt(mag) : "no visible displacement"}. ` +
    `White dots = nodes (indices shown), triangles = supports, straight arrows = forces, curly arrows = moments.`;
}

function buildForm() {
  const box = document.getElementById("inputs");
  for (const [k, labelTxt] of FIELDS) {
    // HTML elements need createElement, not the SVG-namespace el() helper.
    const lab = document.createElement("label");
    lab.textContent = labelTxt;
    box.appendChild(lab);
    const inp = document.createElement("input");
    inp.type = "number"; inp.step = "any";
    inp.value = String(DEFAULTS[k]); inp.id = "in-" + k;
    box.appendChild(inp);
  }
}
function collect() {
  const v = {};
  for (const [k] of FIELDS) v[k] = parseFloat(document.getElementById("in-" + k).value);
  return v;
}

let activeTab = "demo";
function setTab(name) {
  activeTab = name;
  document.getElementById("tab-demo").classList.toggle("active", name === "demo");
  document.getElementById("tab-json").classList.toggle("active", name === "json");
  document.getElementById("panel-demo").classList.toggle("active", name === "demo");
  document.getElementById("panel-json").classList.toggle("active", name === "json");
}
document.getElementById("tab-demo").addEventListener("click", () => setTab("demo"));
document.getElementById("tab-json").addEventListener("click", () => setTab("json"));
document.getElementById("load-demo").addEventListener("click", () => {
  document.getElementById("model").value = JSON.stringify(DEMO_MODEL, null, 2);
});

async function solve() {
  const err = document.getElementById("err"); err.textContent = "";
  let body;
  if (activeTab === "demo") {
    const v = collect();
    for (const [k] of FIELDS) if (!isFinite(v[k])) { err.textContent = "Enter numbers only."; return; }
    body = JSON.stringify(v);
  } else {
    try { body = JSON.stringify({model: JSON.parse(document.getElementById("model").value)}); }
    catch (e) { err.textContent = "Invalid JSON: " + e.message; return; }
  }
  const spin = document.getElementById("spin"); spin.classList.add("show");
  const t0 = performance.now();
  try {
    const r = await fetch("/solve", {method:"POST", headers:{"Content-Type":"application/json"}, body});
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || "solve failed");
    const wait = Math.max(0, 500 - (performance.now() - t0));  // keep the loading animation visible
    await new Promise(res => setTimeout(res, wait));
    render(data);
  } catch (e) {
    err.textContent = "Error: " + e.message;
  } finally {
    spin.classList.remove("show");
  }
}

document.getElementById("solve").addEventListener("click", solve);
document.getElementById("solve-json").addEventListener("click", solve);
document.getElementById("reset").addEventListener("click", () => {
  for (const [k] of FIELDS) document.getElementById("in-" + k).value = DEFAULTS[k];
  document.getElementById("err").textContent = "";
});
buildForm();
document.getElementById("model").value = JSON.stringify(DEMO_MODEL, null, 2);
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", PAGE.encode("utf-8"))
        else:
            self._send(404, "text/plain", b"not found")

    def do_POST(self):
        if self.path != "/solve":
            self._send(404, "text/plain", b"not found")
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
            if "model" in payload:
                body = json.dumps(solve_model(payload["model"])).encode("utf-8")
            else:
                vals = {}
                for key in ("h", "l", "e", "a_col", "i_col", "a_beam", "i_beam", "w", "fx"):
                    v = float(payload[key])
                    if not math.isfinite(v):
                        raise ValueError("values must be finite numbers")
                    vals[key] = v
                if any(vals[k] <= 0 for k in ("h", "l", "e", "a_col", "i_col", "a_beam", "i_beam")):
                    raise ValueError("height, span, E, A and I must be positive")
                body = json.dumps(solve_lframe(**vals)).encode("utf-8")
            self._send(200, "application/json", body)
        except (KeyError, ValueError, TypeError, IndexError, json.JSONDecodeError) as exc:
            self._send(400, "application/json",
                       json.dumps({"error": str(exc)}).encode("utf-8"))

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # quiet server logs
        pass


def main():
    ap = argparse.ArgumentParser(description="Browser UI for rc-matrix-solver")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}"
    print(f"rc-matrix-solver web UI: {url}  (Ctrl-C to stop)")
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopped")


def _check():
    """Headless self-check: demo defaults + a custom model through the HTTP handler."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    base = f"http://127.0.0.1:{port}"

    def post(payload):
        req = urllib.request.Request(
            base + "/solve", data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"})
        return urllib.request.urlopen(req)

    # demo-tab endpoint
    res = json.loads(post(dict(DEFAULTS)).read())
    assert abs(res["mz"] - 110.2941900998947) < 1e-6, "mz mismatch"
    assert res["eq"]["ok"] and abs(res["eq"]["m"]) < 1e-6, "demo not balanced"
    assert len(res["u"]) == 9 and len(res["nodes"]) == 3
    assert set(res["member_forces"]) == {"0", "1"}

    # custom-model endpoint: same frame expressed as JSON
    custom = {
        "model": {
            "nodes": [[0.0, 0.0], [0.0, 5.0], [6.0, 5.0]],
            "members": [
                {"i": 0, "j": 1, "E": 25e6, "A": 0.16, "I": 0.002133},
                {"i": 1, "j": 2, "E": 25e6, "A": 0.15, "I": 0.003125},
            ],
            "supports": {0: [True, True, True], 2: [False, True, False]},
            "nodal_loads": {1: [30.0, 0.0, 0.0]},
            "member_loads": {1: [20.0]},
        }
    }
    res2 = json.loads(post(custom).read())
    assert res2["eq"]["ok"] and abs(res2["eq"]["m"]) < 1e-6, "custom model not balanced"
    assert abs(res2["reactions"]["0"][2] - 110.2941900998947) < 1e-6, "custom mz mismatch"

    # page contains the tab markup
    assert b'id="tab-json"' in urllib.request.urlopen(base + "/").read()

    # validation: missing key, bad span, bad member -> 400
    for bad in (
        dict(DEFAULTS, l=-6.0),
        {"model": {"nodes": [[0, 0]], "members": [{"i": 0, "j": 5, "E": 1, "A": 1, "I": 1}], "supports": {0: [1, 1, 1]}}},
        {"model": {"nodes": [[0, 0], [0, 0]], "members": [{"i": 0, "j": 1, "E": 1, "A": 1, "I": 1}], "supports": {0: [1, 1, 1]}}},
    ):
        try:
            post(bad)
            raise AssertionError("bad input must 400")
        except urllib.error.HTTPError as exc:
            assert exc.code == 400

    server.shutdown()
    server.server_close()
    print("web server self-check OK")


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(_check())
    main()
