"""Create a synthetic .odb fixture using the built OpenROAD executable."""
import argparse
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parent


def create(openroad, output, profile="tungsten"):
    if profile not in ("tungsten","copper"):raise ValueError("Unknown fixture profile")
    output=Path(output).resolve()
    if output.exists():raise ValueError('fixture output already exists')
    output.parent.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy()
    fixture='native_fixture' if profile=='tungsten' else 'copper_fixture'
    env.update(TSV_3DBX=str(ROOT/'examples'/fixture/'fixture.3dbx'),TSV_OUTPUT_ODB=str(output),TSV_FIXTURE_PROFILE=profile)
    result=subprocess.run([str(Path(openroad).resolve()),'-no_splash','-no_init','-exit',str(ROOT/'create_native_fixture.tcl')],
                          env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=True)
    if 'TSV_FIXTURE_PASS' not in result.stdout or not output.is_file():raise RuntimeError(result.stdout)
    return result.stdout

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--openroad',type=Path,required=True);p.add_argument('--output-odb',type=Path,required=True)
    p.add_argument('--profile',choices=['tungsten','copper'],default='tungsten')
    a=p.parse_args();print(create(a.openroad,a.output_odb,a.profile))
