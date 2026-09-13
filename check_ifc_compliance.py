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

    # IFC classes that are routinely NAMED after the thing they're mounted on
    # or adjacent to (e.g. "Wall Lamp", "Toilet-Commercial-Wall-3D",
    # "Railing:Pipe-Wall Mount", "Door-Curtain-Wall-Double-Storefront").
    # A name-only match on a generic keyword like "Wall" pulls these in even
    # though they are fixtures/openings, not structural wall elements. We
    # still trust a match on the IFC *class* itself (e.g. IfcCurtainWall),
    # since that's an unambiguous structural signal - this list only blocks
    # the name-substring path for classes that are known false-positive
    # sources.
    NON_STRUCTURAL_EXCLUDE_TYPES = {
        "IfcDoor", "IfcWindow",
        "IfcFurnishingElement", "IfcFurniture",
        "IfcFlowTerminal", "IfcSanitaryTerminal",
        "IfcRailing", "IfcLightFixture",
        "IfcProxy", "IfcBuildingElementProxy",
    }

    # Gather ALL candidate elements (IfcWall, IfcWallStandardCase, IfcCurtainWall, etc.)
    for element in ifc_file.by_type("IfcProduct"):
        if element.is_a("IfcOpeningElement") or element.is_a("IfcOpening"):
            continue

        el_type = element.is_a()
        el_name = str(getattr(element, "Name", ""))

        type_match = search_keyword.lower() in el_type.lower()
        name_match = search_keyword.lower() in el_name.lower()

        if type_match:
            all_matched_elements.append(element)
        elif name_match and el_type not in NON_STRUCTURAL_EXCLUDE_TYPES:
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

        # Extract Spatial Zone / Storey Level.
        # Spatial containment (element -> storey) is carried by
        # IfcRelContainedInSpatialStructure, exposed on the element via the
        # inverse attribute `ContainedInStructure`. `Decomposes` carries
        # IfcRelAggregates instead (e.g. a wall part belonging to a curtain
        # wall) and will essentially never contain a spatial-structure
        # relationship, so it was never matching before.
        if hasattr(target_element, "ContainedInStructure"):
            for rel in target_element.ContainedInStructure:
                if rel.is_a("IfcRelContainedInSpatialStructure"):
                    data["Storey"] = getattr(
                        rel.RelatingStructure, "Name", "Unknown"
                    )
                    break

        # Fallback: if the element itself has no direct spatial containment
        # (e.g. it's an aggregate part), inherit the storey from its
        # decomposition parent.
        if data["Storey"] == "Unknown" and hasattr(target_element, "Decomposes"):
            for rel in target_element.Decomposes:
                if rel.is_a("IfcRelAggregates"):
                    parent = getattr(rel, "RelatingObject", None)
                    if parent is not None and hasattr(parent, "ContainedInStructure"):
                        for prel in parent.ContainedInStructure:
                            if prel.is_a("IfcRelContainedInSpatialStructure"):
                                data["Storey"] = getattr(
                                    prel.RelatingStructure, "Name", "Unknown"
                                )
                                break
                if data["Storey"] != "Unknown":
                    break

        # Extract Associated Materials (IfcMaterial / IfcMaterialLayerSet).
        # While walking the layers, also remember the thickness of any layer
        # that looks like a cavity/air gap - this feeds a cavity-width
        # fallback below for the (common) case where no explicit
        # "CavityWidth"-style property set exists, even though the material
        # layer breakdown clearly shows one (e.g. "Cavity Fill (150.02mm)").
        cavity_thickness_from_materials = None
        layer_thickness_sum = 0.0
        has_layer_set = False
        try:
            mats = ifcopenshell.util.element.get_material(target_element)
            if mats:
                if hasattr(mats, "ForLayerSet"):
                    has_layer_set = True
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
                        layer_thickness_sum += thick

                        if (
                            cavity_thickness_from_materials is None
                            and mat_name
                            and ("cavity" in mat_name.lower() or mat_name.lower() == "air")
                        ):
                            cavity_thickness_from_materials = thick
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

        # Tier 0 (highest priority): sum of material layer thicknesses.
        # This is the most trustworthy width source we have - it's the
        # actual assembly build-up (brick + cavity + block + board, etc.)
        # that we're already extracting for the Materials list, rather than
        # a loosely name-matched property. On the models checked so far this
        # summed value matched the "true" wall thickness almost exactly
        # (within rounding), whereas the generic property-sweep below can
        # pick up an unrelated same-named property (e.g. a panel/module
        # width on a storefront-style assembly) and return something wildly
        # wrong. Only trust this when there's an actual layer set AND the
        # sum is a sane, non-zero number.
        if has_layer_set and layer_thickness_sum > 0:
            data["Width"] = round(layer_thickness_sum, 2)

        # Fallback 1: Deep Metadata Attribute Sweep.
        # More specific keys are tried before the bare "width" key, since a
        # generic "Width" property (especially one merged in from the
        # element's Type parameters) is the most likely to actually
        # describe something other than wall thickness - e.g. a panel or
        # module width in a curtain-wall-style assembly.
        width_keywords = [
            "wallthickness",
            "overallthickness",
            "nominalthickness",
            "thickness/width",
            "thickness",
            "width",
        ]
        if data["Width"] == "Unknown":
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

        # Fallback: no explicit cavity property, but the material layer
        # breakdown already showed a cavity/air layer - use its thickness
        # rather than reporting "None/Undefined" when the data is right
        # there in the materials list.
        if data["CavityWidth"] == "None/Undefined" and cavity_thickness_from_materials is not None:
            data["CavityWidth"] = f"{cavity_thickness_from_materials} (from material layer)"

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

        # Fallback 3: Direct 3D Bounding Box Geometry Extrusion Processing.
        # This assumes an axis-aligned, roughly rectangular element where the
        # shortest horizontal bounding-box side approximates wall thickness.
        # That assumption breaks for L-shaped runs, curved segments, or
        # walls at odd angles - on those elements this fallback can return
        # something closer to the wall's *length* than its thickness.
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

        # Universal sanity check - applied regardless of which tier above
        # produced the value, since any of them (a mismatched property, a
        # name-regex false hit, or a non-rectangular bounding box) can
        # silently return something implausible. Flag rather than discard,
        # so the raw number is still visible for manual review.
        MAX_PLAUSIBLE_THICKNESS_MM = 600.0  # generous; even thick masonry cavity walls fall well under this
        if isinstance(data["Width"], (int, float)) and data["Width"] > MAX_PLAUSIBLE_THICKNESS_MM:
            data["Width"] = (
                f"Unreliable ({data['Width']}mm - exceeds plausible wall"
                " thickness; verify source property/geometry)"
            )

        extracted_walls_data.append(data)

    return extracted_walls_data
