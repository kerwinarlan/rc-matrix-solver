"""Material properties and strength reduction factors per ACI 318-19.

NSCP 2015 (5th ed.) is based on ACI 318-08/11 and uses the same formulas with
different section numbers (the equivalence is noted per formula, not silently
assumed identical). NSCP is an SI code, so all units here are MPa, mm, N -
consistent with the rest of this tool.
"""

from dataclasses import dataclass

# Strength reduction factors, ACI 318-19 Tables 21.2.1 and 21.2.2
# (NSCP 2015 Sec 409.3.2 uses the same values).
PHI_FLEXURE: float = 0.90  # tension-controlled flexure
PHI_SHEAR: float = 0.75    # shear
PHI_COMPRESSION: float = 0.65  # compression-controlled, tied columns


@dataclass(frozen=True)
class Material:
    """Concrete and reinforcement material properties. Stresses in MPa."""

    fc: float  # concrete compressive strength, MPa
    fy: float  # reinforcement yield strength, MPa
    es: float = 200_000.0  # reinforcement modulus of elasticity, MPa (ACI 318-19 20.2.2.1)
    unit_weight: float = 24.0  # kN/m^3, normal-weight concrete (ACI 318-19 19.2.2.1)

    @property
    def epsilon_y(self) -> float:
        """Yield strain of reinforcement. ACI 318-19 20.2.2.1."""
        return self.fy / self.es


def beta1(fc: float) -> float:
    """Concrete stress-block factor beta1, ACI 318-19 22.2.2.4.3.

    0.85 for fc' <= 28 MPa, reduced by 0.05 per 7 MPa above 28 MPa, minimum 0.65.
    NSCP 2015 Sec 409.3.7 (ACI 318-08/11 10.2.7.3) is identical.
    """
    if fc <= 28.0:
        return 0.85
    if fc >= 55.0:
        return 0.65
    return 0.85 - 0.05 * (fc - 28.0) / 7.0
