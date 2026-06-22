import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.geom
import re

def extract_ifc_wall_dimensions(file_path, search_keyword="Wall"):
    """
    Exhaustively scans the IFC model for any component matching the keyword
    and extracts its dimensions using a 4-tier fallback framework.
    """
    try:
        ifc_file = ifcopenshell.open(file_path)
    except Exception as e:
        print(f"Error opening IFC file: {e}")
        return None

    target_element = None
    
    # Tier 1: Gather ALL candidate products
    # Normalizes search to catch IfcWall, IfcWallStandardCase, IfcCurtainWall, etc.
    for element in ifc_file.by_type("IfcProduct"):
        if element.is_a("IfcOpeningElement") or element.is_a("IfcOpening"):
            continue
        
        el_type = element.is_a()
        el_name = str(getattr(element, "Name", ""))
        
        if search_keyword.lower() in el_type.lower() or search_keyword.lower() in el_name.lower():
            target_element = element
            break
            
    if not target_element:
        return None

    # Base payload structure
    data = {
        "Type": target_element.is_a(),
        "Name": getattr(target_element, "Name", "Unknown"),
        "GlobalId": target_element.GlobalId,
        "IsExternal": False,
        "Width": "Unknown",
        "CavityWidth": "None/Undefined"
    }

    # Extract Property Sets from the Instance Layer
    psets = ifcopenshell.util.element.get_psets(target_element)
    
    # Extract Property Sets from the Type Layer (Revit's 'Edit Type')
    if hasattr(target_element, "IsDefinedBy"):
        for rel in target_element.IsDefinedBy:
            if rel.is_a("IfcRelDefinesByType"):
                type_element = rel.RelatingType
                if type_element:
                    type_psets = ifcopenshell.util.element.get_psets(type_element)
                    for t_name, t_props in type_psets.items():
                        # Consolidate type parameters if not shadowed by instance parameters
                        if t_name not in psets:
                            psets[t_name] = t_props
                        else:
                            for k, v in t_props.items():
                                if k not in psets[t_name]:
                                    psets[t_name][k] = v

    # Flatten all properties into lowercase keys for a blind keyword scan
    flat_props = {}
    for pset_name, props in psets.items():
        for k, v in props.items():
            flat_props[k.lower()] = v
            if "isexternal" in k.lower() and v is True:
                data["IsExternal"] = True

    # Fallback Path 1: Deep Metadata Attribute Sweep
    width_keywords = ["width", "thickness", "nominalthickness", "wallthickness", "overallthickness", "thickness/width"]
    for kw in width_keywords:
        if kw in flat_props and flat_props[kw] not in [None, "", "Unknown"]:
            try:
                val = float(flat_props[kw])
                if val > 0:
                    data["Width"] = val
                    break
            except (ValueError, TypeError):
                continue

    # Extract Cavity Data if explicitly written
    cavity_keywords = ["cavity", "cavitywidth", "airgap", "voidwidth"]
    for ck in cavity_keywords:
        if ck in flat_props and flat_props[ck] not in [None, ""]:
            data["CavityWidth"] = flat_props[ck]
            break

    # Fallback Path 2: Exact String Regex Mining (Matches "SIP 202mm Wall")
    if data["Width"] == "Unknown":
        search_string = f"{data['Name']} {data['Type']}"
        # Matches patterns like '202mm', '202 mm', '352mm'
        match = re.search(r'(\d+(?:\.\d+)?)\s*mm', search_string, re.IGNORECASE)
        if match:
            try:
                extracted_width = float(match.group(1))
                if extracted_width > 0:
                    data["Width"] = extracted_width
            except (ValueError, TypeError):
                pass

    # Fallback Path 3: Direct 3D Bounding Box Extrusion Processing
    if data["Width"] == "Unknown":
        try:
            settings = ifcopenshell.geom.settings()
            settings.set(settings.USE_WORLD_COORDINATES, True)
            shape = ifcopenshell.geom.create_shape(settings, target_element)
            
            verts = shape.geometry.verts
            grouped_verts = [verts[i:i+3] for i in range(0, len(verts), 3)]
            
            if grouped_verts:
                x_coords = [v[0] for v in grouped_verts]
                y_coords = [v[1] for v in grouped_verts]
                
                dx = max(x_coords) - min(x_coords)
                dy = max(y_coords) - min(y_coords)
                
                # The minor horizontal delta vector isolates the physical cross-sectional width
                computed_thickness = min(dx, dy) * 1000.0  # Convert meters to millimeters
                if computed_thickness > 0:
                    data["Width"] = round(computed_thickness, 2)
        except Exception:
            pass 

    return data
