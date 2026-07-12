import re
import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element


def extract_all_ifc_wall_dimensions(file_path, search_keyword="Wall"):
    """Exhaustively scans the IFC model for ALL components matching the keyword

    and extracts their dimensions, materials, and spatial info using a 4-tier
    fallback framework.
    """
    try:
        ifc_file = ifcopenshell.open(file_path)
    except Exception as e:
        print(f"Error opening IFC file: {e}")
        return []

    # Detect project length units to prevent feet/meters export errors
    unit_scale_to_mm = 1000.0  # Default assume meters -> mm
    try:
        for unit in ifc_file.by_type("IfcUnitAssignment")[0].Units:
            if getattr(unit, "UnitType", "") == "LENGTHUNIT":
                prefix = str(getattr(unit, "Prefix", "")).upper()
                name = str(getattr(unit, "Name", "")).upper()
                if "FOOT" in name or "FEET" in name:
                    unit_scale_to_mm = 304.8
                elif "INCH" in name:
                    unit_scale_to_mm = 25.4
                elif "MILLI" in prefix or "MILLIMETRE" in name:
                    unit_scale_to_mm = 1.0
                elif "CENTI" in prefix or "CENTIMETRE" in name:
                    unit_scale_to_mm = 10.0
                elif "METRE" in name:
                    unit_scale_to_mm = 1000.0
    except Exception:
        unit_scale_to_mm = 1000.0

    all_matched_elements = []

    # Gather ALL candidate elements (IfcWall, IfcWallStandardCase, IfcCurtainWall, etc.)
    for element in ifc_file.by_type("IfcProduct"):
        if element.is_a("IfcOpeningElement") or element.is_a("IfcOpening"):
            continue

        el_type = element.is_a()
        el_name = str(getattr(element, "Name", ""))

        # Check if the search keyword exists in either the IFC Class or the Element Name
        if (
            search_keyword.lower() in el_type.lower()
            or search_keyword.lower() in el_name.lower()
        ):
            all_matched_elements.append(element)

    if not all_matched_elements:
        return []

    extracted_walls_data = []

    for target_element in all_matched_elements:
        data = {
            "Type": target_element.is_a(),
            "Name": getattr(target_element, "Name", "Unknown"),
            "GlobalId": target_element.GlobalId,
            "IsExternal": False,
            "Width": "Unknown",
            "CavityWidth": "None/Undefined",
            "Materials": [],
            "Storey": "Unknown",
        }

        # Extract Spatial Zone / Storey Level
        if hasattr(target_element, "Decomposes"):
            for rel in target_element.Decomposes:
                if rel.is_a("IfcRelContainedInSpatialStructure"):
                    data["Storey"] = getattr(
                        rel.RelatingStructure, "Name", "Unknown"
                    )

        # Extract Associated Materials (IfcMaterial / IfcMaterialLayerSet)
        try:
            mats = ifcopenshell.util.element.get_material(target_element)
            if mats:
                if hasattr(mats, "ForLayerSet"):
                    for layer in mats.ForLayerSet.MaterialLayers:
                        mat_name = getattr(
                            layer.Material, "Name", "Unnamed Layer"
                        )
                        thick = (
                            round(layer.LayerThickness * unit_scale_to_mm, 2)
                            if layer.LayerThickness
                            else 0
                        )
                        data["Materials"].append(f"{mat_name} ({thick}mm)")
                elif hasattr(mats, "Materials"):
                    for m in mats.Materials:
                        data["Materials"].append(
                            getattr(m, "Name", "Unnamed Material")
                        )
                else:
                    data["Materials"].append(
                        getattr(mats, "Name", "Unnamed Material")
                    )
        except Exception:
            pass

        # Extract Property Sets from Instance Layer
        psets = ifcopenshell.util.element.get_psets(target_element)

        # Extract Property Sets from Type Layer
        if hasattr(target_element, "IsDefinedBy"):
            for rel in target_element.IsDefinedBy:
                if rel.is_a("IfcRelDefinesByType"):
                    type_element = rel.RelatingType
                    if type_element:
                        type_psets = ifcopenshell.util.element.get_psets(
                            type_element
                        )
                        for t_name, t_props in type_psets.items():
                            if t_name not in psets:
                                psets[t_name] = t_props
                            else:
                                for k, v in t_props.items():
                                    if k not in psets[t_name]:
                                        psets[t_name][k] = v

        # Flatten all properties into lowercase keys
        flat_props = {}
        for pset_name, props in psets.items():
            for k, v in props.items():
                flat_props[k.lower()] = v
                if "isexternal" in k.lower() and v is True:
                    data["IsExternal"] = True

        # Fallback 1: Deep Metadata Attribute Sweep
        width_keywords = [
            "width",
            "thickness",
            "nominalthickness",
            "wallthickness",
            "overallthickness",
            "thickness/width",
        ]
        for kw in width_keywords:
            if kw in flat_props and flat_props[kw] not in [
                None,
                "",
                "Unknown",
            ]:
                try:
                    val = float(flat_props[kw])
                    # Apply unit conversion scale if needed
                    if val < 5.0 and unit_scale_to_mm != 1.0:
                        val = val * unit_scale_to_mm
                    if val > 0:
                        data["Width"] = round(val, 2)
                        break
                except (ValueError, TypeError):
                    continue

        # Extract Cavity Data
        cavity_keywords = ["cavity", "cavitywidth", "airgap", "voidwidth"]
        for ck in cavity_keywords:
            if ck in flat_props and flat_props[ck] not in [None, ""]:
                data["CavityWidth"] = flat_props[ck]
                break

        # Fallback 2: Name/Type Regex Mining
        if data["Width"] == "Unknown":
            search_string = f"{data['Name']} {data['Type']}"
            match = re.search(
                r"(\d+(?:\.\d+)?)\s*mm", search_string, re.IGNORECASE
            )
            if match:
                try:
                    extracted_width = float(match.group(1))
                    if extracted_width > 0:
                        data["Width"] = extracted_width
                except (ValueError, TypeError):
                    pass

        # Fallback 3: Direct 3D Bounding Box Geometry Extrusion Processing
        if data["Width"] == "Unknown":
            try:
                settings = ifcopenshell.geom.settings()
                settings.set(settings.USE_WORLD_COORDINATES, True)
                shape = ifcopenshell.geom.create_shape(
                    settings, target_element
                )

                verts = shape.geometry.verts
                grouped_verts = [
                    verts[i : i + 3] for i in range(0, len(verts), 3)
                ]

                if grouped_verts:
                    x_coords = [v[0] for v in grouped_verts]
                    y_coords = [v[1] for v in grouped_verts]

                    dx = max(x_coords) - min(x_coords)
                    dy = max(y_coords) - min(y_coords)

                    # Compute thickness using actual model scale factors
                    computed_thickness = min(dx, dy) * unit_scale_to_mm
                    if computed_thickness > 0:
                        data["Width"] = round(computed_thickness, 2)
            except Exception:
                pass

        extracted_walls_data.append(data)

    return extracted_walls_data
