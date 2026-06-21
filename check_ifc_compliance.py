import ifcopenshell
import ifcopenshell.util.element

def extract_ifc_wall_dimensions(file_path, keyword="Wall"):
    try:
        model = ifcopenshell.open(file_path)
    except Exception:
        return None

    target_element = None
    for element in model.by_type("IfcProduct"):
        element_type = element.is_a()
        element_name = getattr(element, "Name", "") or ""
        if keyword.lower() in element_type.lower() or keyword.lower() in element_name.lower():
            target_element = element
            break

    if not target_element:
        return None

    dimensions = {
        "GlobalId": target_element.GlobalId,
        "Type": target_element.is_a(),
        "Name": getattr(target_element, "Name", "Unnamed Element"),
        "Width": "Unknown",
        "CavityWidth": None,
        "IsExternal": True
    }

    psets = ifcopenshell.util.element.get_psets(target_element)
    for pset_name, pset_data in psets.items():
        if "width" in pset_name.lower() or "quantity" in pset_name.lower():
            for key, val in pset_data.items():
                if "width" in key.lower() or "thickness" in key.lower():
                    if isinstance(val, (int, float)):
                        dimensions["Width"] = val

        if "cavity" in pset_name.lower():
            for key, val in pset_data.items():
                if "width" in key.lower() and isinstance(val, (int, float)):
                    dimensions["CavityWidth"] = val

        if "wallcommon" in pset_name.lower() or "common" in pset_name.lower():
            if "isexternal" in pset_data:
                dimensions["IsExternal"] = bool(pset_data["isexternal"])

    return dimensions
