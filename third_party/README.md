# Third-party repositories

Forks of external repos incorporated as git submodules. They are reference
material from Engr. Jaydee N. Lucero's talk "Python and its use in structural
engineering" (PythonAsia 2026, March 21, 2026):

- Blog post: https://engrjaydee.blogspot.com/2026/03/python-and-its-use-in-structural.html

| Submodule | Upstream | What it is | License |
|---|---|---|---|
| `truss_analyzer` | https://github.com/arisa-chan/truss_analyzer | 2D truss FEM with numpy + matplotlib (notebook-style script, needs Python 3.12+) | none stated (all rights reserved by default - contact the author before redistributing) |
| `midasgennx_2d_truss_example` | https://github.com/arisa-chan/midasgennx_2d_truss_example | 2D steel truss model/analyze/design/optimize via the MIDAS Gen NX 2026 API (`midas_civil`, requires a MIDAS license) | MIT (see its `LICENSE`) |
| `simple-beam-calculator` | https://github.com/arisa-chan/simple-beam-calculator | FreeSimpleGUI beam moment calculator - the tutorial behind `gui/frame_gui.py` (blog: Python GUI for Engineers, Jan 2026) | MIT (see its `LICENSE`) |

Each submodule points at our fork (`kerwinarlan/<repo>`), which tracks the
upstream default branch. Neither is imported by the solver, design, or bridge
packages - they are standalone examples kept here for reference. Clone with
`git submodule update --init` to fetch them.
