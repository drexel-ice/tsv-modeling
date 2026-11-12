"""Independent checks for native topology and SPEF values."""
import copy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from native_plan import validate_graph, validate_spef, text

class NativePlanTests(unittest.TestCase):
    def setUp(self):
        self.result = {'tsvs': [{'id': v, 'r_ohm': 2., 'c_ground_farad': 4e-15} for v in ('a', 'b')],
                       'pairs': [{'pair': ['a', 'b'], 'same_net': False, 'c_coupling_farad': 6e-15}]}
        self.graph = {'cap_nodes': [dict(id=i, net=v, owner=v, spef_name=f'{v}{j}', c_ff=2.)
                                   for v, start in [('a', 1), ('b', 3)] for j, i in enumerate(range(start, start+2))],
                      'resistors': [dict(owner=v, source=i, target=i+1, r_ohm=2.) for v, i in [('a', 1), ('b', 3)]],
                      'couplings': [dict(owner=json.dumps(['a', 'b']), source=i, target=i+2, c_ff=3.) for i in (1, 2)]}
        self.spef = '*C_UNIT 1 PF\n*R_UNIT 1 KOHM\n'
        for v in ('a', 'b'):
            self.spef += f'*D_NET {v} .010\n*CAP\n1 {v}0 .002\n2 {v}1 .002\n3 a0 b0 .003\n4 a1 b1 .003\n*RES\n1 {v}0 {v}1 .002\n*END\n'

    def test_graph_and_unit_scaled_spef(self):
        self.assertEqual(validate_graph(self.graph, self.result)['coupling_elements'], 2)
        self.assertEqual(validate_spef(self.spef, self.graph, self.result)['net_sections'], 2)

    def test_wrong_endpoint_and_accumulated_elements_rejected(self):
        bad = copy.deepcopy(self.graph)
        bad['couplings'][0]['target'] = 4
        with self.assertRaises(ValueError): validate_graph(bad, self.result)
        bad = copy.deepcopy(self.graph)
        bad['resistors'].append(bad['resistors'][0])
        with self.assertRaises(ValueError): validate_graph(bad, self.result)

    def test_wrong_units_missing_coupling_and_total_rejected(self):
        for old, new in [('*C_UNIT 1 PF', '*C_UNIT 1 FF'), ('3 a0 b0 .003', ''), ('*D_NET a .010', '*D_NET a .004')]:
            with self.assertRaises(ValueError): validate_spef(self.spef.replace(old, new), self.graph, self.result)

    def test_tcl_arguments_are_inert(self):
        value = text('x]; error "injected"; # $env(HOME)')
        self.assertNotIn('injected', value)
        self.assertNotIn('$env', value)

if __name__ == '__main__': unittest.main()
