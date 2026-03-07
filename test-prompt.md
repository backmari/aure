You are refining a neutron reflectivity model (refl1d script) that did not fit well enough.

## Sample Description
50 nm Cu over 5 nm Ti on a silicon substrate. Ambient medium is dTHF. Reflection from the back (substrate)

## Current Model Script
```python
"""
Improved refl1d model for Cu/Ti on Si with back reflection geometry.
"""

import warnings
from refl1d.names import *

# Suppress refl1d deprecation warnings
warnings.filterwarnings("ignore", category=UserWarning, module="refl1d")

# ========== Load Data ==========
probe = load4("/home/mat/data/REFL_218386_combined_data_auto.txt")

# ========== Materials ==========
# SLD values in 1e-6 Å⁻²
ambient = SLD(name="dTHF", rho=6.3500)          # deuterated THF
cu_oxide = SLD(name="CuOxide", rho=5.0000)      # approximate Cu2O/CuO average
copper = SLD(name="Copper", rho=6.5500)
ti_oxide = SLD(name="TiOxide", rho=4.0000)      # TiO₂
titanium = SLD(name="Titanium", rho=-1.9500)
substrate = SLD(name="Silicon", rho=2.0700)

# ========== Sample Structure ==========
# Back reflection: neutrons enter from substrate side.
# Stack order (fronting to backing): ambient -> CuOxide -> Cu -> TiOxide -> Ti -> substrate
sample = (
    ambient(0, 5.0) |
    cu_oxide(20.0, 5.0) |
    copper(500.0, 5.0) |
    ti_oxide(15.0, 5.0) |
    titanium(50.0, 5.0) |
    substrate(0, 3.0)
)

# ========== Fit Parameter Bounds ==========
# Ambient (dTHF) SLD
sample[0].material.rho.range(5.3, 7.4)

# Cu oxide layer
sample[1].thickness.range(5.0, 50.0)
sample[1].material.rho.range(4.0, 6.5)
sample[1].interface.range(0.0, 20.0)

# Copper layer
sample[2].thickness.range(250.0, 800.0)
sample[2].material.rho.range(5.5, 7.5)
sample[2].interface.range(0.0, 20.0)

# Ti oxide interfacial layer
sample[3].thickness.range(5.0, 30.0)
sample[3].material.rho.range(3.5, 5.5)
sample[3].interface.range(0.0, 15.0)

# Titanium adhesion layer
sample[4].thickness.range(20.0, 120.0)
sample[4].material.rho.range(-3.5, -0.5)
sample[4].interface.range(0.0, 15.0)

# Silicon substrate roughness (realistic)
sample[5].interface.range(2.0, 10.0)
sample[5].material.rho.range(1.5, 2.5)

# ========== Probe Intensity ===========
# Allow intensity to vary to account for normalization uncertainty
probe.intensity.range(0.70, 1.10)

# ========== Experiment ==========
experiment = Experiment(probe=probe, sample=sample)
problem = FitProblem(experiment)
```

## Fit Results
- χ² (chi-squared): 2.311
- Method: dream
- Converged: Yes

## Best-fit Parameters (from fitting)
  - intensity REFL_218386_combined_data_auto: 1.0431
  - dTHF rho: 6.0076
  - CuOxide interface: 1.1687
  - CuOxide rho: 4.8763
  - CuOxide thickness: 37.1261
  - Copper interface: 0.2505
  - Copper rho: 6.3689
  - Copper thickness: 471.5857
  - TiOxide interface: 3.1705
  - TiOxide rho: 3.9641
  - TiOxide thickness: 18.6097
  - Titanium interface: 1.3896
  - Titanium rho: -1.8063
  - Titanium thickness: 28.2152
  - Silicon interface: 4.1797
  - Silicon rho: 2.1435

## Issues Identified
  - χ² = 2.311 is slightly above the acceptance threshold (2.2), indicating minor mismatches between model and data.
  - The fitted titanium thickness (28.2 Å) is considerably lower than the nominal 5 nm (50 Å) described in the sample.
  - The copper oxide layer is fitted to ~37 nm, which is far thicker than a typical native Cu‑oxide (10–20 Å) and may be unphysical.
  - The reported total estimated thickness (987.5 Å) does not match the sum of the individual layer thicknesses, suggesting a possible inconsistency in the model definition or extraction routine.

## Suggestions for Improvement
  - Constrain the Ti layer thickness to the known value (~50 Å) or allow a tighter bound around this value to see if the fit improves.
  - Reduce the allowed range for the Cu‑oxide thickness to a realistic native oxide thickness (10–30 Å) and refit; this may lower χ² and bring the total thickness into agreement.
  - Check whether the intensity scaling parameter is hitting a bound; if so, widen its allowed range or verify the normalization of the data.
  - Re‑examine the model definition to ensure that the total thickness reported by the extraction routine correctly sums the individual layers (including any buried interfaces).
  - If after the above adjustments χ² remains >2.2, consider adding a thin surface oxide layer on the copper (if not already present) with a realistic thickness (10–20 Å) to capture any interfacial contrast not currently modeled.

