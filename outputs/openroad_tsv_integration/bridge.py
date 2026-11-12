"""Research-stage OpenDB/TSV bridge. Python 3.10+, no third-party dependencies.

No compiled OpenDB module is imported here; inject the module from OpenROAD.
The default write path stores SI results as a namespaced property on the root
chip. run_native.py provides checked native RC injection with the patched CLI.
"""
from dataclasses import dataclass, asdict
from itertools import combinations
from math import isclose, hypot, isfinite
import hashlib
import json
import tsv_models as models

SCHEMA = 'org.drexel.tsv.research.v1'
RESULT_PROPERTY = SCHEMA + '.results'


@dataclass(frozen=True)
class Via:
    id: str
    source: str
    target: str
    net: str
    x_m: float
    y_m: float
    z_min_m: float
    z_max_m: float
    diameter_m: float
    liner_m: float
    ground_spacing_m: float
    ground_reference: str
    conductor: str
    substrate: str
    acceptors_cm3: float
    intrinsic_cm3: float
    temperature_k: float
    provenance: dict
    conductivity_s_m: float | None = None

    @property
    def length_m(self):
        return self.z_max_m-self.z_min_m


def positive(name, value):
    if isinstance(value, bool) or not isinstance(value,(int,float)) or not isfinite(value) or value<=0:
        raise ValueError(f'{name} must be a finite positive number')
    return float(value)


def finite(name, value):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not isfinite(value):
        raise ValueError(f'{name} must be finite')
    return float(value)


def same_object(a,b):
    # SWIG may materialize distinct Python wrappers for one native object.
    return a is b or (a is not None and b is not None and a.getId()==b.getId())


def endpoint_key(chip_path, pad_instance):
    # JSON arrays avoid collisions between names containing hierarchy delimiters.
    return json.dumps([list(chip_path),pad_instance],separators=(',',':'))


def point_components(point):
    """odb::Point3D uses x(), y(), z(); tuple permitted for binding variations."""
    if isinstance(point,(tuple,list)) and len(point)==3:
        return point
    return point.x(),point.y(),point.z()


def probe(odb_module, db):
    checks={
        'database': {name:hasattr(db,name) for name in (
            'getChip','getDbuPerMicron','constructUnfoldedModel',
            'getUnfoldedChipBumpInsts','getUnfoldedChipNets')},
        'classes': {name:hasattr(odb_module,name) for name in (
            'dbDoubleProperty','dbStringProperty','dbChipCapNode','dbChipRSeg',
            'dbChipCCSeg','dbCCSeg')},
    }
    return checks


def extract_endpoints(db):
    """Read occurrence-specific positions and logical nets from unfolded ODB."""
    for method in ('getDbuPerMicron','constructUnfoldedModel','getUnfoldedChipBumpInsts','getUnfoldedChipNets'):
        if not hasattr(db,method):
            raise RuntimeError(f'OpenDB Python binding lacks {method}; inspect the selected checkout')
    db.constructUnfoldedModel()
    dbu=positive('assembly DBU per micron',db.getDbuPerMicron())
    meters_per_dbu=1e-6/dbu
    endpoints={};handles={}
    for unfolded in db.getUnfoldedChipBumpInsts():
        raw=unfolded.getChipBumpInst()
        bump=raw.getChipBump()
        inst=bump.getInst()
        if inst is None:continue
        parent=unfolded.getParentRegion().getParentChip()
        path=[p.getName() for p in parent.getChipInstPath()]
        key=endpoint_key(path,inst.getName())
        if key in endpoints:raise ValueError(f'ambiguous endpoint {key}')
        coords=[finite('global coordinate',v)*meters_per_dbu for v in point_components(unfolded.getGlobalPosition())]
        endpoints[key]={'key':key,'chip_path':path,'pad_instance':inst.getName(),
                        'position_m':coords,'net':None,'source':'OpenDB unfolded global position'}
        handles[key]={'unfolded':unfolded,'raw_bump':raw,'pad_instance':inst,'bump':bump}
    for unet in db.getUnfoldedChipNets():
        net=unet.getChipNet()
        # Recover this net occurrence's exact endpoint set, not just a master net name.
        members=[]
        for unfolded in unet.getConnectedBumps():
            inst=unfolded.getChipBumpInst().getChipBump().getInst()
            parent=unfolded.getParentRegion().getParentChip()
            key=endpoint_key([p.getName() for p in parent.getChipInstPath()],inst.getName())
            if key in endpoints:members.append(key)
        token=hashlib.sha256(json.dumps(sorted(members)).encode()).hexdigest()[:16]
        identity=f'{net.getName()}@{token}'
        for key in members:
            if endpoints[key]['net'] not in (None,identity):
                raise ValueError(f'endpoint {key} belongs to multiple chip net occurrences')
            endpoints[key]['net']=identity
            handles[key]['chip_net']=net
    return endpoints,handles


