"""RC beam design package per ACI 318-19 (NSCP 2015 compatible).

Public API: design_beam() designs a rectangular beam section for flexure and
shear from plain values (Mu, Vu, geometry, materials). Lower-level functions
(design_flexure, design_shear, phi_mn, rho_min, rho_max) are exported for the
bridge and for direct use in checks.
"""

from .checks import BeamDesignResult, design_beam, design_members
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
from .materials import PHI_FLEXURE, PHI_SHEAR, Material, beta1
from .shear import ShearDesign, design_shear, vc_detailed, vc_simplified

__all__ = [
    "BAR_DIAMETERS_MM",
    "BeamDesignResult",
    "FlexureDesign",
    "Material",
    "PHI_FLEXURE",
    "PHI_SHEAR",
    "ShearDesign",
    "as_required_singly",
    "bar_area",
    "beta1",
    "design_beam",
    "design_flexure",
    "design_members",
    "design_shear",
    "phi_mn",
    "rho_max",
    "rho_min",
    "select_bars",
    "vc_detailed",
    "vc_simplified",
]
