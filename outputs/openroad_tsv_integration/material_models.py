"""Material DC resistance plus externally supplied, geometry-bound capacitance.

The 2009 tungsten fits are preserved in tsv_models.py. This family does not
extrapolate their empirical capacitance, inductance or AC-resistance corrections.
"""
from dataclasses import asdict
from hashlib import sha256
from itertools import combinations
from math import hypot, isfinite
from pathlib import Path
import json
import tsv_models


def geometry_fingerprint(vias, context=None):
    """Bind reference capacitance to all modeled dimensions, materials and nets."""
    rows = []
    for via in sorted(vias, key=lambda item: item.id):
        row = asdict(via)
        # Storage provenance may differ between offline/native reads of one case.
        row.pop('provenance')
        rows.append(row)
    def canonical(value):
        if isinstance(value, (float, int)) and not isinstance(value, bool):
            return format(value, '.12g')
        if isinstance(value, dict):return {k: canonical(v) for k, v in value.items()}
        if isinstance(value, list):return [canonical(v) for v in value]
        return value
    return sha256(json.dumps(canonical({"vias":rows,"electrostatic_context":context}), sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _number(name, value, positive=False):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not isfinite(value):
        raise ValueError(f'{name} must be finite')
    if value < 0 or (positive and value == 0):
        raise ValueError(f'{name} has invalid sign')
    return float(value)


def evaluate_material_dc(vias, config):
    settings = config['model']
    if _number('frequency_hz', settings['frequency_hz']) != 0:
        raise ValueError('Material DC model requires frequency_hz=0; copper AC fits are not implemented')
    cutoff = _number('neighbor_cutoff_m', settings['neighbor_cutoff_m'], positive=True)
    fingerprint = geometry_fingerprint(vias, config.get("electrostatic_context"))
    reference = config.get('reference_capacitance')
    if reference is not None:
        if reference.get('geometry_sha256') != fingerprint:
            raise ValueError('Reference capacitance geometry/material/net fingerprint does not match')
        if reference.get('unit') != 'F' or _number('reference frequency_hz', reference.get('frequency_hz')) != 0:
            raise ValueError('Reference capacitance must declare F and frequency_hz=0')
        if not isinstance(reference.get('source'), str) or not reference['source'].strip():
            raise ValueError('Reference capacitance needs an explicit source')
        if reference.get('kind') not in ('q3d_extraction', 'measurement', 'test_vector', 'palace_electrostatic'):
            raise ValueError('Reference kind must be q3d_extraction, measurement, test_vector, or palace_electrostatic')
        if reference['kind']=='palace_electrostatic':
            evidence=reference.get('evidence_sha256')
            if not isinstance(evidence,dict) or not evidence or any(
                not isinstance(value,str) or len(value)!=64 or any(c not in '0123456789abcdef' for c in value)
                for value in evidence.values()):
                raise ValueError('Palace reference requires SHA256 evidence for solver inputs and outputs')
            if reference.get('physical_validation')!='linear_dielectric_enclosure_benchmark_only':
                raise ValueError('Palace v1 reference is limited to a linear dielectric enclosure benchmark')
        if reference['kind'] == 'test_vector' and settings.get('allow_test_capacitance') is not True:
            raise ValueError('Test-vector capacitance requires explicit allow_test_capacitance=true')
        if set(reference.get('ground_farad', {})) != {via.id for via in vias}:
            raise ValueError('Reference ground capacitance must cover exactly the modeled TSVs')
    individual = []
    pairs = []
    expected_pairs = set()
    for via in vias:
        if via.conductor not in ('tungsten', 'copper') or via.substrate != 'p_silicon':
            raise ValueError('Material DC benchmark supports tungsten/copper in p-type silicon')
        sigma = _number('conductivity_s_m', via.conductivity_s_m, positive=True)
        if reference is None:
            ground_c = None
        else:
            ground_c = _number('reference ground capacitance', reference['ground_farad'][via.id])
        individual.append({'id': via.id,
                           'r_ohm': tsv_models.resistance_dc(via.length_m, via.diameter_m, sigma),
                           'c_ground_farad': ground_c, 'geometry': asdict(via),
                           'resistance_model': 'uniform_cylinder_bulk_dc',
                           'conductivity_temperature_k': via.temperature_k,
                           'capacitance_model': 'supplied_reference' if reference else 'not_available'})
    for a, b in combinations(vias, 2):
        pitch = hypot(a.x_m-b.x_m, a.y_m-b.y_m)
        edge = pitch-(a.diameter_m+b.diameter_m)/2
        if edge <= 0:
            raise ValueError('Overlapping TSV conductors')
        if pitch > cutoff:
            continue
        names = sorted((a.id, b.id))
        key = json.dumps(names, separators=(',', ':'))
        expected_pairs.add(key)
        cc = None if reference is None else _number('reference pair capacitance', reference.get('pair_farad', {}).get(key))
        pairs.append({'pair': names, 'pitch_m': pitch, 'edge_spacing_m': edge,
                      'same_net': a.net == b.net, 'c_coupling_farad': cc})
    if reference is not None and set(reference.get('pair_farad', {})) != expected_pairs:
        raise ValueError('Reference pair capacitance must cover exactly the modeled neighbor pairs')
    status = 'resistance_only_capacitance_pending'
    if reference:
        status = 'reference_capacitance_test_only' if reference['kind'] == 'test_vector' else 'reference_capacitance_supplied_unvalidated'
    return {'schema': 'org.drexel.tsv.research.v1', 'status': status,
            'native_rc_injected': False, 'model_sha256': sha256(Path(__file__).read_bytes()+Path(tsv_models.__file__).read_bytes()).hexdigest(),
            'geometry_sha256': fingerprint, 'settings': settings,
            'capacitance_reference': reference, 'tsvs': individual, 'pairs': pairs, 'skipped_pairs': [],
            'limitations': ['Conductivity is supplied at the declared temperature; no automatic temperature correction',
                            'DC conductor resistance only; no contact/barrier/AC resistance or inductance model',
                            'Capacitance is supplied reference data, not a prediction from the 2009 tungsten fits',
                            'Scalar supplied capacitance does not represent substrate conductance or dynamic crosstalk',
                            'Neighbor cutoff and all surrounding conductors must match the extraction reference context',
                            'Physical validity of the reference dataset requires independent verification']}
