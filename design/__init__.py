"""RC member design package per ACI 318-19 (NSCP 2015 compatible).

Public API: design_beam() designs a rectangular beam section for flexure and
shear from plain values (Mu, Vu, geometry, materials); design_column()
designs a tied rectangular column for axial load and uniaxial moment
(P-M interaction) from plain values (Pu, Mu, geometry, materials).
Lower-level functions (design_flexure, design_shear, design_column,
phi_mn, phi_pn_max, rho_min, rho_max) are exported for the bridge and for
direct use in checks.
"""

from .checks import BeamDesignResult, design_beam, design_members
from .column import (
    RHO_MAX_COLUMN,
    RHO_MIN_COLUMN,
    ColumnDesignResult,
    axial_capacity,
    design_column,
    nominal_point,
    phi_mn_at_pu,
    tie_spacing,
)
from .flexure import (
    BAR_DIAMETERS_MM,
    FlexureDesign,
    as_required_singly,
    bar_area,
    design_flexure,
    phi_mn,
    rho_max,
    rho_min,
    select_bars,
)
from .materials import (
    PHI_COMPRESSION,
    PHI_FLEXURE,
    PHI_SHEAR,
    Material,
    beta1,
)
from .shear import ShearDesign, design_shear, vc_detailed, vc_simplified

__all__ = [
    "BAR_DIAMETERS_MM",
    "BeamDesignResult",
    "ColumnDesignResult",
    "FlexureDesign",
    "Material",
    "PHI_COMPRESSION",
    "PHI_FLEXURE",
    "PHI_SHEAR",
    "RHO_MAX_COLUMN",
    "RHO_MIN_COLUMN",
    "ShearDesign",
    "as_required_singly",
    "axial_capacity",
    "bar_area",
    "beta1",
    "design_beam",
    "design_column",
    "design_flexure",
    "design_members",
    "design_shear",
    "nominal_point",
    "phi_mn",
    "phi_mn_at_pu",
    "rho_max",
    "rho_min",
    "select_bars",
    "tie_spacing",
    "vc_detailed",
    "vc_simplified",
]
