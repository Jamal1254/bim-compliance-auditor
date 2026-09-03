import ifcopenshell
from neo4j import GraphDatabase
import streamlit as st

class IFCGraphMapper:
    def __init__(self):
        # Read securely from Streamlit's configuration layer
        uri = st.secrets.get("NEO4J_URI", "neo4j+s://cf515c86.databases.neo4j.io")
        username = st.secrets.get("NEO4J_USERNAME", "neo4j")
        password = st.secrets.get("NEO4J_PASSWORD", "pwToINeEQUP8EctkjlHYZcOlWfb8RhI6TF32qtczq6M")
        self.database = st.secrets.get("NEO4J_DATABASE", "neo4j")        
        self.driver = GraphDatabase.driver(uri, auth=(username, password))
    
    def close(self):
        self.driver.close()

    def clear_database(self):
        """Clears existing nodes to ensure a fresh, project-specific audit graph."""
        with self.driver.session(database=self.database) as session:
            session.run("MATCH (n) DETACH DELETE n")

    def upload_ifc_to_graph(self, ifc_filepath):
        """Parses the IFC model and maps core architectural entities and relationships."""
        ifc_model = ifcopenshell.open(ifc_filepath)
        
        with self.driver.session(database=self.database) as session:
            # 1. Map Spatial Hierarchies (Storeys/Levels)
            storeys = ifc_model.by_type("IfcBuildingStorey")
            for storey in storeys:
                session.run(
                    "MERGE (s:BuildingStorey {globalId: $gid}) "
                    "SET s.name = $name",
                    gid=storey.GlobalId, name=storey.Name
                )

            # 2. Map Structural Components (Walls, CurtainWalls, etc.)
            products = ifc_model.by_type("IfcProduct")
            for product in products:
                if product.is_a("IfcSpatialStructureElement"):
                    continue
                
                width = "Unknown"
                is_external = "False"
                
                for definition in getattr(product, "IsDefinedBy", []):
                    if definition.is_a("IfcRelDefinesByProperties"):
                        property_set = definition.RelatingPropertyDefinition
                        if property_set.is_a("IfcPropertySet"):
                            if "Common" in property_set.Name or "Dimensions" in property_set.Name:
                                for prop in property_set.HasProperties:
                                    if "Width" in prop.Name or "Thickness" in prop.Name:
                                        width = str(prop.NominalValue.wrappedValue) if prop.NominalValue else width
                                    if "External" in prop.Name:
                                        is_external = str(prop.NominalValue.wrappedValue) if prop.NominalValue else is_external

                session.run(
                    "MERGE (e:BIMElement {globalId: $gid}) "
                    "SET e.name = $name, e.type = $type, e.width = $width, e.isExternal = $is_external",
                    gid=product.GlobalId, name=product.Name, type=product.is_a(),
                    width=width, is_external=is_external
                )

                # 3. Establish Spatial Containment Relationships (CONTAINED_IN)
                for relation in getattr(product, "ContainedInStructure", []):
                    storey_id = relation.RelatingStructure.GlobalId
                    session.run(
                        "MATCH (e:BIMElement {globalId: $element_id}), (s:BuildingStorey {globalId: $storey_id}) "
                        "MERGE (e)-[:CONTAINED_IN]->(s)",
                        element_id=product.GlobalId, storey_id=storey_id
                    )

                # 4. Establish Material Association Relationships (HAS_MATERIAL)
                for assoc in getattr(product, "HasAssociations", []):
                    if assoc.is_a("IfcRelAssociatesMaterial"):
                        material_select = assoc.RelatingMaterial
                        material_name = "Unknown Material"
                        
                        if material_select.is_a("IfcMaterial"):
                            material_name = material_select.Name
                        elif material_select.is_a("IfcMaterialLayerSetUsage"):
                            material_name = material_select.ForLayerSet.LayerSetName if material_select.ForLayerSet else material_name
                        
                        session.run(
                            "MATCH (e:BIMElement {globalId: $element_id}) "
                            "MERGE (m:Material {name: $mat_name}) "
                            "MERGE (e)-[:HAS_MATERIAL]->(m)",
                            element_id=product.GlobalId, mat_name=material_name
                        )

        self.close()
        return True
