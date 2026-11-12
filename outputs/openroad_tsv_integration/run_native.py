"""Use an OpenROAD executable for ODB transport and ordinary Python for equations.

Works without a compiled Python odb module. No shell interpolation or eval.
Default persistence uses a research JSON property. --native-rc additionally
inserts native RC elements and exports assembly SPEF with the patched executable.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import bridge
from native_plan import make_plan,validate_graph,validate_spef,text

ROOT=Path(__file__).resolve().parent


def decode_snapshot(snapshot):
    unit=1e-6/bridge.positive('assembly DBU per micron',snapshot['dbu_per_micron'])
    endpoints={};metadata={}
    for record in snapshot['endpoints']:
        path,pad=record['identity'];key=bridge.endpoint_key(path,pad)
        if key in endpoints:raise ValueError(f'duplicate endpoint {key}')
        xyz=record['position_dbu']
        if len(xyz)!=3:raise ValueError('expected a 3D position')
        endpoints[key]={'key':key,'chip_path':path,'pad_instance':pad,
                        'position_m':[bridge.finite('coordinate',v)*unit for v in xyz],
                        'net':None,'source':'native OpenDB unfolded global position'}
        metadata[key]=record['metadata']
    for net in snapshot['nets']:
        members=[bridge.endpoint_key(path,pad) for path,pad in net['members']]
        token=hashlib.sha256(json.dumps(sorted(members)).encode()).hexdigest()[:16]
        identity=f'{net["name"]}@{token}'
        for key in members:
            if key not in endpoints:raise ValueError('net references a missing endpoint')
            if endpoints[key]['net'] not in (None,identity):raise ValueError('endpoint has multiple net occurrences')
            endpoints[key]['net']=identity
    return endpoints,metadata


def native(openroad, mode, source, transfer, target=None, plan=None, spef=None):
    env=os.environ.copy()
    env.pop("TSV_NATIVE_PLAN",None)
    env.pop("TSV_SPEF_FILE",None)
    env.update(TSV_MODE=mode,TSV_INPUT_ODB=str(source),TSV_TRANSFER_FILE=str(transfer))
    if target is not None:env['TSV_OUTPUT_ODB']=str(target)
    if plan is not None:env['TSV_NATIVE_PLAN']=str(plan)
    if spef is not None:env['TSV_SPEF_FILE']=str(spef)
    result=subprocess.run([str(openroad),'-no_splash','-no_init','-exit',str(ROOT/'native_transport.tcl')],
                          env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=False)
    if result.returncode:
        raise RuntimeError(f"OpenROAD {mode} failed (exit {result.returncode}):\n{result.stdout}")
    marker=f'TSV_{mode.upper()}_PASS'
    if marker not in result.stdout:raise RuntimeError(result.stdout)
    return result.stdout


def run(openroad, source, target, config, report, native_rc=False, liberty_files=()):
    openroad=Path(openroad).resolve();source=Path(source).resolve();target=Path(target).resolve();report=Path(report).resolve()
    liberty_files=[Path(p).resolve() for p in liberty_files]
    if native_rc and not liberty_files:
        raise ValueError("Native SPEF import requires --liberty with the design timing libraries")
    for library in liberty_files:
        if not library.is_file(): raise ValueError(f"Liberty file not found: {library}")
    if source==target or target.exists():raise ValueError('choose a distinct, nonexistent output ODB')
    if native_rc and target.with_suffix('.bonds.spef').exists():
        raise ValueError('bond SPEF output already exists')
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='tsv-native-',dir=target.parent) as temp:
        temp=Path(temp);snapshot_file=temp/'geometry.json';result_file=temp/'results.json';readback=temp/'readback.json'
        logs=[native(openroad,'export',source,snapshot_file)]
        snapshot=json.loads(snapshot_file.read_text())
        endpoints,metadata=decode_snapshot(snapshot)
        vias=bridge.build_vias(endpoints,config,endpoint_metadata=metadata)
        result=bridge.evaluate(vias,config)
        if native_rc and (any(v['c_ground_farad'] is None for v in result['tsvs'])
                          or any(p['c_coupling_farad'] is None for p in result['pairs'])):
            raise ValueError('Native RC requires supplied ground and coupling capacitance for the material DC model; no capacitance was invented')
        for row in result['tsvs']:row['geometry']['provenance']['coordinates']='native OpenDB unfolded coordinates via Tcl'
        result['verification']='native_OpenDB_property_roundtrip_via_Tcl'
        result['transport']='OpenROAD executable -> JSON geometry -> Python equations -> OpenDB root property'
        logs.append('PYTHON_MODEL_PASS')
        plan=None
        spef=target.with_suffix('.spef')
        if native_rc:
            result['native_rc_injected']=True
            result['native_model']='pi: R, ground C/2 at each end; pair C/2 between matching ends; fF/ohm'
            result['verification']='native_RC_and_OpenDB_roundtrip_via_Tcl'
            plan=temp/'native_plan.tcl';plan.write_text(make_plan(result,endpoints))
        result_file.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
        logs.append(native(openroad,'store',source,result_file,target,plan,spef if native_rc else None))
        # Separate process verifies persisted data, not the current in-memory object.
        logs.append(native(openroad,'verify',target,readback))
        if json.loads(readback.read_text())!=result:raise RuntimeError('persisted OpenDB result differs')
        if native_rc:
            graphfile=temp/'native_graph.json'
            logs.append(native(openroad,'inspect',target,graphfile))
            graph=json.loads(graphfile.read_text())
            summary=validate_graph(graph,result)
            bonds=spef.with_suffix('.bonds.spef')
            spef_summary=validate_spef(bonds.read_text(),graph,result)
            library_plan=temp/'libraries.tcl'
            library_plan.write_text(''.join('read_liberty '+text(str(p))+'\n' for p in liberty_files))
            check_log=native(openroad,'spef_check',target,library_plan,spef=bonds)
            if any('not found' in line.lower() and 'STA-' in line for line in check_log.splitlines()):
                raise RuntimeError('SPEF readback has unresolved nodes: '+check_log)
            logs.append(check_log)
            summary['spef']=spef_summary
            summary['OpenSTA_read_spef']='passed_keep_capacitive_coupling'
            report.parent.mkdir(parents=True,exist_ok=True)
            report.with_suffix('.native_graph.json').write_text(json.dumps({'summary':summary,'graph':graph},indent=2)+'\n')
        report.parent.mkdir(parents=True,exist_ok=True)
        report.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
        report.with_suffix('.native.log').write_text('\n'.join(logs))
        report.with_suffix('.geometry.json').write_text(json.dumps(snapshot,indent=2)+'\n')
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--openroad',type=Path,required=True)
    p.add_argument('--input-odb',type=Path,required=True)
    p.add_argument('--output-odb',type=Path,required=True)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--native-rc',action='store_true',help='requires rebuilt patched OpenROAD; insert native RC and export bond SPEF')
    p.add_argument('--liberty',action='append',type=Path,default=[],help='design Liberty file; repeat for multiple libraries; required with --native-rc')
    a=p.parse_args()
    result=run(a.openroad,a.input_odb,a.output_odb,json.loads(a.config.read_text()),a.report,a.native_rc,a.liberty)
    print(f'PASS: {len(result["tsvs"])} TSVs, {len(result["pairs"])} pairs; verified in a separate OpenROAD process')
    print(a.report)

if __name__=='__main__':main()
