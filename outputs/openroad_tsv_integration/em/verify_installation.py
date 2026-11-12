"""Verify native Apple Silicon executables and an analytical electrostatic solve."""
import argparse
import csv
import json
import math
import platform
from pathlib import Path
import shutil
import subprocess
import sys
from smoke_geometry import generate


def read_scalar_capacitance(path):
    with Path(path).open(newline='') as stream:
        rows=list(csv.reader(stream))
    rows=[[cell.strip() for cell in row] for row in rows if row]
    if len(rows)!=2 or len(rows[0])!=2 or '(F)' not in rows[0][1]:
        raise ValueError('Expected one-terminal Palace Maxwell matrix with farad units')
    if float(rows[1][0])!=1:raise ValueError('Unexpected terminal index')
    value=float(rows[1][1])
    if not math.isfinite(value) or value<=0:raise ValueError('Invalid capacitance')
    return value


def command(args, log):
    result=subprocess.run([str(arg) for arg in args],text=True,stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT,check=False)
    Path(log).write_text(result.stdout)
    if result.returncode:raise RuntimeError(f'Command failed ({result.returncode}); see {log}')
    return result.stdout


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--palace',type=Path)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    output=args.output_dir.resolve();output.mkdir(parents=True,exist_ok=True)
    report={'platform':platform.platform(),'architecture':platform.machine(),
            'python':sys.executable,'status':'not_verified','checks':{}}
    try:
        if platform.system()!='Darwin' or platform.machine()!='arm64':
            raise RuntimeError('Run this installation check natively on Apple Silicon macOS')
        import gmsh
        report['gmsh_version']=gmsh.__version__
        library=Path(gmsh.libpath).resolve()
        description=command(['/usr/bin/file','-L',library],output/'gmsh_architecture.log')
        if 'arm64' not in description:raise RuntimeError('Gmsh library is not native arm64')
        report['checks']['gmsh_native_arm64']=True
        palace=args.palace or shutil.which('palace')
        if not palace or not Path(palace).is_file():raise RuntimeError('Palace executable not found')
        palace=Path(palace).resolve();report['palace']=str(palace)
        native_binaries=list(palace.parent.glob('palace-*.bin'))
        if not native_binaries:
            raise RuntimeError('Cannot locate Palace solver binary next to launcher for architecture verification')
        architectures=[]
        for binary in native_binaries:
            architectures.append(command(['/usr/bin/file','-L',binary],output/(binary.name+'.architecture.log')))
        if not any('arm64' in value for value in architectures):
            raise RuntimeError('No native arm64 Palace solver binary found')
        report['checks']['palace_native_arm64']=True
        report['palace_binary_architectures']=architectures
        command([palace,'--help'],output/'palace_help.log')
        report['checks']['palace_help']=True
        results=[]
        for name,size in [('coarse',0.8),('fine',0.5)]:
            case=generate(output/name,size)
            command([palace,'-serial','-dry-run',case['config']],output/f'{name}_dry_run.log')
            command([palace,'-serial',case['config']],output/f'{name}_solver.log')
            value=read_scalar_capacitance(output/name/'postpro/terminal-C.csv')
            exact=case['analytic_capacitance_f']
            case.update(extracted_capacitance_f=value,relative_error=abs(value-exact)/exact)
            results.append(case)
        report['coax_cases']=results
        fine=results[-1]
        if fine['relative_error']>0.01:raise RuntimeError('Fine-mesh analytical error exceeds 1%')
        mesh_change=abs(results[0]['extracted_capacitance_f']-fine['extracted_capacitance_f'])/fine['extracted_capacitance_f']
        report['mesh_relative_change']=mesh_change
        if mesh_change>0.01:raise RuntimeError('Coarse/fine capacitance change exceeds 1%; refine before use')
        report['checks']['gmsh_real_mesh_generation']=True
        report['checks']['palace_electrostatic_solve']=True
        report['checks']['analytic_error_below_1_percent']=True
        report['checks']['mesh_change_below_1_percent']=True
        report['status']='installation_and_analytic_smoke_verified'
    except Exception as error:
        report['error']=str(error)
        print(f'VERIFICATION FAILED: {error}',file=sys.stderr)
    (output/'installation_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(output/'installation_report.json')
    if report['status']!='installation_and_analytic_smoke_verified':return 1
    print('PASS: native Gmsh mesh and Palace analytic capacitance smoke test')
    return 0


if __name__=='__main__':raise SystemExit(main())
