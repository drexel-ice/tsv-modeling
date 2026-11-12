"""Analytical coaxial-capacitor smoke geometry, mesh coordinates in micrometers."""
import json
from math import log,pi
from pathlib import Path

EPS0=8.8541878128e-12


def generate(output, mesh_size=0.65):
    import gmsh
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    a,b,length,er=1.0,5.0,10.0,3.9
    gmsh.initialize()
    try:
        gmsh.model.add('analytic_coax_smoke')
        occ=gmsh.model.occ
        outer=occ.addCylinder(0,0,0,0,0,length,b)
        inner=occ.addCylinder(0,0,0,0,0,length,a)
        volumes,_=occ.cut([(3,outer)],[(3,inner)])
        occ.synchronize()
        if len(volumes)!=1:raise RuntimeError('Coax boolean produced unexpected volumes')
        terminal=[];ground=[];ends=[]
        for dim,tag in gmsh.model.getBoundary(volumes,oriented=False):
            box=gmsh.model.getBoundingBox(dim,tag)
            if box[5]-box[2]<1e-4:
                ends.append(tag)
            elif max(abs(box[0]),abs(box[3]))<(a+b)/2:
                terminal.append(tag)
            else:ground.append(tag)
        if len(terminal)!=1 or len(ground)!=1 or len(ends)!=2:
            raise RuntimeError('Coax boundary classification failed')
        gmsh.model.addPhysicalGroup(3,[volumes[0][1]],1)
        for attribute,tags in [(11,terminal),(12,ground),(13,ends)]:
            gmsh.model.addPhysicalGroup(2,tags,attribute)
        gmsh.option.setNumber('Mesh.MeshSizeMin',mesh_size)
        gmsh.option.setNumber('Mesh.MeshSizeMax',mesh_size)
        gmsh.option.setNumber('General.NumThreads',2)
        gmsh.option.setNumber('Mesh.MshFileVersion',2.2)
        gmsh.model.mesh.generate(3)
        gmsh.model.mesh.setOrder(2)
        gmsh.model.mesh.optimize('HighOrder')
        mesh=output/'coax.msh'
        gmsh.write(str(mesh))
        nodes=len(gmsh.model.mesh.getNodes()[0])
    finally:gmsh.finalize()
    config={'Problem':{'Type':'Electrostatic','Output':str(output/'postpro')},
            'Model':{'Mesh':str(mesh),'L0':1e-6},
            'Domains':{'Materials':[{'Attributes':[1],'Permittivity':er}]},
            'Boundaries':{'Terminal':[{'Index':1,'Attributes':[11]}],
                          'Ground':{'Attributes':[12]},'ZeroCharge':{'Attributes':[13]}},
            'Solver':{'Order':2,'Linear':{'Type':'BoomerAMG','KSPType':'CG','Tol':1e-10,'MaxIts':500}}}
    filename=output/'coax.json';filename.write_text(json.dumps(config,indent=2)+'\n')
    return {'config':str(filename),'mesh':str(mesh),'node_count':nodes,
            'analytic_capacitance_f':2*pi*EPS0*er*length*1e-6/log(b/a),
            'geometry':'coax annulus: a=1 um, b=5 um, length=10 um, er=3.9',
            'boundary_conditions':'inner 1 V, outer ground, zero normal charge on axial ends'}