def read_numeric(odb_module, owner, name):
    prop=odb_module.dbDoubleProperty.find(owner,SCHEMA+'.'+name)
    return None if prop is None else prop.getValue()


def build_vias(endpoints, config, odb_module=None, handles=None, endpoint_metadata=None):
    """Require conductor endpoints; pad centers alone do not establish TSV geometry.

    Diameter/liner/ground parameters come from selected endpoint's double properties
    when available, otherwise the explicit per-via config. Neither a pad bounding
    box nor die thickness is silently substituted.
    """
    vias=[];used=set();ids=set()
    for spec in config['tsvs']:
        if spec.get('kind')!='cylindrical_tsv' or spec.get('endpoints_are_conductor_ends') is not True:
            raise ValueError('TSV classification and conductor-end confirmation required')
        vid=spec['id']
        if not isinstance(vid,str) or not vid or vid in ids:raise ValueError('TSV ids must be unique nonempty strings')
        ids.add(vid)
        sk=endpoint_key(spec['source']['chip_path'],spec['source']['pad_instance'])
        tk=endpoint_key(spec['target']['chip_path'],spec['target']['pad_instance'])
        if sk==tk or sk in used or tk in used:raise ValueError('distinct, nonshared TSV endpoints required in v1')
        used.update((sk,tk))
        a,b=endpoints[sk],endpoints[tk]
        if not a['net'] or a['net']!=b['net']:raise ValueError(f'{vid}: endpoints must share a chip net occurrence')
        ax,ay,az=a['position_m'];bx,by,bz=b['position_m']
        # Prototype supports parallel TSVs along assembly Z only.
        if not isclose(ax,bx,abs_tol=1e-12) or not isclose(ay,by,abs_tol=1e-12):
            raise ValueError(f'{vid}: endpoints are not vertically aligned')
        provenance={'coordinates':'OpenDB unfolded coordinates' if handles is not None else 'offline fixture',
                    'classification':'explicit config','source':sk,'target':tk}
        values={}
        for name in ('diameter_m','liner_m','ground_spacing_m','acceptors_cm3','intrinsic_cm3','temperature_k','conductivity_s_m'):
            val=None
            if endpoint_metadata is not None:
                val=endpoint_metadata.get(sk,{}).get(name)
                if val is not None and name in spec and not isclose(val,spec[name],rel_tol=1e-10):
                    raise ValueError(f'{vid}: config conflicts with ODB property {name}')
            if odb_module is not None and handles is not None:
                val=read_numeric(odb_module,handles[sk]['pad_instance'],name)
                if val is not None and name in spec and not isclose(val,spec[name],rel_tol=1e-10):
                    raise ValueError(f'{vid}: config conflicts with ODB property {name}')
            if name=='conductivity_s_m' and val is None and name not in spec:
                continue
            provenance[name]='OpenDB namespaced double property' if val is not None else 'explicit config'
            if val is None:val=spec.get(name)
            values[name]=positive(name,val)
        positive('TSV length',abs(bz-az))
        for field in ('ground_reference','conductor','substrate'):
            stored=None if endpoint_metadata is None else endpoint_metadata.get(sk,{}).get(field)
            if odb_module is not None and handles is not None:
                prop=odb_module.dbStringProperty.find(handles[sk]['pad_instance'],SCHEMA+'.'+field)
                if prop is not None:stored=prop.getValue()
            if stored is not None and stored!=spec.get(field):
                raise ValueError(f'{vid}: config conflicts with ODB property {field}')
            if not isinstance(spec.get(field),str) or not spec[field]:raise ValueError(f'{vid}: missing {field}')
        if values['acceptors_cm3']<=values['intrinsic_cm3']:raise ValueError('acceptors must exceed intrinsic concentration')
        vias.append(Via(vid,sk,tk,a['net'],ax,ay,min(az,bz),max(az,bz),
                        **values,ground_reference=spec['ground_reference'],conductor=spec['conductor'],
                        substrate=spec['substrate'],provenance=provenance))
    return vias


