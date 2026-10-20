import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# IfcOpenShell/Streamlit aren't available in this offline test environment;
# deliberately replace only those external boundaries, not our code.
if 'ifcopenshell' not in sys.modules:
    o = ModuleType('ifcopenshell')
    o.__path__ = []
    o.open = lambda name: None
    util = ModuleType('ifcopenshell.util')
    util.__path__ = []
    element_mod = ModuleType('ifcopenshell.util.element')
    unit_mod = ModuleType('ifcopenshell.util.unit')
    unit_mod.calculate_unit_scale = lambda model: model.scale_m
    element_mod.get_material = lambda e, **kwargs: getattr(e, 'material', None)
    element_mod.get_psets = lambda e: getattr(e,'psets', {})
    util.element = element_mod; util.unit = unit_mod; o.util = util
    sys.modules.update({'ifcopenshell':o, 'ifcopenshell.util':util,
                        'ifcopenshell.util.element':element_mod, 'ifcopenshell.util.unit':unit_mod})

from check_ifc_compliance import extract_all_ifc_wall_dimensions, parse_component_filter, _mm_per_native_unit
from audit_engine import AuditRule, audit_elements
from validation_export import sample_from_current_model,evidence_review_worksheet
from validation import evaluate_records
from spec_context import clause_candidates
from unittest.mock import patch
import io
import pytest

class FakeElement:
    def __init__(self, typ, gid, name, material=None, psets=None, dimensions=None):
        self.typ=typ; self.GlobalId=gid; self.Name=name; self.material=material; self.psets=psets or {}
        self.ContainedInStructure=[];self.Decomposes=[]
        for k,v in (dimensions or {}).items(): setattr(self,k,v)
    def is_a(self,cls=None):
        if cls is None:return self.typ
        if cls=='IfcElement':return True
        if cls=='IfcWall':return self.typ in ('IfcWall','IfcWallStandardCase')
        if cls=='IfcDoor':return self.typ in ('IfcDoor','IfcDoorStandardCase')
        if cls=='IfcWindow':return self.typ in ('IfcWindow','IfcWindowStandardCase')
        return self.typ==cls
    def id(self):return id(self)

class FakeMaterial:
    def __init__(self,layers):
        self.ForLayerSet=SimpleNamespace(MaterialLayers=[SimpleNamespace(
            Material=SimpleNamespace(Name=name),LayerThickness=thick) for name,thick in layers])
    def is_a(self,tag=None):return 'IfcMaterialLayerSetUsage' if tag is None else tag=='IfcMaterialLayerSetUsage'

class FakeModel:
    def __init__(self, schema, length_m, els):self.schema=schema;self.scale_m=length_m;self.els=els
    def by_type(self,t):
        if t!='IfcElement':raise AssertionError('must use IFC hierarchy')
        return self.els

@pytest.fixture
def models(monkeypatch):
    import ifcopenshell
    imperial=FakeModel('IFC2X3',0.3048,[
        FakeElement('IfcWall','2x3-W1','Foot Wall',FakeMaterial([('brick',0.5),('insulation',0.25)])),
        FakeElement('IfcDoor','2x3-D1','Door',dimensions={'OverallWidth':3,'OverallHeight':7}),
        FakeElement('IfcBeam','2x3-B1','Beam')])
    metric=FakeModel('IFC4',0.001,[
        FakeElement('IfcWallStandardCase','4-W1','Thick retaining wall',FakeMaterial([('concrete',725)])),
        FakeElement('IfcWindow','4-V1','Window',dimensions={'OverallWidth':1200,'OverallHeight':900}),
        FakeElement('IfcColumn','4-C1','Column')])
    monkeypatch.setattr(ifcopenshell,'open',lambda name: {'a.ifc':imperial,'b.ifc':metric}[name])
    return imperial,metric

def test_filter_all_is_independent_of_uploaded_model():
    assert parse_component_filter('All model elements')[0]=='all'
    assert parse_component_filter('IfcColumn,IfcPipeSegment')[1]==('IfcColumn','IfcPipeSegment')
    assert parse_component_filter('Wall')[1]==('IfcWall','IfcCurtainWall')

@pytest.mark.parametrize('invalid',['randomword','wall2','Ifc../bad'])
def test_invalid_ifc_class_rejected(invalid):
    with pytest.raises(ValueError):parse_component_filter(invalid)

def test_two_schema_imperial_and_metric_units(models):
    imperial,metric=models
    a=extract_all_ifc_wall_dimensions('a.ifc','All model elements')
    b=extract_all_ifc_wall_dimensions('b.ifc','All model elements')
    assert len(a)==3 and len(b)==3
    assert a[0]['Type']=='IfcBeam'  # sorted by independent GlobalIds
    aw=next(e for e in a if e['Type']=='IfcWall')
    assert aw['Width']==228.6 and aw['IFCSchema']=='IFC2X3'
    door=next(e for e in a if e['Type']=='IfcDoor')
    assert door['Dimensions_mm']['OverallWidth_mm']==914.4
    bw=next(e for e in b if e['Type']=='IfcWallStandardCase')
    assert bw['Width']==725.0, 'no arbitrary 600mm cutoff'
    assert bw['IFCSchema']=='IFC4'
    assert next(e for e in b if e['Type']=='IfcWindow')['Dimensions_mm']['OverallWidth_mm']==1200

def test_distinct_models_do_not_depend_on_name_or_ids(models):
    first=extract_all_ifc_wall_dimensions('a.ifc','Wall')
    second=extract_all_ifc_wall_dimensions('b.ifc','Wall')
    assert [r['GlobalId'] for r in first]==['2x3-W1']
    assert [r['GlobalId'] for r in second]==['4-W1']

def test_actual_ifc_measurement_used_not_element_name(models):
    m=FakeModel('IFC4',0.001,[FakeElement('IfcWall','XX','Basic Wall 999mm fake')])
    import ifcopenshell
    prev=ifcopenshell.open
    ifcopenshell.open=lambda x:m
    try:
        out=extract_all_ifc_wall_dimensions('anything.ifc','Wall')
        assert out[0]['Width']=='Unknown'
        assert out[0]['MeasurementQuality']=='MISSING'
    finally:ifcopenshell.open=prev

def test_conflicting_measurements_are_abstentions(models):
    import ifcopenshell
    m=FakeModel('IFC4',0.001,[FakeElement('IfcWall','AA','Wall',FakeMaterial([('one',100)]),
                                    {'Qto_WallBaseQuantities':{'Width':125}})])
    old=ifcopenshell.open; ifcopenshell.open=lambda x:m
    try:
        e=extract_all_ifc_wall_dimensions('anything.ifc','Wall')[0]
        assert e['MeasurementQuality']=='CONFLICTING'
        assert audit_elements([e],AuditRule(100,source='test',scope='all'))[0]['IssueCategory']=='REVIEW_REQUIRED'
    finally:ifcopenshell.open=old

def test_no_rule_no_pass_fail(models):
    rows=audit_elements(extract_all_ifc_wall_dimensions('b.ifc','All model elements'),None)
    assert all(r['IssueCategory']=='NOT_ASSESSABLE' for r in rows)

def test_wall_rule_is_not_misapplied_to_doors(models):
    data=extract_all_ifc_wall_dimensions('a.ifc','All model elements')
    rows=audit_elements(data,AuditRule(228.6,source='test',scope='all'))
    assert next(r for r in rows if r['IFCType']=='IfcDoor')['IssueCategory']=='NOT_APPLICABLE'
    assert next(r for r in rows if r['IFCType']=='IfcWall')['IssueCategory']=='PASS'

def test_door_explicit_metric(models):
    data=extract_all_ifc_wall_dimensions('a.ifc','All model elements')
    rows=audit_elements(data,AuditRule(900,source='synthetic',scope='all',metric='Door overall width'))
    assert next(r for r in rows if r['IFCType']=='IfcDoor')['IssueCategory']=='GEOMETRY_MISMATCH'

def test_unknown_scope_is_reviewed_not_passed(models):
    data=extract_all_ifc_wall_dimensions('b.ifc','Wall')
    rows=audit_elements(data,AuditRule(725,source='p.10',scope='external',test_mode=False))
    assert rows[0]['IssueCategory']=='SCOPE_UNVERIFIED'

def test_sample_generated_for_any_set_and_stable():
    a=[dict(GlobalId=f'A{i}',IFCType='IfcWall',IssueCategory='NOT_ASSESSABLE') for i in range(50)]
    b=[dict(GlobalId=f'B{i}',IFCType='IfcSlab',IssueCategory='NOT_ASSESSABLE') for i in range(50)]
    x=sample_from_current_model(a+b,30,seed=42)
    y=sample_from_current_model(list(reversed(a+b)),30,seed=42)
    assert len(x)==30 and [t['GlobalId'] for t in x]==[t['GlobalId'] for t in y]
    assert Counter(r['IFCType'] for r in x)=={'IfcWall':15,'IfcSlab':15}
    z=sample_from_current_model([dict(GlobalId='OTHER',IFCType='IfcBeam',IssueCategory='NOT_ASSESSABLE')],30)
    assert len(z)==1 and z[0]['GlobalId']=='OTHER'

