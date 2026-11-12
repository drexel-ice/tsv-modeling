"""Two uniform TSVs in a grounded dielectric enclosure; linear electrostatics.

No depletion, substrate conduction, pads or end fringing. Geometry comes from
an OpenDB export. All extraction dimensions and numerical inputs are recorded.
"""
import argparse
import csv
from hashlib import sha256
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import bridge
from material_models import geometry_fingerprint
from run_native import native,decode_snapshot,run


def read_matrix(path,count):
    with Path(path).open(newline='') as stream:rows=list(csv.reader(stream))
    if len(rows)!=count+1 or len(rows[0])!=count+1:
        raise ValueError('Unexpected Palace matrix dimensions')
    if any(''.join(cell.split())!=f'C[i][{j}](F)' for j,cell in enumerate(rows[0][1:],1)):
        raise ValueError('Expected ordered Maxwell columns with farad units')
    matrix=[]
    for index,row in enumerate(rows[1:],1):
        if len(row)!=count+1 or float(row[0])!=index:raise ValueError('Unexpected terminal order')
        values=[float(v) for v in row[1:]]
        if not all(math.isfinite(v) for v in values):raise ValueError('Nonfinite matrix')
        matrix.append(values)
    return matrix


def branch_capacitance(matrix,ids):
    n=len(ids)
    if len(matrix)!=n or any(len(row)!=n for row in matrix):raise ValueError('Matrix dimensions')
    scale=max(abs(v) for row in matrix for v in row)
    if not math.isfinite(scale) or scale<=0:raise ValueError('Invalid matrix scale')
    for i in range(n):
        if not all(math.isfinite(v) for v in matrix[i]):raise ValueError('Nonfinite matrix')
        if matrix[i][i]<=0:raise ValueError('Nonpositive diagonal')
        for j in range(i):
            if abs(matrix[i][j]-matrix[j][i])>1e-6*scale:raise ValueError('Nonreciprocal matrix')
            if max(matrix[i][j],matrix[j][i])>0:raise ValueError('Positive off diagonal')
    ground={ids[i]:sum(matrix[i]) for i in range(n)}
    if min(ground.values())<=0:raise ValueError('Nonpositive ground branch')
    pair={json.dumps([ids[i],ids[j]],separators=(',',':')):
          -(matrix[i][j]+matrix[j][i])/2 for i in range(n) for j in range(i+1,n)}
    return ground,pair


def dimensions(vias):
    if len(vias)!=2:raise ValueError('This benchmark requires exactly two TSVs')
    a,b=vias
    for field in ('diameter_m','liner_m','z_min_m','z_max_m'):
        if not math.isclose(getattr(a,field),getattr(b,field),rel_tol=1e-10,abs_tol=1e-15):
            raise ValueError('Uniform equal TSVs with matching axial ends required')
    centers=[(v.x_m*1e6,v.y_m*1e6) for v in vias]
    radius=a.diameter_m*0.5e6;liner=a.liner_m*1e6
    if math.dist(*centers)<=2*(radius+liner):raise ValueError('Overlapping liners')
    return centers,radius,liner,a.length_m*1e6


