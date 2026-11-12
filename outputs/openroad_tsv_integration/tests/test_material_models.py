"""Material physics and model dispatch checks; no pretend extraction data."""
import copy
import json
from math import pi
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bridge
from material_models import geometry_fingerprint

ROOT = Path(__file__).resolve().parents[1]


def copper_inputs():
    config = json.loads((ROOT/'examples/copper_config.json').read_text())
    endpoints = {}
    for i, via in enumerate(config['tsvs']):
        for name, z in [('source', 50e-6), ('target', 100e-6)]:
            identity = via[name]
            key = bridge.endpoint_key(**identity)
            endpoints[key] = dict(key=key, **identity, position_m=[(50+20*i)*1e-6, 50e-6, z],
                                  net=f'signal{i}', source='unit test geometry')
    return config, endpoints


def add_test_reference(config, fingerprint):
    """Arbitrary parser/transport vectors; not physical capacitance predictions."""
    config['model']['allow_test_capacitance'] = True
    config['reference_capacitance'] = {
        'kind': 'test_vector', 'source': 'ARTIFICIAL UNIT TEST VALUES; NOT Q3D OR MEASUREMENT',
        'geometry_sha256': fingerprint, 'unit': 'F', 'frequency_hz': 0,
        'ground_farad': {'TSV_0': 50e-15, 'TSV_1': 50e-15},
        'pair_farad': {'["TSV_0","TSV_1"]': 5e-15}}


class MaterialModelsTests(unittest.TestCase):
    def setUp(self):
        self.config, self.endpoints = copper_inputs()

    def evaluate(self):
        return bridge.evaluate(bridge.build_vias(self.endpoints, self.config), self.config)

    def test_copper_bulk_resistance_and_unknown_capacitance(self):
        result = self.evaluate()
        self.assertEqual(result['status'], 'resistance_only_capacitance_pending')
        row = result['tsvs'][0]
        expected = 50e-6/(5.8e7*pi*(2.5e-6)**2)
        self.assertAlmostEqual(row['r_ohm'], expected, places=12)
        self.assertIsNone(row['c_ground_farad'])
        self.assertIsNone(result['pairs'][0]['c_coupling_farad'])
        self.assertNotIn('l_self_dc_henry', row)

    def test_material_length_and_area_scaling(self):
        base = self.evaluate()['tsvs'][0]['r_ohm']
        for row in self.config['tsvs']:
            row['conductor'] = 'tungsten'
            row['conductivity_s_m'] = 1.82e7
        self.assertAlmostEqual(self.evaluate()['tsvs'][0]['r_ohm']/base, 5.8e7/1.82e7)
        self.config['tsvs'][0]['diameter_m'] = 10e-6
        self.assertAlmostEqual(self.evaluate()['tsvs'][0]['r_ohm']/base, 5.8e7/1.82e7/4)

    def test_does_not_reuse_tungsten_ac_fit(self):
        self.config['model']['frequency_hz'] = 1e9
        with self.assertRaisesRegex(ValueError, 'frequency_hz=0'): self.evaluate()

    def test_explicit_conductivity_and_material_metadata(self):
        del self.config['tsvs'][0]['conductivity_s_m']
        with self.assertRaisesRegex(ValueError, 'conductivity_s_m'): self.evaluate()
        self.config, self.endpoints = copper_inputs()
        key = bridge.endpoint_key(**self.config['tsvs'][0]['source'])
        with self.assertRaisesRegex(ValueError, 'conductor'):
            bridge.build_vias(self.endpoints,self.config,endpoint_metadata={key:{'conductor':'tungsten'}})

    def test_reference_capacitance_requires_binding_and_test_opt_in(self):
        add_test_reference(self.config,self.evaluate()['geometry_sha256'])
        result = self.evaluate()
        self.assertEqual(result['status'], 'reference_capacitance_test_only')
        self.assertEqual(result['tsvs'][0]['c_ground_farad'], 50e-15)
        self.assertEqual(result['pairs'][0]['c_coupling_farad'], 5e-15)
        self.config['model']['allow_test_capacitance'] = False
        with self.assertRaisesRegex(ValueError, 'explicit'): self.evaluate()
        self.config['model']['allow_test_capacitance'] = True
        good = copy.deepcopy(self.config)
        self.config['electrostatic_context']['substrate_bias_v'] = 0.5
        with self.assertRaisesRegex(ValueError, 'fingerprint'): self.evaluate()
        self.config = good
        self.config['tsvs'][0]['liner_m'] *= 2
        with self.assertRaisesRegex(ValueError, 'fingerprint'): self.evaluate()

    def test_missing_negative_or_extra_reference_values_rejected(self):
        add_test_reference(self.config,self.evaluate()['geometry_sha256'])
        good=copy.deepcopy(self.config)
        self.config['reference_capacitance']['pair_farad']={}
        with self.assertRaises(ValueError): self.evaluate()
        self.config=copy.deepcopy(good)
        self.config['reference_capacitance']['ground_farad']['TSV_0']=-1e-15
        with self.assertRaises(ValueError): self.evaluate()
        self.config=copy.deepcopy(good)
        self.config['reference_capacitance']['ground_farad']['unexpected']=0
        with self.assertRaises(ValueError): self.evaluate()

if __name__=='__main__':unittest.main()
