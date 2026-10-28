"""IFC2x3 / IFC4 element evidence extraction, independent of project names.

Never infer certified dimensions from a filename, element name, or bounding box.
Declared IFC units are converted to mm consistently. Incompatible or uncertain
values remain evidence for review, not compliance decisions.
"""
from __future__ import annotations
import re
from collections import defaultdict
import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.unit

ALIASES = {
    "wall": ("IfcWall", "IfcCurtainWall"), "beam": ("IfcBeam",),
    "slab": ("IfcSlab",), "column": ("IfcColumn",),
    "door": ("IfcDoor",), "window": ("IfcWindow",),
    "roof": ("IfcRoof",), "stair": ("IfcStair", "IfcStairFlight"),
    "ramp": ("IfcRamp", "IfcRampFlight"), "footing": ("IfcFooting",),
    "pile": ("IfcPile",), "member": ("IfcMember",),
    "plate": ("IfcPlate",), "railing": ("IfcRailing",),
    "covering": ("IfcCovering",), "pipe": ("IfcPipeSegment",),
    "duct": ("IfcDuctSegment",),
}
ALL_ALIASES = {"all model elements", "all elements", "all", "*", "all sample types"}


def parse_component_filter(query):
    tokens = [x.strip() for x in str(query or "all model elements").split(",") if x.strip()]
    if not tokens or any(t.casefold() in ALL_ALIASES for t in tokens):
        return ("all", ())
    classes = []
    for raw in tokens:
        term = raw.casefold()
        if term in ALIASES:
            classes.extend(ALIASES[term])
        elif re.fullmatch(r"Ifc[A-Za-z0-9_]+", raw, re.I):
            classes.append("Ifc" + raw[3:])
        else:
            raise ValueError(f"Unknown IFC class/category '{raw}'. Try 'All model elements' or 'IfcWall,IfcBeam'.")
    return ("classes", tuple(dict.fromkeys(classes)))


def _select_elements(model, filter_query):
    mode, classes = parse_component_filter(filter_query)
    # IFC's own class hierarchy does not depend on model authoring software.
    result = []
    for entity in model.by_type("IfcElement"):
        if entity.is_a("IfcFeatureElement") or not getattr(entity, "GlobalId", None):
            continue
        if mode == "all" or any(entity.is_a(c) for c in classes):
            result.append(entity)
    return sorted(result, key=lambda e: str(e.GlobalId))


def _mm_per_native_unit(model):
    """IfcOpenShell's standard IFC-unit conversion handles SI and feet/inches."""
    scale = float(ifcopenshell.util.unit.calculate_unit_scale(model)) * 1000.0
    if not (0 < scale < 1e9):
        raise ValueError("Invalid IFC project LENGTHUNIT; cannot safely convert to mm.")
    return scale


def _length(value, scale):
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
        return round(n * scale, 4) if 0 < n < float("inf") else None
    except (TypeError, ValueError):
        return None


def _boolean(value):
    if hasattr(value, "wrappedValue"):
        value = value.wrappedValue
    if isinstance(value, (bool, int)):
        return bool(value)
    if isinstance(value, str) and value.strip().casefold() in {"true", "yes", "1", "false", "no", "0"}:
        return value.strip().casefold() in {"true", "yes", "1"}
    return None


def _storey(element):
    visited = set()
    pending = [element]
    while pending:
        current = pending.pop()
        ident = current.id()
        if ident in visited:
            continue
        visited.add(ident)
        for rel in getattr(current, "ContainedInStructure", ()) or ():
            s = getattr(rel, "RelatingStructure", None)
            if s is not None:
                return getattr(s, "Name", "Unknown") or "Unknown"
        for rel in getattr(current, "Decomposes", ()) or ():
            parent = getattr(rel, "RelatingObject", None)
            if parent is not None:
                pending.append(parent)
    return "Unknown"


def _materials(element, scale):
    names, sums, cavity = [], [], None
    mat = ifcopenshell.util.element.get_material(element, should_skip_usage=False)
    if mat is None:
        return names, sums, cavity
    layer_set = getattr(mat, "ForLayerSet", None)
    if layer_set is None and mat.is_a("IfcMaterialLayerSet"):
        layer_set = mat
    if layer_set is not None:
        total = 0.0
        for layer in getattr(layer_set, "MaterialLayers", ()) or ():
            thick = _length(getattr(layer, "LayerThickness", None), scale)
            name = getattr(getattr(layer, "Material", None), "Name", None) or "Unnamed material"
            names.append(f"{name} ({thick} mm)" if thick is not None else name)
            if thick is not None:
                total += thick
            if cavity is None and thick is not None and any(x in name.casefold() for x in ("cavity", "air gap", "airspace", "hohlraum", "luftschicht")):
                cavity = thick
        if total > 0:
            sums.append((round(total, 3), "IfcMaterialLayerSet total"))
        return names, sums, cavity
    if mat.is_a("IfcMaterial"):
        return [getattr(mat, "Name", "Unnamed material") or "Unnamed material"], sums, cavity
    for attribute in ("Materials", "MaterialConstituents", "MaterialProfiles"):
        for item in (getattr(mat, attribute, None) or []):
            material = getattr(item, "Material", item)
            name = getattr(material, "Name", "") or getattr(item, "Name", "")
            if name:
                names.append(str(name))
    return names, sums, cavity



