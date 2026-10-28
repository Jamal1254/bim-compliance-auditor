"""Project-independent, user-configured comparison of IFC wall material layers.

The uploaded PDF remains a source of evidence, not an automatically applicable
contract. A human must select the source passage and enter/confirm the ordered
layer values for this controlled experiment. No project name, jurisdiction,
material, or thickness is hard-coded.
"""
import math


def _positive_number(value):
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) and n > 0 else None


def parse_layer_configuration(labels_text, thicknesses_text):
    """Parse comma-separated labels and positive mm values, preserving order."""
    labels = [x.strip() for x in str(labels_text or "").split(",") if x.strip()]
    raw_values = [x.strip() for x in str(thicknesses_text or "").split(",") if x.strip()]
    if not labels or not raw_values:
        raise ValueError("Enter layer labels and expected thicknesses in mm.")
    if len(labels) != len(raw_values):
        raise ValueError("The number of layer labels must equal the number of thickness values.")
    values = []
    for raw in raw_values:
        value = _positive_number(raw)
        if value is None:
            raise ValueError(f"Invalid positive layer thickness: {raw!r}")
        values.append(value)
    return [{"LayerIndex": i, "RuleLayerLabel": labels[i-1],
             "ExpectedThickness_mm": values[i-1]}
            for i in range(1, len(labels)+1)]


def compare_wall_layers_to_configured_rule(
    walls, expected_layers, *, source_page=None, source_quote="", source_label="",
    name_or_type_filter="", numeric_consistency_tolerance_mm=0.5,
):
    """Compare ordered declared IFC layer thicknesses with user-confirmed values.

    The numeric consistency tolerance is only for checking whether the layer
    sum agrees with IFC's separate overall-width evidence. It is not a design
    or regulatory tolerance. Configured-value comparison uses 0.01 mm only
    to accommodate ordinary IFC decimal serialization.
    """
    if not expected_layers:
        raise ValueError("At least one configured layer is required.")
    expected = [_positive_number(x.get("ExpectedThickness_mm")) for x in expected_layers]
    if any(x is None for x in expected):
        raise ValueError("All configured expected layer thicknesses must be positive numbers.")
    labels = [str(x.get("RuleLayerLabel") or f"Layer {i}")
              for i, x in enumerate(expected_layers, 1)]
    search = str(name_or_type_filter or "").strip().casefold()
    output = []
    for wall in walls:
        if str(wall.get("Type") or "") not in {"IfcWall", "IfcWallStandardCase"}:
            continue
        name = str(wall.get("Name") or "")
        wall_type = str(wall.get("TypeName") or wall.get("ElementType") or "")
        if search and search not in f"{name} {wall_type}".casefold():
            continue
        layers = wall.get("MaterialLayers") or []
        observed = [_positive_number(x.get("Thickness_mm")) for x in layers]
        observed_names = [str(x.get("MaterialName") or "Unknown") for x in layers]
        total = _positive_number(wall.get("Width"))
        row = {
            "GlobalId": str(wall.get("GlobalId") or ""),
            "ElementName": name,
            "IFCType": str(wall.get("Type") or ""),
            "Storey": str(wall.get("Storey") or ""),
            "SourcePDFPage": source_page,
            "SourceLabel": str(source_label or ""),
            "SourceQuote": str(source_quote or ""),
            "ObservedLayerCount": len(layers),
            "ObservedLayerNames": " | ".join(observed_names),
            "ObservedLayerThicknesses_mm": " | ".join(
                "" if x is None else f"{x:g}" for x in observed),
            "IFCOverallThickness_mm": total,
            "ConfiguredLayerCount": len(expected),
            "ExpectedLayerLabels": " | ".join(labels),
            "ExpectedLayerThicknesses_mm": " | ".join(f"{x:g}" for x in expected),
            "LayerDifferences_mm": "",
            "ControlledComparisonStatus": "EVIDENCE_INSUFFICIENT",
            "Reason": "",
            "ProjectContractApplicability": "NOT_VERIFIED",
            "RealBuildingCompliance": "NOT_ASSESSABLE",
        }
        if len(layers) != len(expected):
            row["Reason"] = (
                f"IFC declares {len(layers)} material layer(s), but the user-configured "
                f"comparison has {len(expected)}; confirm the wall assembly and layer mapping."
            )
            output.append(row)
            continue
        if any(x is None for x in observed):
            row["Reason"] = "One or more IFC material-layer thicknesses are missing or invalid."
            output.append(row)
            continue
        layer_diffs = [round(observed[i] - expected[i], 4) for i in range(len(expected))]
        row["LayerDifferences_mm"] = " | ".join(f"{x:+g}" for x in layer_diffs)
        if total is not None and abs(sum(observed) - total) > numeric_consistency_tolerance_mm:
            row["ControlledComparisonStatus"] = "REVIEW_REQUIRED"
            row["Reason"] = (
                "Sum of declared IFC material layers conflicts with separate overall-width "
                "evidence. The configured comparison is not interpreted."
            )
        elif all(abs(delta) <= 0.01 for delta in layer_diffs):
            row["ControlledComparisonStatus"] = "MATCHES_CONFIGURED_LAYER_VALUES"
            row["Reason"] = (
                "Declared IFC layer dimensions match the values manually configured from "
                "the selected PDF passage. Applicability remains unverified."
            )
        else:
            row["ControlledComparisonStatus"] = "DIFFERS_FROM_CONFIGURED_LAYER_VALUES"
            changed = [labels[i] for i, delta in enumerate(layer_diffs) if abs(delta) > 0.01]
            row["Reason"] = (
                "Configured dimensions differ for: " + ", ".join(changed) +
                ". This is an experimental numeric difference, not a compliance verdict."
            )
        output.append(row)
    return output
