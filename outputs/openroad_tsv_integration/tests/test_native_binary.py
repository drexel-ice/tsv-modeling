"""Native tests: set OPENROAD_BIN to the built executable. No ODB mocks."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from make_native_fixture import create
from run_native import run

ROOT=Path(__file__).resolve().parents[1]
BINARY=os.environ.get('OPENROAD_BIN')

class NativeBinaryTests(unittest.TestCase):
    @unittest.skipUnless(BINARY,'set OPENROAD_BIN for a real compiled OpenROAD test')
    def test_geometry_metadata_models_and_persistent_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp=Path(directory);source=tmp/'source.odb';output=tmp/'output.odb'
            create(BINARY,source)
            source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
            config=json.loads((ROOT/'examples/native_config.json').read_text())
            # Require native double properties for both TSVs, not config fallbacks.
            for spec in config['tsvs']:
                for field in ('diameter_m','liner_m','ground_spacing_m','acceptors_cm3','intrinsic_cm3','temperature_k'):
                    del spec[field]
            result=run(BINARY,source,output,config,tmp/'report.json')
            self.assertEqual(len(result['tsvs']),2)
            self.assertEqual(len(result['pairs']),1)
            for row in result['tsvs']:
                geo=row['geometry']
                self.assertAlmostEqual(geo['z_max_m']-geo['z_min_m'],60e-6)
                self.assertAlmostEqual(geo['diameter_m'],20e-6)
                self.assertEqual(geo['provenance']['diameter_m'],'OpenDB namespaced double property')
                self.assertAlmostEqual(row['r_ohm']*1e3,10.49,delta=.005)
                self.assertAlmostEqual(row['c_ground_farad']*1e15,29.49,delta=.005)
            self.assertAlmostEqual(result['pairs'][0]['pitch_m'],40e-6)
            self.assertAlmostEqual(result['pairs'][0]['c_coupling_farad']*1e15,6.68,delta=.005)
            self.assertEqual(source_hash,hashlib.sha256(source.read_bytes()).hexdigest())
            # An existing results property is updated, not appended or accumulated.
            repeated=run(BINARY,output,tmp/'output2.odb',config,tmp/'report2.json')
            self.assertEqual(repeated,result)
            with self.assertRaises(ValueError):run(BINARY,source,source,config,tmp/'unsafe.json')
            with self.assertRaises(ValueError):run(BINARY,source,output,config,tmp/'overwrite.json')
            conflict=copy.deepcopy(config);conflict['tsvs'][0]['diameter_m']=40e-6
            with self.assertRaises(ValueError):run(BINARY,source,tmp/'conflict.odb',conflict,tmp/'bad.json')

class NativeRCBinaryTests(unittest.TestCase):
    @unittest.skipUnless(BINARY and os.environ.get('TSV_RUN_NATIVE_RC') == '1',
                         'set TSV_RUN_NATIVE_RC=1 and OPENROAD_BIN after rebuilding the patch')
    def test_native_elements_spef_and_repeat_insertion(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp=Path(directory);source=tmp/'source.odb'
            create(BINARY,source)
            digest=hashlib.sha256(source.read_bytes()).hexdigest()
            config=json.loads((ROOT/'examples/native_config.json').read_text())
            output=tmp/'native.odb'
            result=run(BINARY,source,output,config,tmp/'native.json',native_rc=True,liberty_files=[ROOT/"examples/native_fixture/landing.lib"])
            graph=json.loads((tmp/'native.native_graph.json').read_text())
            self.assertEqual(graph['summary']['tsv_pi_networks'],2)
            self.assertEqual(graph['summary']['ground_cap_nodes'],4)
            self.assertEqual(graph['summary']['coupling_elements'],2)
            repeated=run(BINARY,output,tmp/'again.odb',config,tmp/'again.json',native_rc=True,liberty_files=[ROOT/"examples/native_fixture/landing.lib"])
            self.assertEqual(repeated,result)
            graph2=json.loads((tmp/'again.native_graph.json').read_text())
            # ODB may reuse freed coupling slots in a different iteration order.
            # Compare the complete persisted elements without treating list order as topology.
            for kind in ('cap_nodes','resistors','couplings'):
                self.assertEqual(sorted(graph['graph'][kind],key=lambda row: json.dumps(row,sort_keys=True)),
                                 sorted(graph2['graph'][kind],key=lambda row: json.dumps(row,sort_keys=True)))
            self.assertEqual(digest,hashlib.sha256(source.read_bytes()).hexdigest())

class CopperNativeBinaryTests(unittest.TestCase):
    @unittest.skipUnless(BINARY and os.environ.get('TSV_RUN_NATIVE_RC') == '1',
                         'requires real native RC executable')
    def test_copper_geometry_dc_pending_and_supplied_capacitance(self):
        from test_material_models import add_test_reference
        with tempfile.TemporaryDirectory() as directory:
            tmp=Path(directory);source=tmp/'copper.odb'
            create(BINARY,source,profile='copper')
            config=json.loads((ROOT/'examples/copper_config.json').read_text())
            result=run(BINARY,source,tmp/'resistance_only.odb',config,tmp/'dc.json')
            for row in result['tsvs']:
                geo=row['geometry']
                self.assertAlmostEqual(geo['z_max_m']-geo['z_min_m'],50e-6)
                self.assertAlmostEqual(geo['diameter_m'],5e-6)
                self.assertEqual(geo['provenance']['conductivity_s_m'],'OpenDB namespaced double property')
                self.assertAlmostEqual(row['r_ohm'],.0439048,places=6)
            self.assertAlmostEqual(result['pairs'][0]['pitch_m'],20e-6)
            libs=[ROOT/'examples/copper_fixture/landing.lib']
            with self.assertRaisesRegex(ValueError,'supplied ground and coupling'):
                run(BINARY,source,tmp/'missing_caps.odb',config,tmp/'missing.json',native_rc=True,liberty_files=libs)
            self.assertFalse((tmp/'missing_caps.odb').exists())
            add_test_reference(config,result['geometry_sha256'])
            full=run(BINARY,source,tmp/'native.odb',config,tmp/'native.json',native_rc=True,liberty_files=libs)
            repeated=run(BINARY,tmp/'native.odb',tmp/'again.odb',config,tmp/'again.json',native_rc=True,liberty_files=libs)
            self.assertEqual(full,repeated)
            self.assertEqual(full['status'],'reference_capacitance_test_only')

if __name__=='__main__':unittest.main()
