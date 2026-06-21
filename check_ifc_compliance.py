import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.geom

def extract_ifc_wall_dimensions(file_path, search_keyword="Wall"):
    """
    Exhaustively scans the IFC model for any wall component and extracts its 
    dimensions using a robust multi-tiered parameter and geometric fallback system.
    """
    ifc_file = ifcopenshell.open(file_path)
    target_element = None
    
    # 1. Catch ANY element matching the core keyword
    for element in ifc_file.by_type("IfcProduct"):
        if element.is_a("IfcOpeningElement") or element.is_a("IfcOpening"):
            continue
        if search_keyword.lower() in element.is_a().lower() or search_keyword.lower() in str(getattr(element, "Name", "")).lower():
            target_element = element
            break
            
    if not target_element:
        return None

    # Base dictionary setup
    data = {
        "Type": target_element.is_a(),
        "Name": getattr(target_element, "Name", "Unknown"),
        "GlobalId": target_element.GlobalId,
        "IsExternal": False,
        "Width": "Unknown",
        "CavityWidth": "None/Undefined"
    }

    # Extract Property Sets (Instance & Type layers)
    psets = ifcopenshell.util.element.get_psets(target_element)
    
    # Check for Type Properties (Equivalent to clicking 'Edit Type' in Revit)
    if hasattr(target_element, "IsDefinedBy"):
        for rel in target_element.IsDefinedBy:
            if rel.is_a("IfcRelDefinesByType"):
                type_psets = ifcopenshell.util.element.get_psets(rel.RelatingType)
                for t_name, t_props in type_psets.items():
                    if t_name not in psets:
                        psets[t_name] = t_props

    # Flatten properties to search blindly for dimensions
    flat_props = {}
    for pset_name, props in psets.items():
        for k, v in props.items():
            flat_props[k.lower()] = v
            if "isexternal" in k.lower() and v is True:
                data["IsExternal"] = True

    # Tier 1: Look for explicit textual parameters anywhere in the metadata
    width_keywords = ["width", "thickness", "nominalthickness", "wallthickness", "overallthickness"]
    for kw in width_keywords:
        if kw in flat_props and flat_props[kw] not in [None, "", "Unknown"]:
            try:
                val = float(flat_props[kw])
                if val > 0:
                    data["Width"] = val
                    break
            except (ValueError, TypeError):
                continue

    # Tier 2: Look for cavity specific parameters
    cavity_keywords = ["cavity", "cavitywidth", "airgap", "voidwidth"]
    for ck in cavity_keywords:
        if ck in flat_props and flat_props[ck] not in [None, ""]:
            data["CavityWidth"] = flat_props[ck]
            break

    # Tier 3: GEOMETRIC FALLBACK
    # If parameters are completely blank/missing, compute the physical bounding box
    if data["Width"] == "Unknown":
        try:
            settings = ifcopenshell.geom.settings()
            settings.set(settings.USE_WORLD_COORDINATES, True)
            shape = ifcopenshell.geom.create_shape(settings, target_element)
            
            # Extract raw vertices matrix
            verts = shape.geometry.verts
            grouped_verts = [verts[i:i+3] for i in range(0, len(verts), 3)]
            
            if grouped_verts:
                x_coords = [v[0] for v in grouped_verts]
                y_coords = [v[1] for v in grouped_verts]
                z_coords = [v[2] for v in grouped_verts]
                
                # Calculate bounding box dimensions
                dx = max(x_coords) - min(x_coords)
                dy = max(y_coords) - min(y_coords)
                
                # The smaller horizontal dimension represents the structural wall thickness
                computed_thickness = min(dx, dy) * 1000.0  # Convert to mm
                if computed_thickness > 0:
                    data["Width"] = round(computed_thickness, 2)
        except Exception:
            pass  # Fallback gracefully to "Unknown" if geometry engine fails

    return data
