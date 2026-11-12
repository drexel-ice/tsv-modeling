"""Test real Palace CSV parsing, not a mocked solver or mesh execution."""
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'em'))
from verify_installation import read_scalar_capacitance

class VerificationParserTests(unittest.TestCase):
    def parse(self,content):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'terminal-C.csv';p.write_text(content)
            return read_scalar_capacitance(p)

    def test_documented_palace_csv(self):
        self.assertEqual(self.parse('i, C[i][1] (F)\n1.00e+00,+1.3e-15\n'),1.3e-15)

    def test_wrong_units_and_terminal_count_rejected(self):
        for content in ['i,C[i][1] (pF)\n1,1.3\n','i,C[i][1] (F),C[i][2] (F)\n1,1e-15,-1e-16\n2,-1e-16,1e-15\n']:
            with self.assertRaises(ValueError):self.parse(content)

    def test_nonphysical_scalar_and_wrong_index_rejected(self):
        for value,index in [('nan',1),('inf',1),('-1e-15',1),('0',1),('1e-15',2)]:
            with self.assertRaises(ValueError):self.parse(f'i,C[i][1] (F)\n{index},{value}\n')

if __name__=='__main__':unittest.main()