## Physics Features from Data
  - Estimated thickness: 987.5 Å
  - Estimated roughness: 10.4 Å
  - Estimated layers: 3
  - Critical edge at Qc=0.0136 Å⁻¹

## Task
Generate an IMPROVED refl1d model script that addresses the issues above.
You must output a COMPLETE, valid refl1d Python script (not a partial edit).

Rules:
1. Keep the same data file path and probe loading.
2. You may add layers, remove layers, change materials, adjust SLD values, change parameter bounds, or add constraints.
3. If parameters are hitting their bounds, widen those bounds.
4. If there are systematic residuals, consider adding an interface layer or adjusting the model structure.
5. Use the best-fit parameter values as starting points for the refined model where they are physically reasonable.
6. Always include `probe.intensity.range(...)` for normalization.
7. The script must end with `experiment = Experiment(probe=probe, sample=sample)` and `problem = FitProblem(experiment)`.
8. NEVER change the fitting engine/method. The fitting method is chosen by the workflow — focus only on the model.
9. By default, avoid adding an SiO₂ layer on the silicon substrate (see rule 16), unless the user explicitly requests it in their feedback below.
10. NEVER change the back-reflection/measurement geometry. If the current model uses `back_reflectivity(...)` or `back_absorption(...)`, you MUST keep it. Do NOT reverse the layer order or swap the fronting/backing media. The geometry is determined by the physical experiment and is NOT a fitting parameter.
11. NEVER change error bars, resolution, or Q-range — these are experimental parameters.
12. Use SLD ranges of at least ±1.0 around nominal values for each material to give the fitter sufficient freedom.
13. If a metal layer is **directly** in contact with the ambient medium (air, solvent, etc.)
    and no oxide or surface layer of any kind is already present between them, you MAY add a
    single thin native metal oxide layer (10–30 Å).  Common examples: CuO or Cu₂O on copper
    (SLD ~4–6 ×10⁻⁶ Å⁻²), TiO₂ on titanium.  **However**:
      - Do NOT add an oxide if there is already an oxide, SEI, or any other surface layer
        between the metal and the ambient.
      - Do NOT split an existing oxide into sublayers (e.g., CuO + Cu₂O).  Keep it simple.
      - Do NOT add TiO₂ on titanium if Ti is an adhesion layer NOT in contact with the ambient.
      - Prefer keeping the model simple (fewer layers) over adding speculative oxide layers.
14. CRITICAL refl1d API rule: `SLD(...)` objects do NOT have `.material`, `.thickness`, or `.interface` attributes. Those attributes only exist on `Slab` objects inside the sample stack. You MUST set parameter bounds using `sample[i]` indexing, for example:
      sample[0].material.rho.range(5.5, 7.0)   # ambient SLD
      sample[1].thickness.range(10.0, 30.0)     # first layer thickness
      sample[1].material.rho.range(2.0, 4.0)    # first layer SLD
      sample[1].interface.range(0.0, 5.0)       # first layer roughness
    NEVER write `copper.material.rho.range(...)` or `ambient.material.rho.range(...)` — this will crash with "'SLD' object has no attribute 'material'".
15. When adding a new layer, set its initial thickness to a physically reasonable
    value based on the material type:
      - SEI / organic layers: 50–200 Å
      - Metal oxide layers (CuO, Cu₂O, TiO₂): 10–50 Å
      - Metallic plating (Li, Cu): 10–100 Å
    NEVER add a layer with initial thickness < 5 Å — such layers cannot be resolved
    by the fitter and will collapse.  Also give the thickness range enough room
    (e.g., 5 to 500 Å for SEI, 5 to 200 Å for oxides).
16. By default, avoid adding an SiO₂ layer on the silicon substrate.  Native SiO₂
    is typically only 10–20 Å and in reflectometry it adds 3 parameters that can
    absorb signal from more important layers.  If an SiO₂ layer is already in the
    model, consider removing it or fixing its thickness to < 20 Å to free up fitting
    capacity for unknown layers.  **However**, if the user explicitly requests an
    SiO₂ layer in their feedback, you MUST add it.



Output ONLY the Python script, no markdown fences, no explanation — just the script itself.

IMPORTANT: If user feedback is provided below, it takes absolute priority over
any of the rules above.  The user is the domain expert — follow their
instructions even if they contradict a default rule.

## User Feedback (from the scientist running this analysis)
Can you remove the layer between the titanium and the copper, and add a silicon oxide layer between the substrate and the titanium

IMPORTANT: The user's feedback above is authoritative. Follow it even if it conflicts with any of the numbered rules above. The user is the domain expert and their instructions override all default constraints.