def evaluate(vias, config):
    settings=config['model']
    family=settings.get('family','ted2009_tungsten')
    if family=='material_dc_reference_c':
        from material_models import evaluate_material_dc
        return evaluate_material_dc(vias,config)
    if family!='ted2009_tungsten':raise ValueError(f'Unknown model family: {family}')
    if settings.get('allow_unreconciled_capacitance') is not True:
        raise ValueError('Capacitance is unreconciled: explicit research opt-in required')
    ground=settings['ground_convention'];coupling=settings['coupling_convention']
    frequency=finite('frequency_hz',settings['frequency_hz'])
    if frequency<0:raise ValueError('frequency must be >=0')
    cutoff=positive('neighbor_cutoff_m',settings['neighbor_cutoff_m'])
    individual=[];pairs=[];skipped=[]
    for v in vias:
        if v.conductor!='tungsten' or v.substrate!='p_silicon':
            raise ValueError(f'{v.id}: this model adapter is restricted to tungsten in p-type silicon; no copper/HBT extrapolation')
        if v.conductivity_s_m is not None and not isclose(v.conductivity_s_m,models.SIGMA_W,rel_tol=1e-10):
            raise ValueError('The TED tungsten fit has fixed conductivity; use material_dc_reference_c for other conductivity values')
        # Audit calibration domain instead of accepting every positive geometry.
        ar=v.length_m/v.diameter_m
        if not .5-1e-10<=ar<=9+1e-10 or not 20e-6-1e-12<=v.diameter_m<=60e-6+1e-12:
            raise ValueError(f'{v.id}: outside audited diameter/aspect-ratio envelope')
        r=models.resistance(v.length_m,v.diameter_m,frequency)
        c=models.capacitance_ground(v.length_m,v.diameter_m,v.ground_spacing_m,v.liner_m,
                    convention=ground,acceptors_cm3=v.acceptors_cm3,intrinsic_cm3=v.intrinsic_cm3,temperature_k=v.temperature_k)
        vals={'id':v.id,'r_ohm':r,'c_ground_farad':c,
              'l_self_dc_henry':models.self_inductance(v.length_m,v.diameter_m,'dc'),
              'l_self_asymptotic_henry':models.self_inductance(v.length_m,v.diameter_m,'asymptotic'),
              'geometry':asdict(v)}
        if any(not isfinite(vals[k]) or vals[k]<0 for k in ('r_ohm','c_ground_farad','l_self_dc_henry','l_self_asymptotic_henry')):
            raise ValueError(f'{v.id}: model returned invalid parasitic')
        individual.append(vals)
    for a,b in combinations(vias,2):
        pitch=hypot(a.x_m-b.x_m,a.y_m-b.y_m)
        if pitch>cutoff:continue
        names=sorted((a.id,b.id))
        compatible=(a.ground_reference==b.ground_reference and all(isclose(x,y,rel_tol=1e-9,abs_tol=1e-15) for x,y in
                    ((a.z_min_m,b.z_min_m),(a.z_max_m,b.z_max_m),(a.diameter_m,b.diameter_m),(a.ground_spacing_m,b.ground_spacing_m))))
        if not compatible:
            skipped.append({'pair':names,'reason':'unsupported unequal diameter, Z interval, ground spacing or reference'})
            continue
        edge=pitch-(a.diameter_m+b.diameter_m)/2
        if edge<=0:raise ValueError(f'overlapping TSV conductors: {names}')
        cc=models.capacitance_coupling(a.length_m,a.diameter_m,edge,a.ground_spacing_m,convention=coupling)
        if not isfinite(cc) or cc<0:raise ValueError(f'{names}: coupling fit is negative/nonfinite')
        pairs.append({'pair':names,'pitch_m':pitch,'edge_spacing_m':edge,
                      'same_net':a.net==b.net,'c_coupling_farad':cc,
                      'l_mutual_dc_henry':models.mutual_inductance(a.length_m,a.diameter_m,pitch,'dc'),
                      'l_mutual_asymptotic_henry':models.mutual_inductance(a.length_m,a.diameter_m,pitch,'asymptotic')})
    from pathlib import Path
    model_hash=hashlib.sha256(Path(models.__file__).read_bytes()).hexdigest()
    return {'schema':SCHEMA,'status':'research_unreconciled_capacitance',
            'native_rc_injected':False,'model_sha256':model_hash,
            'settings':settings,'tsvs':individual,'pairs':pairs,'skipped_pairs':skipped,
            'limitations':['No TSV/HBT equivalence assumed','No multi-body electrostatic correction',
                          'Neighbor cutoff truncates pair enumeration','No new Q3D validation',
                          'Model fits restricted to original silicon/oxide constants; no SI correction endorsed']}


def store_results(odb_module, db, results):
    """Persistent folded-root property, keyed by full occurrence endpoint paths.

    Updates one owned property idempotently; no accumulation or RC replacement.
    Re-read .odb and call read_results to verify persistence in a real runtime.
    """
    root=db.getChip()
    if root is None:raise ValueError('no top chip')
    text=json.dumps(results,sort_keys=True,separators=(',',':'),allow_nan=False)
    cls=odb_module.dbStringProperty
    prop=cls.find(root,RESULT_PROPERTY)
    if prop is None:
        prop=cls.create(root,RESULT_PROPERTY,text)
        if prop is None:raise RuntimeError('unable to create results property; check name/type collision')
    else:prop.setValue(text)
    return text


def read_results(odb_module, db):
    prop=odb_module.dbStringProperty.find(db.getChip(),RESULT_PROPERTY)
    if prop is None:raise ValueError('results property missing')
    return json.loads(prop.getValue())
