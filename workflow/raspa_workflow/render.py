from __future__ import annotations

from typing import Any


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def render_simulation(cfg: dict[str, Any], task: dict[str, Any]) -> str:
    sim = cfg["simulation"]
    outputs = cfg.get("outputs", {})
    workflow = cfg["workflow"]
    lines = [
        "SimulationType                MonteCarlo",
        f"NumberOfCycles                {sim['production_cycles']}",
        f"NumberOfInitializationCycles  {sim['initialization_cycles']}",
        f"PrintEvery                     {sim['print_every']}",
        "RestartFile                   no",
        "",
    ]
    movies = workflow == "minimization" or outputs.get("movies", False)
    lines += [
        f"Movies                         {_yes_no(movies)}",
        f"WriteMoviesEvery               {outputs.get('movies_every', 1 if workflow == 'minimization' else 1000)}",
        "",
    ]
    if workflow == "minimization":
        minimization = cfg.get("minimization", {})
        lines += [
            f"MaximumNumberOfMinimizationSteps {minimization.get('maximum_steps', 1000)}",
            f"RMSGradientTolerance             {minimization.get('rms_gradient_tolerance', '1e-6')}",
            f"MaxGradientTolerance             {minimization.get('max_gradient_tolerance', '1e-6')}",
            "RemoveTranslationFromHessian     yes",
            "RemoveRotationFromHessian        yes",
            "Ensemble                         NVT",
            "",
        ]
    lines += [
        "UseChargesFromCIFFile         yes",
        "ChargeMethod                  Ewald",
        f"CutOff                        {sim.get('cutoff', 12.0)}",
        "Forcefield                    local",
        f"EwaldPrecision                {sim.get('ewald_precision', '1e-6')}",
        "",
        "Framework 0",
        f"FrameworkName                 {task['framework']}",
        "RemoveAtomNumberCodeFromLabel yes",
        f"UnitCells                     {' '.join(str(x) for x in task['unitcells'])}",
    ]
    hvf = cfg.get("helium_void_fractions", {}).get(task["framework"])
    if hvf is not None:
        lines.append(f"HeliumVoidFraction             {hvf}")
    lines += [f"ExternalTemperature            {task['temperature']}"]
    if workflow != "minimization":
        lines.append(f"ExternalPressure               {task['pressure']}")

    flexible = cfg.get("flexible", {})
    if flexible.get("enabled"):
        lines += [
            f"TimeStep                      {flexible.get('time_step', 0.0005)}",
            "FrameworkDefinitions           local",
            "FlexibleFramework              yes",
            "HybridNVEMoveProbability       1.0",
            f"  NumberOfHybridNVESteps       {flexible.get('hybrid_nve_steps', 5)}",
        ]

    if workflow != "minimization" and outputs.get("vtk", False):
        grid = " ".join(str(x) for x in outputs.get("vtk_grid_points", [150, 150, 150]))
        lines += [
            "",
            "ComputeDensityProfile3DVTKGrid yes",
            f"WriteDensityProfile3DVTKGridEvery {outputs.get('vtk_every', 500)}",
            f"DensityProfile3DVTKGridPoints  {grid}",
            "AverageDensityOverUnitCellsVTK yes",
            "RemoveAtomNumberCodeFromLabel  yes",
            "DensityAveragingTypeVTK        FullBox",
        ]

    lines.append("")
    components = task["components"]
    fractions = task["fractions"]
    for index, (component, fraction) in enumerate(zip(components, fractions)):
        lines += [
            f"Component {index} MoleculeName               {component}",
            "            MoleculeDefinition               Local",
            f"            MolFraction                      {fraction}",
            "            TranslationProbability           0.5",
            "            ReinsertionProbability           0.5",
        ]
        if workflow != "minimization" and component.lower() == "n2":
            lines.append("            RotationProbability              0.5")
        if workflow == "minimization":
            lines += [
                "            RotationProbability              0.5",
                "            CreateNumberOfMolecules           1",
            ]
        else:
            lines += [
                "            SwapProbability                  1.0",
                "            CreateNumberOfMolecules           0",
            ]
            if len(components) > 1:
                changes = " ".join(str(i) for i in range(len(components)))
                lines += [
                    "            IdentityChangeProbability      0.1",
                    f"            NumberOfIdentityChanges       {len(components)}",
                    f"            IdentityChangesList           {changes}",
                ]
        lines.append("")
    return "\n".join(lines) + "\n"
