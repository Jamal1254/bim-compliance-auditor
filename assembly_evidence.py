"""Compare *numbers* from separate IFC/PDF sources without asserting applicability.

This intentionally DOES NOT return audit PASS/FAIL. A wall's material layer
total may have a similar number to a cavity-wall assembly yet represent an
entirely different physical construction.
"""
import math


def numerical_wall_assembly_neighbours(elements, assembly, window_mm=10.0):
    """List comparable-looking numbers with explicit non-contractual status.

    window_mm is a display-only discovery window, never an allowed tolerance.
    """
    reference = float(assembly["AssemblyThickness_mm"])
    if not math.isfinite(reference) or reference <= 0:
        raise ValueError("Invalid nominal assembly dimension.")
    window = float(window_mm)
    if not math.isfinite(window) or window < 0:
        raise ValueError("Invalid numeric review window.")
    output = []
    for wall in elements:
        if not wall.get("Type", "").startswith("IfcWall"):
            continue
        measured = wall.get("Width")
        if isinstance(measured, bool) or not isinstance(measured, (int, float)):
            continue
        if not math.isfinite(measured):
            continue
        difference = float(measured) - reference
        if abs(difference) > window:
            continue
        output.append({
            "GlobalId": wall.get("GlobalId", ""),
            "IFCClass": wall.get("Type", ""),
            "WallName": wall.get("Name", ""),
            "Storey": wall.get("Storey", ""),
            "IsExternal": wall.get("IsExternal"),
            "ObservedIFC_mm": measured,
            "IFCMeasurementSource": wall.get("WidthSource", ""),
            "IFCMaterialLayers": "; ".join(str(m) for m in wall.get("Materials", [])),
            "PDFPage": assembly.get("PDFPage"),
            "PDFNominalAssembly_mm": reference,
            "SignedNumericalDifference_mm": round(difference, 4),
            "PDFQuotedLine": assembly.get("QuotedLine", ""),
            "DiscoveryWindow_mm_NOT_TOLERANCE": window,
            "ContractualApplicability": "NOT_VERIFIED",
            "PropertyComparability": "NOT_VERIFIED",
            "ComplianceVerdict": "NOT_ASSESSABLE",
        })
    return sorted(output, key=lambda x: (abs(x["SignedNumericalDifference_mm"]), str(x["GlobalId"])))
