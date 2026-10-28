"""Evidence-first requirement -> IFC element candidate ranking.

This is an interpretable retrieval stage, NOT a compliance decision. It treats
nominal cavity-wall assemblies as different physical quantities from a single
IFC material-layer total unless full assembly composition is established.
The same candidate list can guide bounded Neo4j retrieval / LLM context.
"""
import math
import re

_MATERIAL_PARTS = ("brick", "block", "cavity")


def _numeric(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _material_components(wall):
    names = [str(s).casefold() for s in wall.get("Materials", []) or []]
    joined = " ".join(names)
    return {part: bool(re.search(r"\b" + part + r"\w*\b", joined))
            for part in _MATERIAL_PARTS}


def _requirements(assembly_rows):
    """Preserve source provenance for each PDF assembly without assuming scope."""
    for i, a in enumerate(assembly_rows):
        value = _numeric(a.get("AssemblyThickness_mm"))
        if value is None:
            continue
        yield {
            "RequirementID": f"PDF-P{a['PDFPage']}-A{i+1}",
            "PDFPage": a["PDFPage"],
            "PDFNominalAssembly_mm": value,
            "ClauseText": str(a.get("QuotedLine") or ""),
            "Context": str(a.get("SurroundingText") or ""),
            "SourceMeaning": "nominal cavity-wall assembly",
        }


def rank_element_requirement_candidates(walls, assembly_rows, *,
                                        max_pairs=80, numeric_window_mm=15.0):
    """Rank plausible wall-to-assembly evidence pairs; never issue verdicts.

    The numeric window is a *retrieval hint*, not building tolerance. A wall
    very far from a nominal assembly and with no evidence of its constituent
    materials is NOT a credible candidate for this particular requirement.
    Different PDF requirements get fair representation under max_pairs.
    """
    if max_pairs < 0 or not math.isfinite(numeric_window_mm) or numeric_window_mm < 0:
        raise ValueError("Candidate budget and discovery window must be nonnegative")
    requirements = list(_requirements(assembly_rows))
    pools = []
    for requirement in requirements:
        context = (requirement["ClauseText"] + " " + requirement["Context"]).casefold()
        external_clause = bool(re.search(r"\bexternal\s+(?:masonry\s+)?walls?\b", context))
        below_dpc = bool(re.search(r"\bbelow\s+(?:the\s+)?(?:damp\s+proof\s+course|dpc)\b", context))
        above_dpc = bool(re.search(r"\babove\s+(?:the\s+)?(?:damp\s+proof\s+course|dpc)\b", context))
        pairs = []
        for e in walls:
            if not str(e.get("Type") or "").startswith("IfcWall"):
                continue
            gid = str(e.get("GlobalId") or "")
            if not gid:
                continue
            width = _numeric(e.get("Width"))
            distance = abs(width - requirement["PDFNominalAssembly_mm"]) if width is not None else None
            materials = _material_components(e)
            parts_present = all(materials.values())
            near = distance is not None and distance <= numeric_window_mm
            # Do not exhaust the candidate quota with generic 50/100/250 mm
            # walls just because they are marked external in IFC.
            if not near and not parts_present:
                continue
            external = e.get("IsExternal")
            reasons = []
            score = 0
            if near:
                score += 4
                reasons.append(f"Numerical proximity {distance:.4f} mm (discovery, NOT tolerance)")
            elif distance is not None:
                reasons.append("Full-material assembly cue, but numeric thickness is distant")
            else:
                reasons.append("Full-material assembly cue, but IFC total thickness unavailable")
            if external_clause and external is True:
                score += 2
                reasons.append("IsExternal=True is a category cue; not proof of contractual scope")
            elif external_clause and external is False:
                score -= 4
                reasons.append("CONFLICT: IFC wall marked internal")
            elif external_clause:
                reasons.append("External/internal scope not established")
            if parts_present:
                score += 3
                reasons.append("Brick/cavity/block names present; assembly layer structure still unverified")
            else:
                reasons.append("Full brick+cavity+block assembly NOT evidenced by material names")
            if below_dpc or above_dpc:
                reasons.append("DPC level and house/storey applicability remain unverified")
            if external_clause and external is False:
                status = "SCOPE_CONFLICT"
            elif width is None:
                status = "MISSING_MEASUREMENT"
            elif not parts_present:
                status = "ASSEMBLY_NOT_ESTABLISHED"
            else:
                status = "REVIEW_REQUIRED"
            pairs.append({
                "RequirementID": requirement["RequirementID"],
                "PDFPage": requirement["PDFPage"],
                "ClauseText": requirement["ClauseText"],
                "ClauseContext": requirement["Context"][:700],
                "SourceMeaning": requirement["SourceMeaning"],
                "GlobalId": gid,
                "IFCType": e.get("Type", ""),
                "ElementName": e.get("Name", ""),
                "Storey": e.get("Storey", ""),
                "IFCIsExternal": external,
                "IFCMaterials": "; ".join(map(str, e.get("Materials", []) or [])),
                "IFCThicknessSource": e.get("WidthSource", ""),
                "ObservedThickness_mm": width,
                "PDFNominalAssembly_mm": requirement["PDFNominalAssembly_mm"],
                "AbsNumericDifference_mm": round(distance, 4) if distance is not None else None,
                "RankScore": score,
                "RetrievalBasis": "numeric_proximity" if near else "material_assembly_terms",
                "Reasons": "; ".join(reasons),
                "ScreeningStatus": status,
                "ContractualApplicability": "NOT_VERIFIED",
                "StructuralComparability": "NOT_VERIFIED",
                "ComplianceVerdict": "NOT_ASSESSABLE",
                "Method": "scoped_ifc_pdf_evidence_ranking",
            })
        pairs.sort(key=lambda row: (
            row["ScreeningStatus"] == "SCOPE_CONFLICT",
            -row["RankScore"],
            row["AbsNumericDifference_mm"] if row["AbsNumericDifference_mm"] is not None else float("inf"),
            str(row["GlobalId"]),
        ))
        pools.append(pairs)
    # Round robin: a long, earlier PDF section must not monopolise the cap.
    selected = []
    cursor = [0] * len(pools)
    seen = set()
    while len(selected) < max_pairs:
        advanced = False
        for i, pool in enumerate(pools):
            while cursor[i] < len(pool):
                pair = pool[cursor[i]]
                cursor[i] += 1
                k = (pair["RequirementID"], pair["GlobalId"])
                if k in seen:
                    continue
                seen.add(k)
                selected.append(pair)
                advanced = True
                break
            if len(selected) >= max_pairs:
                break
        if not advanced:
            break
    return selected


def select_graph_elements(elements, ranked_links, cap=40):
    """Prioritise graph context that is relevant to the retrieved PDF clauses.

    No more arbitrary first 40 alphabetically sorted walls. Remaining slots
    cover diverse material, type, storey and wall thickness combinations.
    """
    if cap <= 0:
        return []
    indexed = {str(e.get("GlobalId")): e for e in elements if e.get("GlobalId")}
    chosen, seen = [], set()
    for pair in ranked_links:
        gid = pair["GlobalId"]
        if gid in indexed and gid not in seen:
            chosen.append(indexed[gid]); seen.add(gid)
            if len(chosen) >= cap:
                return chosen
    # Deterministic diversity sweep, not randomly changing across runs.
    others = sorted((e for gid, e in indexed.items() if gid not in seen),
                    key=lambda e: str(e.get("GlobalId")))
    groups = {}
    for e in others:
        materials = tuple(sorted(str(x).casefold() for x in e.get("Materials", []) or []))
        key = (e.get("Type"), e.get("Storey"), materials,
               round(_numeric(e.get("Width")) or 0, 1))
        groups.setdefault(key, []).append(e)
    group_keys = sorted(groups, key=str)
    while len(chosen) < cap and any(groups.values()):
        for key in group_keys:
            if groups[key]:
                chosen.append(groups[key].pop(0))
                if len(chosen) >= cap:
                    break
    return chosen


def format_grounded_link_context(ranked_links, graph_records=(), max_links=8):
    """Show model-specific GlobalIds and source pages in a small LLM prompt."""
    graph_by_id = {str(r.get("globalId")): r for r in graph_records}
    lines = []
    for p in ranked_links[:max_links]:
        gid = p["GlobalId"]
        graph = graph_by_id.get(gid, {})
        lines.append(
            f"PDF p.{p['PDFPage']} {p['RequirementID']} => IFC GlobalId={gid}; "
            f"observed={p['ObservedThickness_mm']} mm "
            f"({p['IFCThicknessSource']}); storey={p['Storey']}; "
            f"materials={p['IFCMaterials']}; graph_storeys={graph.get('storeys', [])}; "
            f"graph_materials={graph.get('materials', [])}; "
            f"screen={p['ScreeningStatus']}; reasons={p['Reasons']}. "
            "This is NOT an applicable contractual rule and NOT a compliance verdict."
        )
    return "\n".join(lines)
