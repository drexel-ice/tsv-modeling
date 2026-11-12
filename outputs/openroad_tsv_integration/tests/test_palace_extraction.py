"""Maxwell-to-branch conversion and provenance binding for the Palace adapter."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'em')]
from extract_tsv_capacitance import read_matrix,branch_capacitance,dimensions
from test_material_models import copper_inputs,add_test_reference
import bridge


class PalaceExtractionTests(unittest.TestCase):
    def test_maxwell_diagonal_is_not_ground_capacitance(self):
        matrix=[[60e-15,-10e-15],[-10e-15,70e-15]]
        ground,pair=branch_capacitance(matrix,['a','b'])
        self.assertAlmostEqual(ground['a']/1e-15,50)
        self.assertAlmostEqual(ground['b']/1e-15,60)
        self.assertAlmostEqual(pair['["a","b"]']/1e-15,10)
        # Branch network reconstructs the Maxwell terminal charge response.
        voltage=[2,-1]
        for i,name in enumerate(['a','b']):
            charge=ground[name]*voltage[i]+pair['["a","b"]']*(voltage[i]-voltage[1-i])
            self.assertAlmostEqual(charge/1e-15,sum(matrix[i][j]*voltage[j] for j in range(2))/1e-15)

    def test_invalid_or_nonreciprocal_matrix_rejected(self):
        for matrix in [[[1,.1],[.1,1]],[[1,-.1],[-.2,1]],[[1,-2],[-2,1]],[[float('nan'),0],[0,1]]]:
            with self.assertRaises(ValueError):branch_capacitance(matrix,['a','b'])

    def test_csv_units_indices_and_column_order(self):
        valid='i,C[i][1] (F),C[i][2] (F)\n1,6e-14,-1e-14\n2,-1e-14,7e-14\n'
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'matrix.csv';path.write_text(valid)
            self.assertEqual(read_matrix(path,2)[0][1],-1e-14)
            for invalid in [valid.replace('(F)','(pF)'),valid.replace('2,-1e-14','3,-1e-14'),
                            valid.replace('C[i][1]','C[i][3]')]:
                path.write_text(invalid)
                with self.assertRaises(ValueError):read_matrix(path,2)

    def test_palace_provenance_remains_bound_to_boundary_context(self):
        config,endpoints=copper_inputs()
        vias=bridge.build_vias(endpoints,config)
        add_test_reference(config,bridge.evaluate(vias,config)['geometry_sha256'])
        config['model'].pop('allow_test_capacitance')
        reference=config['reference_capacitance'];reference.update(kind='palace_electrostatic',
            source='UNIT TEST provenance only; no solver results',
            evidence_sha256={'test_input':'a'*64},
            physical_validation='linear_dielectric_enclosure_benchmark_only')
        self.assertEqual(bridge.evaluate(vias,config)['capacitance_reference']['kind'],'palace_electrostatic')
        good=copy.deepcopy(config)
        config['electrostatic_context']['ground_boundary']='changed'
        with self.assertRaisesRegex(ValueError,'fingerprint'):bridge.evaluate(vias,config)
        config=good;config['reference_capacitance']['evidence_sha256']={}
        with self.assertRaisesRegex(ValueError,'evidence'):bridge.evaluate(vias,config)

    def test_nonuniform_geometry_rejected(self):
        config,endpoints=copper_inputs();vias=bridge.build_vias(endpoints,config)
        self.assertAlmostEqual(dimensions(vias)[3],50)
        config['tsvs'][1]['liner_m']*=2
        with self.assertRaisesRegex(ValueError,'equal TSVs'):
            dimensions(bridge.build_vias(endpoints,config))


if __name__=='__main__':unittest.main()
