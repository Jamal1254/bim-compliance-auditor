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
    """Return ranked, source-linked pairs with non-verdict eligibility checks.

    Numeric distance is only one discovery hint, NEVER a tolerance. The
    complete matched assembly and relevant building/project scope must be
    verified separately, independently of the ranking score.
    """
    output = []
    for requirement in _requirements(assembly_rows):
        context = (requirement["ClauseText"] + " " + requirement["Context"]).casefold()
        external_clause = bool(re.search(r"\bexternal\s+(?:masonry\s+)?walls?\b", context))
        below_dpc = bool(re.search(r"\bbelow\s+(?:the\s+)?(?:damp\s+proof\s+course|dpc)\b", context))
        above_dpc = bool(re.search(r"\babove\s+(?:the\s+)?(?:damp\s+proof\s+course|dpc)\b", context))
        for e in walls:
            if not str(e.get("Type") or "").startswith(("IfcWall",)):
                continue
            gid = str(e.get("GlobalId") or "")
            if not gid:
                continue
            width = _numeric(e.get("Width"))
            distance = abs(width - requirement["PDFNominalAssembly_mm"]) if width is not None else None
            materials = _material_components(e)
            parts_present = all(materials.values())
            external = e.get("IsExternal")
            reasons = []
            score = 0
            if distance is not None and distance <= numeric_window_mm:
                score += 4
                reasons.append(f"Numerical proximity {distance:.4f} mm (discovery, NOT tolerance)")
            elif distance is not None:
                reasons.append("Reported IFC thickness differs from nominal PDF assembly")
            else:
                reasons.append("Comparable IFC wall thickness not available")
            if external_clause and external is True:
                score += 2
                reasons.append("Model IsExternal=True supports external-category retrieval")
            elif external_clause and external is False:
                reasons.append("CONFLICT: IFC marks element internal")
            elif external_clause:
                reasons.append("External/internal scope unverified")
            if parts_present:
                score += 3
                reasons.append("Material names mention brick, cavity and block; verify layer structure")
            else:
                reasons.append("Full brick+cavity+block assembly NOT evidenced by material names")
            if below_dpc or above_dpc:
                reasons.append("DPC level / number-of-storeys applicability not verified from IFC")
            if width is None:
                status = "MISSING_MEASUREMENT"
            elif external_clause and external is False:
                status = "SCOPE_CONFLICT"
            elif not parts_present:
                status = "ASSEMBLY_NOT_ESTABLISHED"
            else:
                status = "REVIEW_REQUIRED"
            # Only reasonably similar numerical candidates are useful for the
            # bounded graph/LLM retrieval; distant elements are still eligible
            # for local baseline comparison, if requested explicitly.
            output.append({
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
                "Reasons": "; ".join(reasons),
                "ScreeningStatus": status,
                "ContractualApplicability": "NOT_VERIFIED",
                "StructuralComparability": "NOT_VERIFIED",
                "ComplianceVerdict": "NOT_ASSESSABLE",
                "Method": "context_plus_numeric_retrieval",
            })
    # Keep one highest-scoring row per unique requirement-element pair
    output.sort(key=lambda r: (
        -r["RankScore"],
        r["AbsNumericDifference_mm"] if r["AbsNumericDifference_mm"] is not None else float("inf"),
        str(r["RequirementID"]), str(r["GlobalId"]),
    ))
    return output[:max_pairs]


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
