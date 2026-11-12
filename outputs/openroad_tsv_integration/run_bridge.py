"""Offline example or real ODB property round trip; see README.md."""
import argparse
import json
from pathlib import Path
from bridge import extract_endpoints,build_vias,evaluate,store_results,read_results,probe


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',required=True,type=Path)
    parser.add_argument('--fixture',type=Path,help='offline endpoint data; not an OpenDB test')
    parser.add_argument('--input-odb',type=Path)
    parser.add_argument('--output-odb',type=Path)
    parser.add_argument('--report',required=True,type=Path)
    args=parser.parse_args()
    config=json.loads(args.config.read_text())
    if bool(args.fixture)==bool(args.input_odb):parser.error('choose one of --fixture or --input-odb')
    if args.fixture:
        if args.output_odb:parser.error('--output-odb requires --input-odb')
        endpoints=json.loads(args.fixture.read_text())
        result=evaluate(build_vias(endpoints,config),config)
        result['verification']='offline_fixture_only'
    else:
        import odb
        if args.output_odb is None:parser.error('--output-odb is required; input is never overwritten')
        if args.input_odb.resolve()==args.output_odb.resolve():parser.error('input and output must differ')
        if args.output_odb.exists():parser.error('output already exists; choose a new output path')
        db=odb.dbDatabase.create()
        odb.read_db(db,str(args.input_odb))
        capabilities=probe(odb,db)
        endpoints,handles=extract_endpoints(db)
        result=evaluate(build_vias(endpoints,config,odb,handles),config)
        result['capabilities']=capabilities
        result['verification']='OpenDB_property_roundtrip'
        store_results(odb,db,result)
        args.output_odb.parent.mkdir(parents=True,exist_ok=True)
        odb.write_db(db,str(args.output_odb))
        reread=odb.dbDatabase.create()
        odb.read_db(reread,str(args.output_odb))
        if read_results(odb,reread)!=result:
            raise RuntimeError('OpenDB property roundtrip differs; output must not be used')
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(f'{len(result["tsvs"])} TSVs, {len(result["pairs"])} pairs; {result["verification"]}')
    print(args.report)

if __name__=='__main__':main()
