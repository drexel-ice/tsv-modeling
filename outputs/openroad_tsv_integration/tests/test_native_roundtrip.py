"""Run only in a real OpenDB Python runtime with an explicitly supplied design."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bridge as b

AVAILABLE=importlib.util.find_spec('odb') is not None
INPUT=os.environ.get('TSV_ODB_INPUT')
CONFIG=os.environ.get('TSV_ODB_CONFIG')

class NativeRoundtrip(unittest.TestCase):
    @unittest.skipUnless(AVAILABLE and INPUT and CONFIG,'requires odb runtime, TSV_ODB_INPUT, and TSV_ODB_CONFIG; not a live integration pass')
    def test_write_read_preserves_research_results(self):
        import odb
        db=odb.dbDatabase.create();odb.read_db(db,INPUT)
        endpoints,handles=b.extract_endpoints(db)
        cfg=json.loads(Path(CONFIG).read_text())
        result=b.evaluate(b.build_vias(endpoints,cfg,odb,handles),cfg)
        self.assertGreater(len(result['tsvs']),0)
        b.store_results(odb,db,result)
        with tempfile.TemporaryDirectory() as tmp:
            out=str(Path(tmp)/'roundtrip.odb')
            odb.write_db(db,out)
            reread=odb.dbDatabase.create();odb.read_db(reread,out)
            self.assertEqual(b.read_results(odb,reread),result)

if __name__=='__main__':unittest.main()
