"""bridge - the Excel <-> Python seam for the RC Matrix Solver and Design tool.

Public API: layout data (``workbook_layout``), engine-neutral I/O
(``WorkbookIO`` / ``open_workbook``), template generation (``build_template``),
and the end-to-end orchestrator (``run.main``).

See ``docs/excel-bridge-architecture.md`` for the full design.
"""

from .excel_io import (
    InputData,
    OpenpyxlWorkbookIO,
    OutputData,
    WorkbookIO,
    XlwingsWorkbookIO,
    build_template,
    open_workbook,
)
from .workbook_layout import SHEETS, TABLES, Column, Table

__version__ = "0.1.0"

__all__ = [
    "InputData",
    "OutputData",
    "WorkbookIO",
    "OpenpyxlWorkbookIO",
    "XlwingsWorkbookIO",
    "build_template",
    "open_workbook",
    "SHEETS",
    "TABLES",
    "Column",
    "Table",
    "__version__",
]
