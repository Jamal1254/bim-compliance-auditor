"""Project-isolated IFC evidence graph. No shared-account credentials or global delete.

The graph contains *observed* evidence, not automatically verified contractual
requirements. Each project is keyed by file SHA-256 to avoid cross-file leakage.
"""
import hashlib
import os
from neo4j import GraphDatabase


def _setting(name):
    value = os.environ.get(name)
    if value:
        return value
    try:
        import streamlit as st
        return str(st.secrets.get(name, "") or "")
    except Exception:
        return ""


class IFCGraphMapper:
    def __init__(self):
        uri = _setting("NEO4J_URI")
        username = _setting("NEO4J_USERNAME")
        password = _setting("NEO4J_PASSWORD")
        self.database = _setting("NEO4J_DATABASE") or "neo4j"
        if not all((uri, username, password)):
            raise RuntimeError("Provide NEO4J_URI, NEO4J_USERNAME and NEO4J_PASSWORD in Streamlit Secrets")
        self.driver = GraphDatabase.driver(uri, auth=(username, password))

    def close(self):
        self.driver.close()

    def setup_constraints(self):
        with self.driver.session(database=self.database) as s:
            s.run("CREATE CONSTRAINT audit_element_v4_key IF NOT EXISTS FOR (e:AuditElementV4) REQUIRE e.key IS UNIQUE").consume()
            s.run("CREATE CONSTRAINT audit_model_v4_sha IF NOT EXISTS FOR (m:AuditModelV4) REQUIRE m.sha256 IS UNIQUE").consume()
            s.run("CREATE CONSTRAINT audit_storey_v4_key IF NOT EXISTS FOR (s:AuditStoreyV4) REQUIRE s.key IS UNIQUE").consume()
            s.run("CREATE CONSTRAINT audit_material_v4_key IF NOT EXISTS FOR (m:AuditMaterialV4) REQUIRE m.key IS UNIQUE").consume()

    def upload_elements(self, model_hash, elements):
        """Upsert only uploaded project's selected elements, in batches."""
        if not model_hash or len(model_hash) != 64:
            raise ValueError("Model SHA-256 required")
        self.setup_constraints()
        items = []
        for e in elements:
            gid = str(e.get("GlobalId") or "")
            if not gid:
                continue
            materials = sorted(set(str(m) for m in e.get("Materials", []) if m))
            items.append({
                "key": f"{model_hash}:{gid}", "gid": gid,
                "name": str(e.get("Name") or ""), "ifcType": str(e.get("Type") or ""),
                "storey": str(e.get("Storey") or "Unknown"),
                "isExternal": e.get("IsExternal") if isinstance(e.get("IsExternal"), bool) else None,
                "widthMm": e.get("Width") if isinstance(e.get("Width"), (int, float)) else None,
                "widthSource": str(e.get("WidthSource") or ""),
                "materials": [{"key": f"{model_hash}:material:{hashlib.sha256(m.encode()).hexdigest()}", "name": m} for m in materials]
            })
        with self.driver.session(database=self.database) as s:
            for i in range(0, len(items), 150):
                batch = items[i:i+150]
                s.run("""
                    MERGE (model:AuditModelV4 {sha256:$hash})
                    WITH model
                    UNWIND $rows AS row
                    MERGE (e:AuditElementV4 {key:row.key})
                    SET e.globalId=row.gid,e.modelHash=$hash,e.name=row.name,
                        e.type=row.ifcType,e.widthMm=row.widthMm,
                        e.widthSource=row.widthSource,e.isExternal=row.isExternal
                    MERGE (e)-[:IN_MODEL]->(model)
                    FOREACH (_ IN CASE WHEN row.storey='Unknown' THEN [] ELSE [1] END |
                        MERGE (st:AuditStoreyV4 {key:$hash + ':storey:' + row.storey})
                        SET st.name=row.storey,st.modelHash=$hash
                        MERGE (e)-[:CONTAINED_IN]->(st)
                    )
                """, hash=model_hash, rows=batch).consume()
                s.run("""
                    UNWIND $rows AS row
                    MATCH (e:AuditElementV4 {key:row.key})
                    UNWIND row.materials AS mat
                    MERGE (m:AuditMaterialV4 {key:mat.key})
                    SET m.name=mat.name,m.modelHash=$hash
                    MERGE (e)-[:HAS_MATERIAL]->(m)
                """, rows=batch, hash=model_hash).consume()
        return len(items)

    def retrieve_element_neighborhood(self, global_ids, model_hash, limit=150):
        if not global_ids:
            return []
        with self.driver.session(database=self.database) as s:
            return [dict(x) for x in s.run("""
                MATCH (e:AuditElementV4 {modelHash:$hash})
                WHERE e.globalId IN $ids
                OPTIONAL MATCH (e)-[:CONTAINED_IN]->(st:AuditStoreyV4)
                OPTIONAL MATCH (e)-[:HAS_MATERIAL]->(mat:AuditMaterialV4)
                RETURN e.globalId AS globalId,e.name AS name,e.type AS type,
                       e.widthMm AS observedWallThicknessMm,e.widthSource AS widthSource,
                       e.isExternal AS isExternal,
                       collect(DISTINCT st.name) AS storeys,
                       collect(DISTINCT mat.name) AS materials
                ORDER BY globalId LIMIT $limit
            """,hash=model_hash,ids=list(global_ids),limit=int(limit))]