def generate(output,vias,context,near_size,far_size):
    import gmsh
    centers,radius,liner,length=dimensions(vias)
    clearance=context['ground_clearance_from_liner_um']
    xmin=min(c[0] for c in centers)-radius-liner-clearance
    xmax=max(c[0] for c in centers)+radius+liner+clearance
    ymin=min(c[1] for c in centers)-radius-liner-clearance
    ymax=max(c[1] for c in centers)+radius+liner+clearance
    output=Path(output);output.mkdir(parents=True)
    gmsh.initialize()
    try:
        gmsh.option.setNumber('General.NumThreads',2)
        gmsh.model.add('two_tsv_dielectric_enclosure');occ=gmsh.model.occ
        rectangle=occ.addRectangle(xmin,ymin,0,xmax-xmin,ymax-ymin)
        outer=[occ.addDisk(x,y,0,radius+liner,radius+liner) for x,y in centers]
        substrate,_=occ.cut([(2,rectangle)],[(2,t) for t in outer],removeTool=False)
        annuli=[]
        for (x,y),tag in zip(centers,outer):
            inner=occ.addDisk(x,y,0,radius,radius)
            annulus,_=occ.cut([(2,tag)],[(2,inner)])
            annuli+=annulus
        surfaces,_=occ.fragment(substrate,annuli)
        occ.synchronize()
        curves=[tag for dim,tag in gmsh.model.getEntities(1) if gmsh.model.getType(dim,tag) in ('Ellipse','Circle')]
        # Distance-based refinement resolves the thin liners in the cross section.
        distance=gmsh.model.mesh.field.add('Distance')
        gmsh.model.mesh.field.setNumbers(distance,'CurvesList',curves)
        gmsh.model.mesh.field.setNumber(distance,'Sampling',100)
        threshold=gmsh.model.mesh.field.add('Threshold')
        for key,value in [('InField',distance),('SizeMin',near_size),('SizeMax',far_size),('DistMin',liner),('DistMax',2.0)]:
            gmsh.model.mesh.field.setNumber(threshold,key,value)
        gmsh.model.mesh.field.setAsBackgroundMesh(threshold)
        occ.extrude(surfaces,0,0,length,numElements=[5],recombine=False)
        occ.synchronize()
        volumes=gmsh.model.getEntities(3)
        liners=[tag for dim,tag in volumes if occ.getMass(dim,tag)<math.pi*((radius+liner)**2-radius**2)*length*1.01]
        substrate=[tag for dim,tag in volumes if tag not in liners]
        if len(liners)!=2 or len(substrate)!=1:raise RuntimeError('Unexpected dielectric volumes')
        gmsh.model.addPhysicalGroup(3,liners,1);gmsh.model.addPhysicalGroup(3,substrate,2)
        terminals=[[],[]];ground=[];ends=[]
        for dim,tag in gmsh.model.getBoundary(volumes,combined=True,oriented=False):
            box=gmsh.model.getBoundingBox(dim,tag)
            if box[5]-box[2]<1e-4:ends.append(tag);continue
            if box[3]-box[0]<1e-4 or box[4]-box[1]<1e-4:ground.append(tag);continue
            x=(box[0]+box[3])/2;y=(box[1]+box[4])/2
            index=min(range(2),key=lambda i:math.dist((x,y),centers[i]))
            if abs((box[3]-box[0])/2-radius)>1e-4:raise RuntimeError('Unclassified external boundary')
            terminals[index].append(tag)
        if len(ground)!=4 or any(len(t)!=1 for t in terminals):raise RuntimeError('Unexpected enclosure boundaries')
        for attribute,tags in [(11,terminals[0]),(12,terminals[1]),(13,ground),(14,ends)]:
            gmsh.model.addPhysicalGroup(2,tags,attribute)
        gmsh.option.setNumber('Mesh.MeshSizeMax',far_size)
        gmsh.option.setNumber('Mesh.MeshSizeFromPoints',0)
        gmsh.option.setNumber('Mesh.MeshSizeFromCurvature',0)
        gmsh.option.setNumber('Mesh.MeshSizeExtendFromBoundary',0)
        gmsh.option.setNumber('Mesh.MshFileVersion',2.2)
        gmsh.model.mesh.generate(3);gmsh.model.mesh.setOrder(2)
        _,element_tags,_=gmsh.model.mesh.getElements(3)
        all_elements=[int(tag) for tags in element_tags for tag in tags]
        minimum_jacobian=float(min(gmsh.model.mesh.getElementQualities(all_elements,'minDetJac')))
        if minimum_jacobian<=0:raise RuntimeError('Invalid curved mesh: nonpositive element Jacobian')
        mesh=output/'tsv.msh';gmsh.write(str(mesh))
        nodes=len(gmsh.model.mesh.getNodes()[0])
    finally:gmsh.finalize()
    config={'Problem':{'Type':'Electrostatic','Output':str(output/'postpro')},
            'Model':{'Mesh':str(mesh),'L0':1e-6},
            'Domains':{'Materials':[{'Attributes':[1],'Permittivity':context['liner_relative_permittivity']},
                                    {'Attributes':[2],'Permittivity':context['silicon_relative_permittivity']}]},
            'Boundaries':{'Terminal':[{'Index':i+1,'Attributes':[11+i]} for i in range(2)],
                          'Ground':{'Attributes':[13]},'ZeroCharge':{'Attributes':[14]}},
            'Solver':{'Order':2,'Linear':{'Type':'BoomerAMG','KSPType':'CG','Tol':1e-10,'MaxIts':1000}}}
    filename=output/'tsv.json';filename.write_text(json.dumps(config,indent=2)+'\n')
    return {'config':str(filename),'mesh':str(mesh),'nodes':nodes,'box_um':[xmin,xmax,ymin,ymax,0,length],
            'near_mesh_um':near_size,'far_mesh_um':far_size,
            'mesh_minimum_jacobian':minimum_jacobian,'volume_elements':len(all_elements)}


