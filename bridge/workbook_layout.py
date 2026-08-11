"""Workbook sheet and named-range layout - the single source of truth.

Pure data module: no third-party imports. ``docs/excel-bridge-architecture.md``
mirrors this layout; change the data here first, then keep the doc in sync.

Conventions encoded here:

* One header row per table; data starts on the row below (``data_row``).
* Every data column maps to a named range: ``<GROUP>_<QUANTITY>`` for inputs,
  ``OUT_<GROUP>_<QUANTITY>`` for outputs. Column names are globally unique.
* Input tables carry a count named range ``<GROUP>_COUNT`` whose value sits in
  ``count_cell`` (a plain number, maintained by the user for Excel-side
  formulas). The Python reader ignores counts and scans until the first blank
  row, so stale counts never lose data.
* Named ranges cover rows ``data_row .. MAX_ROWS`` (static, generous) so cells
  written anywhere in that band are in range; blank cells read as missing data.
"""

from dataclasses import dataclass
from typing import Literal, Tuple

#: Named ranges span rows up to this row; readers stop at the first blank row.
MAX_ROWS = 1000

Direction = Literal["in", "out"]


@dataclass(frozen=True)
class Column:
    """One data column of a table: header text, named-range name, value kind."""

    header: str                                     #: Cell header shown in Excel.
    name: str                                       #: Named-range base name, e.g. NODE_X.
    dtype: Literal["id", "number"] = "number"       #: "id" -> int, "number" -> float.


@dataclass(frozen=True)
class Table:
    """A named table on a sheet: header position, direction, columns."""

    sheet: str                              #: Sheet name, e.g. "Inputs-Node".
    title: str                              #: Human title, e.g. "Nodal loads".
    start_row: int                          #: 1-based header row.
    start_col: int                          #: 1-based first data column.
    direction: Direction                    #: "in" (read from) or "out" (write to).
    columns: Tuple[Column, ...]             #: Columns left to right.
    count_name: str = ""                    #: Named range for the row count (inputs only).
    count_cell: str = ""                    #: A1-style cell holding the count value, e.g. "I1".

    @property
    def data_row(self) -> int:
        """1-based row where data starts (header row + 1)."""
        return self.start_row + 1


#: Every sheet and table, in workbook order. Inputs read by Python; outputs written by Python.
TABLES: Tuple[Table, ...] = (
    # --- Inputs -----------------------------------------------------------
    Table(
        sheet="Inputs-Node", title="Node inputs", start_row=1, start_col=1,
        direction="in", count_name="NODE_COUNT", count_cell="I1",
        columns=(
            Column("Node ID", "NODE_ID", "id"),
            Column("X (m)", "NODE_X"),
            Column("Y (m)", "NODE_Y"),
            Column("Restraint UX (1=fixed)", "NODE_SUP_UX"),
            Column("Restraint UY (1=fixed)", "NODE_SUP_UY"),
            Column("Restraint RZ (1=fixed)", "NODE_SUP_RZ"),
        ),
    ),
    Table(
        sheet="Inputs-Member", title="Member inputs", start_row=1, start_col=1,
        direction="in", count_name="MEMBER_COUNT", count_cell="I1",
        columns=(
            Column("Member ID", "MEMBER_ID", "id"),
            Column("I-Node ID", "MEMBER_I_NODE", "id"),
            Column("J-Node ID", "MEMBER_J_NODE", "id"),
            Column("E (Pa)", "MEMBER_E"),
            Column("A (m^2)", "MEMBER_A"),
            Column("I (m^4)", "MEMBER_I"),
        ),
    ),
    Table(
        sheet="Inputs-Loads", title="Nodal loads", start_row=1, start_col=1,
        direction="in", count_name="LOAD_N_COUNT", count_cell="I1",
        columns=(
            Column("Node ID", "LOAD_NODE", "id"),
            Column("Fx (N)", "LOAD_N_FX"),
            Column("Fy (N)", "LOAD_N_FY"),
            Column("Mz (N*m)", "LOAD_N_MZ"),
        ),
    ),
    Table(
        sheet="Inputs-Loads", title="Member UDLs", start_row=6, start_col=1,
        direction="in", count_name="LOAD_U_COUNT", count_cell="I6",
        columns=(
            Column("Member ID", "LOAD_MEMBER", "id"),
            Column("wx (N/m)", "LOAD_U_WX"),
            Column("wy (N/m)", "LOAD_U_WY"),
        ),
    ),
    Table(
        sheet="Inputs-Materials", title="Material inputs", start_row=1, start_col=1,
        direction="in", count_name="MATERIAL_COUNT", count_cell="I1",
        columns=(
            Column("fc' (Pa)", "MATERIAL_FC"),
            Column("fy (Pa)", "MATERIAL_FY"),
            Column("Es (Pa)", "MATERIAL_ES"),
        ),
    ),
    # --- Outputs ----------------------------------------------------------
    Table(
        sheet="Outputs-Displacements", title="Nodal displacements", start_row=1, start_col=1,
        direction="out",
        columns=(
            Column("Node ID", "OUT_DISP_NODE_ID", "id"),
            Column("ux (m)", "OUT_DISP_UX"),
            Column("uy (m)", "OUT_DISP_UY"),
            Column("rz (rad)", "OUT_DISP_RZ"),
        ),
    ),
    Table(
        sheet="Outputs-Reactions", title="Support reactions", start_row=1, start_col=1,
        direction="out",
        columns=(
            Column("Node ID", "OUT_REAC_NODE_ID", "id"),
            Column("Fx (N)", "OUT_REAC_FX"),
            Column("Fy (N)", "OUT_REAC_FY"),
            Column("Mz (N*m)", "OUT_REAC_MZ"),
        ),
    ),
    Table(
        sheet="Outputs-MemberForces", title="Member end forces", start_row=1, start_col=1,
        direction="out",
        columns=(
            Column("Member ID", "OUT_MF_MEMBER_ID", "id"),
            Column("Axial (N)", "OUT_MF_AXIAL"),
            Column("Shear (N)", "OUT_MF_SHEAR"),
            Column("Moment i-end (N*m)", "OUT_MF_M_I"),
            Column("Moment j-end (N*m)", "OUT_MF_M_J"),
        ),
    ),
    Table(
        sheet="Outputs-Design", title="RC design results", start_row=1, start_col=1,
        direction="out",
        columns=(
            Column("Member ID", "OUT_DES_MEMBER_ID", "id"),
            Column("As required (mm^2)", "OUT_DES_AS_REQ"),
            Column("As provided (mm^2)", "OUT_DES_AS_PROV"),
            Column("Stirrup spacing (mm)", "OUT_DES_STIRRUP"),
        ),
    ),
)

#: Sheet creation order for the template generator (Inputs-Loads hosts two tables).
SHEETS: Tuple[str, ...] = (
    "Inputs-Node",
    "Inputs-Member",
    "Inputs-Loads",
    "Inputs-Materials",
    "Outputs-Displacements",
    "Outputs-Reactions",
    "Outputs-MemberForces",
    "Outputs-Design",
)


def column_letter(index: int) -> str:
    """1-based column index to Excel letters: 1 -> "A", 27 -> "AA"."""
    letters = ""
    while index > 0:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters
