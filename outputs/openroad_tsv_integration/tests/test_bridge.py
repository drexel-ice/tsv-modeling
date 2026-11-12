import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bridge as b

ROOT=Path(__file__).resolve().parents[1]

class Property:
    def __init__(self,value):self.value=value
    def getValue(self):return self.value
    def setValue(self,value):self.value=value

class StringProperties:
    @staticmethod
    def find(obj,name):return obj.props.get(name)
    @staticmethod
    def create(obj,name,value):
        if name in obj.props:return None
        obj.props[name]=Property(value)
        return obj.props[name]

class DoubleProperties:
    @staticmethod
    def find(obj,name):return obj.props.get(name)

ODB=NS(dbStringProperty=StringProperties,dbDoubleProperty=DoubleProperties)

class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.config=json.loads((ROOT/'examples/config.json').read_text())
        self.endpoints=json.loads((ROOT/'examples/endpoints.json').read_text())

    def test_known_geometry_and_values(self):
        vias=b.build_vias(self.endpoints,self.config)
        result=b.evaluate(vias,self.config)
        self.assertEqual(len(result['pairs']),1)
        pair=result['pairs'][0]
        self.assertAlmostEqual(pair['pitch_m'],40e-6)
        self.assertAlmostEqual(pair['edge_spacing_m'],20e-6)
        self.assertAlmostEqual(result['tsvs'][0]['r_ohm']*1e3,10.4937325116,places=8)
        self.assertAlmostEqual(result['tsvs'][0]['c_ground_farad']*1e15,29.49,delta=.005)
        self.assertFalse(result['native_rc_injected'])

    def test_repeated_storage_is_idempotent(self):
        result=b.evaluate(b.build_vias(self.endpoints,self.config),self.config)
        root=NS(props={});db=NS(getChip=lambda:root)
        b.store_results(ODB,db,result);b.store_results(ODB,db,result)
        self.assertEqual(len(root.props),1)
        self.assertEqual(b.read_results(ODB,db),result)

    def test_requires_explicit_model_convention_opt_in(self):
        self.config['model']['allow_unreconciled_capacitance']=False
        with self.assertRaises(ValueError):b.evaluate(b.build_vias(self.endpoints,self.config),self.config)

    def test_hybrid_bond_and_copper_are_not_tsv_defaults(self):
        self.config['tsvs'][0]['kind']='hybrid_bond'
        with self.assertRaises(ValueError):b.build_vias(self.endpoints,self.config)
        self.config['tsvs'][0]['kind']='cylindrical_tsv'
        self.config['tsvs'][0]['conductor']='copper'
        with self.assertRaises(ValueError):b.evaluate(b.build_vias(self.endpoints,self.config),self.config)

    def test_net_mismatch_rejected(self):
        key=b.endpoint_key(**{'chip_path':['top_die'],'pad_instance':'TSV_0_top'})
        self.endpoints[key]['net']='wrong_net'
        with self.assertRaises(ValueError):b.build_vias(self.endpoints,self.config)

    def test_missing_core_diameter_not_inferred_from_pad(self):
        del self.config['tsvs'][0]['diameter_m']
        with self.assertRaises(ValueError):b.build_vias(self.endpoints,self.config)

    def test_unequal_pair_is_not_silently_approximated(self):
        self.config['tsvs'][1]['diameter_m']=40e-6
        result=b.evaluate(b.build_vias(self.endpoints,self.config),self.config)
        self.assertEqual(len(result['pairs']),0)
        self.assertEqual(len(result['skipped_pairs']),1)

    def test_database_metadata_precedes_config_and_detects_conflict(self):
        handles={k:{'pad_instance':NS(props={b.SCHEMA+'.diameter_m':Property(40e-6)})} for k in self.endpoints}
        with self.assertRaises(ValueError):b.build_vias(self.endpoints,self.config,ODB,handles)

    def test_occurrence_paths_avoid_master_aliasing(self):
        self.assertNotEqual(b.endpoint_key(['a','b'],'pad'),b.endpoint_key(['a/b'],'pad'))
        self.assertNotEqual(b.endpoint_key(['mem0'],'pad'),b.endpoint_key(['mem1'],'pad'))

    def test_global_geometry_extraction_uses_assembly_dbu(self):
        def bump(path,xyz,oid):
            inst=NS(getName=lambda:'shared_pad',props={})
            raw=NS(getId=lambda:oid,getChipBump=lambda:NS(getInst=lambda:inst))
            parent=NS(getChipInstPath=lambda:[NS(getName=lambda:path)])
            return NS(getChipBumpInst=lambda:raw,getParentRegion=lambda:NS(getParentChip=lambda:parent),getGlobalPosition=lambda:xyz)
        a=bump('mem0',(1000,2000,3000),1);c=bump('mem1',(9000,2000,3000),2)
        net=NS(getName=lambda:'signal')
        db=NS(constructUnfoldedModel=lambda:None,getDbuPerMicron=lambda:1000,
              getUnfoldedChipBumpInsts=lambda:[a,c],getUnfoldedChipNets=lambda:[NS(getChipNet=lambda:net,getConnectedBumps=lambda:[a,c])])
        endpoints,_=b.extract_endpoints(db)
        self.assertEqual(len(endpoints),2)
        self.assertAlmostEqual(endpoints[b.endpoint_key(['mem1'],'shared_pad')]['position_m'][0],9e-6)
        self.assertEqual(len({e['net'] for e in endpoints.values()}),1)

if __name__=='__main__':unittest.main()