def test_worksheet_leaves_truth_unfilled():
    sheet=evidence_review_worksheet([dict(GlobalId='X',IFCType='IfcWall',IssueCategory='GEOMETRY_MISMATCH')])
    assert sheet[0]['ground_truth_mismatch']==''
    assert sheet[0]['predicted_mismatch']=='1'

def test_no_metrics_when_labels_are_blank():
    m=evaluate_records([{'ground_truth_mismatch':'','predicted_mismatch':'1'}])
    assert m['N_evaluated']==0 and m['precision'] is None

def test_pdf_search_relevance_across_categories(monkeypatch):
    class Reader:
        def __init__(self,x):self.pages=[SimpleNamespace(extract_text=lambda: 'External walls must be 250 mm total thickness.\nThe insulation thickness is 60 mm.\nAll external masonry shall be inspected.\n\nDoors require a clear opening 900 mm width.\nDoor leaf is steel.\nDoor hinges must comply with standard.\n\n')]
    import spec_context
    monkeypatch.setattr(spec_context,'PdfReader',Reader)
    records,n=clause_candidates(b'ignored',['IfcWall','IfcDoor'])
    assert n>=2
    assert any('wall' in r['Types'] for r in records)
    assert any('door' in r['Types'] for r in records)

def test_scanned_pdf_is_clearly_rejected(monkeypatch):
    import spec_context
    monkeypatch.setattr(spec_context,'PdfReader',lambda x:SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda:'')]))
    with pytest.raises(ValueError,match='OCR'):clause_candidates(b'',component='IfcWall')

def test_nonenglish_pdf_still_returns_unverified_evidence(monkeypatch):
    import spec_context
    text = 'Béton armé : largeur de la dalle supérieure à deux cents millimètres, et contrôle selon la norme technique.\nCe paragraphe spécifie les matériaux de construction pour le chantier et les étages.'
    monkeypatch.setattr(spec_context,'PdfReader',lambda x:SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda:text)]))
    results,n=clause_candidates(b'pdf',['IfcWall'])
    assert n==0 or all(r['Score']==0 for r in results)
    assert results and results[0]['Page']==1
    assert results[0]['Types']==['unmatched-language-review']

def test_synthetic_scope_never_confused_with_verified_scope():
    with pytest.raises(ValueError):AuditRule(thickness_mm=100,scope='all',source='real clause',test_mode=False)
    with pytest.raises(ValueError):AuditRule(thickness_mm=100,scope='global_id',source='synthetic')

def test_graph_uses_model_hash_and_has_no_global_delete(monkeypatch):
    import importlib
    if 'neo4j' not in sys.modules:
        n=ModuleType('neo4j')
        n.GraphDatabase=SimpleNamespace(driver=lambda *args,**kwargs:None)
        sys.modules['neo4j']=n
    mod=importlib.import_module('ifc_to_neo4j')
    calls=[]
    class Response:
        def consume(self):return self
        def __iter__(self):return iter([])
    class Session:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def run(self,q,**kw):calls.append((q,kw));return Response()
    class Driver:
        def session(self,**kwargs):return Session()
        def close(self):pass
    monkeypatch.setenv('NEO4J_URI','bolt://example.test:7687')
    monkeypatch.setenv('NEO4J_USERNAME','test')
    monkeypatch.setenv('NEO4J_PASSWORD','only-test-placeholder')
    monkeypatch.setattr(mod.GraphDatabase,'driver',lambda *args,**kw:Driver())
    mapper=mod.IFCGraphMapper()
    r=[dict(GlobalId='SAME-GID',Name='Beam',Type='IfcBeam',Storey='L1',Materials=['Concrete'],Width='Unknown')]
    hash_a='a'*64;hash_b='b'*64
    assert mapper.upload_elements(hash_a,r)==1
    assert mapper.upload_elements(hash_b,r)==1
    batches=[params for query,params in calls if 'UNWIND $rows' in query and 'MERGE (e:AuditElementV4' in query]
    assert batches[0]['rows'][0]['key']==hash_a+':SAME-GID'
    assert batches[1]['rows'][0]['key']==hash_b+':SAME-GID'
    assert not any('DETACH DELETE' in q for q,params in calls)
