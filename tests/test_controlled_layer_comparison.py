from controlled_layer_comparison import (
    parse_layer_configuration,
    compare_wall_layers_to_configured_rule,
)
import pytest


def wall(gid, dims, names=None, width=None, name="Test wall", typ="IfcWallStandardCase"):
    names = names or [f"Material {i}" for i in range(1, len(dims)+1)]
    return {
        "GlobalId": gid, "Name": name, "Type": typ,
        "Width": sum(dims) if width is None else width,
        "MaterialLayers": [
            {"LayerIndex": i, "MaterialName": names[i-1], "Thickness_mm": dims[i-1]}
            for i in range(1, len(dims)+1)
        ],
    }


def test_configuration_accepts_arbitrary_project_specific_layers_without_hardcoded_values():
    rule = parse_layer_configuration("panel, insulation, board", "17, 83.5, 12.5")
    assert [x["ExpectedThickness_mm"] for x in rule] == [17, 83.5, 12.5]
    rows = compare_wall_layers_to_configured_rule(
        [wall("A", [17, 83.5, 12.5])], rule,
        source_page=7, source_quote="Example source requirement",
    )
    assert rows[0]["ControlledComparisonStatus"] == "MATCHES_CONFIGURED_LAYER_VALUES"
    assert rows[0]["RealBuildingCompliance"] == "NOT_ASSESSABLE"
    assert rows[0]["SourcePDFPage"] == 7


def test_controlled_changed_layer_is_detected_without_claiming_compliance_failure():
    rule = parse_layer_configuration("leaf, cavity, leaf", "102, 150, 100")
    baseline = wall("A", [102, 150, 100])
    changed = wall("B", [102, 140, 100])
    rows = compare_wall_layers_to_configured_rule([baseline, changed], rule)
    assert rows[0]["ControlledComparisonStatus"] == "MATCHES_CONFIGURED_LAYER_VALUES"
    assert rows[1]["ControlledComparisonStatus"] == "DIFFERS_FROM_CONFIGURED_LAYER_VALUES"
    assert rows[1]["LayerDifferences_mm"] == "+0 | -10 | +0"
    assert rows[1]["RealBuildingCompliance"] == "NOT_ASSESSABLE"


def test_one_layer_or_missing_measurement_is_insufficient_not_false_failure():
    rule = parse_layer_configuration("outer, cavity, inner", "102, 150, 100")
    one_layer = wall("A", [352], names=["Generic"])
    missing = wall("B", [102, 150, 100])
    missing["MaterialLayers"][1]["Thickness_mm"] = None
    rows = compare_wall_layers_to_configured_rule([one_layer, missing], rule)
    assert rows[0]["ControlledComparisonStatus"] == "EVIDENCE_INSUFFICIENT"
    assert rows[1]["ControlledComparisonStatus"] == "EVIDENCE_INSUFFICIENT"


def test_inconsistent_overall_width_requires_review():
    rule = parse_layer_configuration("a, b", "50, 50")
    rows = compare_wall_layers_to_configured_rule([wall("A", [50, 50], width=120)], rule)
    assert rows[0]["ControlledComparisonStatus"] == "REVIEW_REQUIRED"


def test_filter_excludes_unselected_wall_types_and_nonwall_classes():
    rule = parse_layer_configuration("a", "100")
    walls = [
        wall("A", [100], name="External masonry"),
        wall("B", [100], name="Drywall partition"),
        wall("C", [100], typ="IfcCurtainWall"),
    ]
    rows = compare_wall_layers_to_configured_rule(walls, rule, name_or_type_filter="masonry")
    assert [r["GlobalId"] for r in rows] == ["A"]


@pytest.mark.parametrize("labels,values", [
    ("a,b", "10"), ("a", "10,20"), ("a", "0"), ("a", "-5"), ("", "10"),
    ("a", "nan"), ("a", "inf"),
])
def test_invalid_rule_inputs_are_rejected(labels, values):
    with pytest.raises(ValueError):
        parse_layer_configuration(labels, values)