def _material_layers(element, scale):
    """Return structural IFC layer records, not estimates from wall names.

    For a multi-layer cavity wall this is the evidence needed to check each
    leaf independently. A generic single material is NOT a three-part
    cavity-wall construction. Layer sequence is preserved as authored, but
    does not prove which face is external without a verified orientation.
    """
    material = ifcopenshell.util.element.get_material(
        element, should_skip_usage=False)
    if material is None:
        return []
    layer_set = getattr(material, "ForLayerSet", None)
    if layer_set is None and material.is_a("IfcMaterialLayerSet"):
        layer_set = material
    if layer_set is None:
        return []
    records = []
    for i, layer in enumerate(getattr(layer_set, "MaterialLayers", ()) or (), 1):
        name = getattr(getattr(layer, "Material", None), "Name", None) or "Unnamed material"
        records.append({
            "LayerIndex": i,
            "MaterialName": str(name),
            "Thickness_mm": _length(getattr(layer, "LayerThickness", None), scale),
            "EvidenceSource": "IfcMaterialLayerSet.MaterialLayers",
        })
    return records


def _property_evidence(element, scale):
    psets = ifcopenshell.util.element.get_psets(element) or {}
    values = defaultdict(list)
    ext = None
    for section, props in psets.items():
        if not isinstance(props, dict):
            continue
        for key, value in props.items():
            if isinstance(value, (list, tuple, dict)) or value is None:
                continue
            lname = str(key).casefold().replace(" ", "").replace("_", "")
            if lname == "isexternal":
                parsed = _boolean(value)
                if parsed is not None:
                    ext = parsed
            if lname in {"overallthickness", "wallthickness", "nominalthickness", "thickness", "width"}:
                # A generic Width in unrelated property sets can mean panel width, NOT wall thickness.
                if lname == "width" and "qto_wall" not in section.casefold():
                    continue
                size = _length(value, scale)
                if size is not None:
                    values["Thickness"].append((size, f"IFC {section}.{key}"))
            if lname in {"height", "overallheight", "overallwidth", "length", "depth"}:
                size = _length(value, scale)
                if size is not None:
                    values[str(key)].append((size, f"IFC {section}.{key}"))
    return values, ext


def _resolve_thickness(candidates):
    """Disagreeing exported quantities cause review, never an arbitrary PASS."""
    if not candidates:
        return ("Unknown", "No explicit comparable IFC wall thickness", "MISSING", [])
    # Layer sum is the primary width measurement; explicit IFC wall quantities
    # can corroborate it. No name parsing or bounding-box guessing.
    first = candidates[0][0]
    distinct = {round(value, 1) for value, _ in candidates}
    if len(distinct) > 1:
        return ("Unknown", "Conflicting IFC thickness sources: manual review", "CONFLICTING", [f"{v:g} mm [{s}]" for v,s in candidates])
    return (round(first, 2), candidates[0][1], "DECLARED", [f"{v:g} mm [{s}]" for v,s in candidates])


def extract_all_ifc_wall_dimensions(file_path, search_keyword="All model elements"):
    """Legacy-compatible API returning evidence for any IFC element class.

    A wall thickness is comparable only when based on declared model evidence;
    other classes get independent size observations, never a wall-thickness claim.
    """
    model = ifcopenshell.open(file_path)  # Fail visibly on invalid IFC.
    scale = _mm_per_native_unit(model)
    elements = _select_elements(model, search_keyword)
    out = []
    for el in elements:
        typ = el.is_a()
        warnings = []
        try:
            materials, layer_candidates, cavity = _materials(el, scale)
        except Exception as ex:
            materials, layer_candidates, cavity = [], [], None
            warnings.append("Material association extraction failed: " + type(ex).__name__)
        try:
            layer_details = _material_layers(el, scale) if el.is_a("IfcWall") else []
        except Exception as ex:
            layer_details = []
            warnings.append("Structured wall material layers unavailable: " + type(ex).__name__)
        try:
            props, external = _property_evidence(el, scale)
        except Exception as ex:
            props, external = {}, None
            warnings.append("Property extraction failed: " + type(ex).__name__)
        try:
            storey = _storey(el)
        except Exception as ex:
            storey = "Unknown"
            warnings.append("Spatial containment extraction failed: " + type(ex).__name__)
        wall = el.is_a("IfcWall")
        thickness_candidates = layer_candidates + props.get("Thickness", []) if wall else []
        width, source, quality, sources = _resolve_thickness(thickness_candidates) if wall else (
            "Unknown", "Not a wall-thickness element", "UNVERIFIED_NON_WALL", [])
        # Native IfcDoor and IfcWindow attributes are standard across IFC2x3/IFC4.
        dimensions = {}
        for attr in ("OverallWidth", "OverallHeight"):
            observed = _length(getattr(el, attr, None), scale)
            if observed is not None:
                dimensions[attr + "_mm"] = observed
        for k, observed in props.items():
            if k != "Thickness" and observed:
                dimensions[k + "_mm"] = observed[0][0]
        out.append({
            "Type": typ, "Name": getattr(el, "Name", "") or "Unnamed element",
            "GlobalId": str(el.GlobalId), "Storey": storey,
            "IsExternal": external, "Width": width, "WidthSource": source,
            "MeasurementQuality": quality, "ThicknessCandidates": sources,
            "CavityWidth": cavity if cavity is not None else "Not established",
            "Materials": materials, "MaterialLayers": layer_details,
            "Dimensions_mm": dimensions,
            "IFCSchema": model.schema, "IFC_mm_per_length_unit": scale,
            "ExtractionWarnings": "; ".join(warnings),
        })
    return out
