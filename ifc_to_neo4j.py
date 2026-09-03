import ifcopenshell
from neo4j import GraphDatabase
import streamlit as st

class IFCGraphMapper:
    def __init__(self):
        # Read securely from Streamlit's secrets configuration with updated instance defaults
        uri = st.secrets.get("NEO4J_URI", "neo4j+s://cf515c86.databases.neo4j.io")
        username = st.secrets.get("NEO4J_USERNAME", "neo4j")
        password = st.secrets.get("NEO4J_PASSWORD", "pwToINeEQUP8EctkjlHYZcOlWfb8RhI6TF32qtczq6M")
        self.database = st.secrets.get("NEO4J_DATABASE", "neo4j")
        
        self.driver = GraphDatabase.driver(uri, auth=(username, password))

    def close(self):
        self.driver.close()

    def setup_constraints(self):
        """Creates database uniqueness constraints and indexes to prevent performance bottlenecks."""
        with self.driver.session(database=self.database) as session:
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (e:BIMElement) REQUIRE e.globalId IS UNIQUE")
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (s:BuildingStorey) REQUIRE s.globalId IS UNIQUE")
            session.run("CREATE INDEX IF NOT EXISTS FOR (m:Material) ON (m.name)")

    def clear_database(self):
        """Clears existing nodes to ensure a fresh, project-specific audit graph."""
        with self.driver.session(database=self.database) as session:
            session.run("MATCH (n) DETACH DELETE n")

    def upload_ifc_to_graph(self, ifc_filepath):
        """Parses the IFC model and maps core architectural entities and relationships."""
        # Ensure graph indexes exist before writing elements
        self.setup_constraints()
        
        ifc_model = ifcopenshell.open(ifc_filepath)
        
        with self.driver.session(database=self.database) as session:
            # 1. Map Spatial Hierarchies (Storeys/Levels)
            storeys = ifc_model.by_type("IfcBuildingStorey")
            for storey in storeys:
                session.run(
                    "MERGE (s:BuildingStorey {globalId: $gid}) "
                    "SET s.name = $name",
                    gid=storey.GlobalId, 
                    name=storey.Name or "Unnamed Level"
                )

            # 2. Map Structural Components (Walls, CurtainWalls, Columns, Slabs, etc.)
            products = ifc_model.by_type("IfcProduct")
            for product in products:
                if product.is_a("IfcSpatialStructureElement"):
                    continue
                
                width = None
                is_external = False
                
                for definition in getattr(product, "IsDefinedBy", []):
                    if definition.is_a("IfcRelDefinesByProperties"):
                        property_set = getattr(definition, "RelatingPropertyDefinition", None)
                        if property_set and property_set.is_a("IfcPropertySet"):
                            pset_name = property_set.Name or ""
                            if "Common" in pset_name or "Dimensions" in pset_name:
                                for prop in getattr(property_set, "HasProperties", []):
                                    prop_name = getattr(prop, "Name", "")
                                    nom_val = getattr(prop, "NominalValue", None)
                                    
                                    if ("Width" in prop_name or "Thickness" in prop_name) and nom_val:
                                        try:
                                            width = float(nom_val.wrappedValue)
                                        except (ValueError, TypeError):
                                            width = str(nom_val.wrappedValue)
                                            
                                    if "External" in prop_name and nom_val:
                                        raw_val = nom_val.wrappedValue
                                        is_external = bool(raw_val) if isinstance(raw_val, (bool, int)) else str(raw_val).lower() == "true"

                session.run(
                    "MERGE (e:BIMElement {globalId: $gid}) "
                    "SET e.name = $name, e.type = $type, e.width = $width, e.isExternal = $is_external",
                    gid=product.GlobalId, 
                    name=product.Name or "Unnamed Element", 
                    type=product.is_a(),
                    width=width if width is not None else "Unknown", 
                    is_external=is_external
                )

                # 3. Establish Spatial Containment Relationships (CONTAINED_IN)
                for relation in getattr(product, "ContainedInStructure", []):
                    storey_id = relation.RelatingStructure.GlobalId
                    session.run(
                        "MATCH (e:BIMElement {globalId: $element_id}), (s:BuildingStorey {globalId: $storey_id}) "
                        "MERGE (e)-[:CONTAINED_IN]->(s)",
                        element_id=product.GlobalId, 
                        storey_id=storey_id
                    )

                # 4. Establish Material Association Relationships (HAS_MATERIAL)
                for assoc in getattr(product, "HasAssociations", []):
                    if assoc.is_a("IfcRelAssociatesMaterial"):
                        material_select = assoc.RelatingMaterial
                        material_name = "Unknown Material"
                        
                        if material_select.is_a("IfcMaterial"):
                            material_name = material_select.Name or material_name
                        elif material_select.is_a("IfcMaterialLayerSetUsage"):
                            if material_select.ForLayerSet and material_select.ForLayerSet.LayerSetName:
                                material_name = material_select.ForLayerSet.LayerSetName
                        elif material_select.is_a("IfcMaterialList"):
                            m_names = [m.Name for m in getattr(material_select, "Materials", []) if getattr(m, "Name", None)]
                            if m_names:
                                material_name = ", ".join(m_names)
                        
                        session.run(
                            "MATCH (e:BIMElement {globalId: $element_id}) "
                            "MERGE (m:Material {name: $mat_name}) "
                            "MERGE (e)-[:HAS_MATERIAL]->(m)",
                            element_id=product.GlobalId, 
                            mat_name=material_name
                        )

        self.close()
        return True