def solve(palace,case,directory,prepare_only=False):
    jobs=[('dry_run',['-dry-run'])]
    if not prepare_only:jobs.append(('solve',[]))
    for name,options in jobs:
        result=subprocess.run([str(palace),'-serial',*options,case['config']],
                              text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (directory/(name+'.log')).write_text(result.stdout)
        if result.returncode:raise RuntimeError(f'Palace {name} failed; see {directory/name}.log')
    return None if prepare_only else read_matrix(directory/'postpro/terminal-C.csv',2)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--openroad',type=Path,required=True)
    parser.add_argument('--palace',type=Path,required=True)
    parser.add_argument('--input-odb',type=Path,required=True)
    parser.add_argument('--config',type=Path,default=ROOT/'examples/copper_config.json')
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--prepare-only',action='store_true',help='generate meshes and validate Palace inputs without solving or importing')
    args=parser.parse_args()
    output=args.output_dir.resolve()
    if output.exists():raise ValueError('Choose a new output directory; results are preserved')
    output.mkdir(parents=True)
    report={'status':'started','physical_validation':'linear_dielectric_enclosure_benchmark_only'}
    try:
        snapshot_file=output/'geometry.json'
        (output/'geometry_export.log').write_text(native(args.openroad.resolve(),'export',args.input_odb.resolve(),snapshot_file))
        snapshot=json.loads(snapshot_file.read_text());config=json.loads(args.config.read_text())
        endpoints,metadata=decode_snapshot(snapshot)
        vias=sorted(bridge.build_vias(endpoints,config,endpoint_metadata=metadata),key=lambda v:v.id)
        dimensions(vias)
        original_context=config.get('electrostatic_context',{})
        context={'liner_relative_permittivity':bridge.positive('liner permittivity',original_context['liner_relative_permittivity']),
                 'silicon_relative_permittivity':bridge.positive('silicon permittivity',original_context['silicon_relative_permittivity']),
                 'substrate_model':'linear_lossless_dielectric_no_depletion_or_conduction',
                 'ground_reference':'four grounded sidewalls of rectangular enclosure',
                 'ground_clearance_from_liner_um':10.0,
                 'axial_boundary':'zero_normal_displacement; uniform extrusion; no end fringing',
                 'pads_and_contacts':'excluded',
                 'legacy_via_ground_metadata':'not used to infer actual reference boundary'}
        config['electrostatic_context']=context
        report['electrostatic_context']=context
        results=[]
        for label,near,far in [('coarse',0.18,2.5),('fine',0.11,1.6)]:
            directory=output/label
            case=generate(directory,vias,context,near,far)
            matrix=solve(args.palace.resolve(),case,directory,args.prepare_only)
            if matrix is not None:
                ground,pair=branch_capacitance(matrix,[v.id for v in vias])
                case.update(maxwell_farad=matrix,ground_farad=ground,pair_farad=pair)
            results.append(case)
            report['cases']=results
            (output/'extraction_report.json').write_text(json.dumps(report,indent=2)+'\n')
        if args.prepare_only:
            report.update(status='meshes_and_palace_inputs_verified_solve_pending',electrostatic_context=context)
            print(json.dumps(report,indent=2));return
        fine=results[-1];coarse=results[0]
        changes={}
        for kind in ['ground_farad','pair_farad']:
            for key,value in fine[kind].items():
                changes[kind+':'+key]=abs(coarse[kind][key]-value)/value
        report['relative_mesh_changes']=changes
        if max(changes.values())>0.01:raise RuntimeError('Mesh convergence exceeds 1%; refine before importing')
        evidence={}
        for directory in [output/'coarse',output/'fine']:
            for path in [directory/'tsv.json',directory/'tsv.msh',directory/'postpro/terminal-C.csv',directory/'solve.log']:
                evidence[str(path.relative_to(output))]=sha256(path.read_bytes()).hexdigest()
        reference={'kind':'palace_electrostatic','source':'Palace 0.16.0 linear dielectric enclosure benchmark; extraction_report.json',
                   'geometry_sha256':geometry_fingerprint(vias,context),'unit':'F','frequency_hz':0,
                   'ground_farad':fine['ground_farad'],'pair_farad':fine['pair_farad'],
                   'evidence_sha256':evidence,'physical_validation':report['physical_validation']}
        config['reference_capacitance']=reference
        config['benchmark']['purpose']='Copper DC resistance plus Palace dielectric-enclosure capacitance'
        config['benchmark']['ground_boundary']=context['ground_reference']
        (output/'copper_palace_config.json').write_text(json.dumps(config,indent=2)+'\n')
        result=run(args.openroad,args.input_odb,output/'copper_palace.odb',config,output/'native_result.json',
                   native_rc=True,liberty_files=[ROOT/'examples/copper_fixture/landing.lib'])
        report.update(status='extracted_and_native_rc_spef_verified',reference=reference,
                      native_rc_injected=result['native_rc_injected'],r_ohm=[v['r_ohm'] for v in result['tsvs']])
    except Exception as error:
        report.update(status='failed',error=str(error));raise
    finally:(output/'extraction_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
