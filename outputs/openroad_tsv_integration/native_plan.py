"""Generate inert Tcl arguments and independently validate persisted native RC."""
import base64
import json
import math


def text(value):
    encoded=base64.b64encode(value.encode()).decode()
    return '[encoding convertfrom utf-8 [binary decode base64 {'+encoded+'}]]'


def path_arg(path):
    return '[list '+' '.join(text(p) for p in path)+']'


def make_plan(result,endpoints):
    lines=['# Generated argument list; model/source identifiers are base64 encoded.']
    for row in result['tsvs']:
        geo=row['geometry'];a=endpoints[geo['source']];b=endpoints[geo['target']]
        if a['position_m'][2]>b['position_m'][2]:a,b=b,a
        if len(a['chip_path'])!=1 or len(b['chip_path'])!=1:
            raise ValueError('Native RC v1 requires direct children of the top chip')
        lines.append('tsv::plan_via '+' '.join((text(row['id']),path_arg(a['chip_path']),text(a['pad_instance']),
                     path_arg(b['chip_path']),text(b['pad_instance']),repr(row['r_ohm']),repr(row['c_ground_farad']*1e15))))
    for pair in result['pairs']:
        if not pair['same_net']:
            lines.append('tsv::plan_pair '+' '.join((text(pair['pair'][0]),text(pair['pair'][1]),repr(pair['c_coupling_farad']*1e15))))
    return '\n'.join(lines)+'\n'


def close(actual,expected,label):
    if not math.isclose(actual,expected,rel_tol=2e-6,abs_tol=1e-9):
        raise ValueError(f'{label}: persisted {actual} differs from {expected}')


def validate_graph(graph,result):
    expected={v['id']:v for v in result['tsvs']}
    caps={k:[] for k in expected};resistors={}
    for cap in graph['cap_nodes']:
        if cap['owner'] in expected:caps[cap['owner']].append(cap)
    for res in graph['resistors']:
        if res['owner'] in expected:
            if res['owner'] in resistors:raise ValueError('duplicate native resistor')
            resistors[res['owner']]=res
    for vid,row in expected.items():
        if len(caps[vid])!=2 or vid not in resistors:raise ValueError('native pi topology is incomplete')
        ids={c['id'] for c in caps[vid]}
        res=resistors[vid]
        if ids!={res['source'],res['target']}:raise ValueError('native resistor endpoints differ')
        close(res['r_ohm'],row['r_ohm'],'R')
        for cap in caps[vid]:close(cap['c_ff'],row['c_ground_farad']*1e15/2,'ground C / 2')
    expected_pairs={tuple(p['pair']):p for p in result['pairs'] if not p['same_net']}
    actual_pairs={key:[] for key in expected_pairs}
    for cap in graph['couplings']:
        if not cap['owner']:continue
        key=tuple(json.loads(cap['owner']))
        if key not in actual_pairs:raise ValueError('unexpected owned coupling')
        actual_pairs[key].append(cap)
    for key,pair in expected_pairs.items():
        values=actual_pairs[key]
        if len(values)!=2:raise ValueError('expected two endpoint coupling capacitors')
        a,b=(resistors[k] for k in key)
        correct={frozenset((a['source'],b['source'])),frozenset((a['target'],b['target']))}
        found={frozenset((c['source'],c['target'])) for c in values}
        if found!=correct:raise ValueError('coupling does not connect matching TSV ends')
        for cap in values:close(cap['c_ff'],pair['c_coupling_farad']*1e15/2,'coupling C / 2')
    return {'tsv_pi_networks':len(expected),'ground_cap_nodes':2*len(expected),
            'coupling_elements':2*len(expected_pairs),'status':'native_graph_verified'}


def validate_spef(content,graph,result):
    """Check serialized R, ground C, coupling C, and D_NET totals independently."""
    cap_scale=res_scale=None
    nets={};current=None;section=None
    for line in content.splitlines():
        fields=line.split()
        if not fields:continue
        if fields[0]=='*C_UNIT':cap_scale=float(fields[1])*{'FF':1,'PF':1e3,'NF':1e6,'F':1e15}[fields[2]]
        elif fields[0]=='*R_UNIT':res_scale=float(fields[1])*{'OHM':1,'KOHM':1e3}[fields[2]]
        elif fields[0]=='*D_NET':
            current={'total':float(fields[2]),'ground':{},'coupling':[],'resistors':[]}
            nets[fields[1]]=current;section=None
        elif fields[0] in ('*CAP','*RES','*CONN','*END'):section=fields[0]
        elif fields[0].startswith('*'):continue
        elif current is not None and section=='*CAP':
            if len(fields)==3:current['ground'][fields[1]]=float(fields[2])
            elif len(fields)==4:current['coupling'].append((frozenset(fields[1:3]),float(fields[3])))
            else:raise ValueError('invalid SPEF capacitor record')
        elif current is not None and section=='*RES':
            if len(fields)!=4:raise ValueError('invalid SPEF resistor record')
            current['resistors'].append((frozenset(fields[1:3]),float(fields[3])))
    if cap_scale is None or res_scale is None:raise ValueError('SPEF unit header missing')
    node_by_id={n['id']:n for n in graph['cap_nodes']}
    selected={r['id'] for r in result['tsvs']}
    for node in graph['cap_nodes']:
        if node['owner'] in selected:
            actual=nets[node['net']]['ground'].get(node['spef_name'],0)*cap_scale
            close(actual,node['c_ff'],'SPEF ground C')
    for resistor in graph['resistors']:
        if resistor['owner'] not in selected:continue
        a=node_by_id[resistor['source']];b=node_by_id[resistor['target']]
        matches=[v*res_scale for edge,v in nets[a['net']]['resistors'] if edge==frozenset((a['spef_name'],b['spef_name']))]
        if len(matches)!=1:raise ValueError('SPEF resistor missing or duplicated')
        close(matches[0],resistor['r_ohm'],'SPEF R')
    for coupling in graph['couplings']:
        if not coupling['owner']:continue
        a=node_by_id[coupling['source']];b=node_by_id[coupling['target']]
        edge=frozenset((a['spef_name'],b['spef_name']))
        for netname in (a['net'],b['net']):
            matches=[v*cap_scale for key,v in nets[netname]['coupling'] if key==edge]
            if len(matches)!=1:raise ValueError('SPEF coupling missing or duplicated within a net')
            close(matches[0],coupling['c_ff'],'SPEF coupling C')
    for net in nets.values():
        expected=(sum(net['ground'].values())+sum(v for _,v in net['coupling']))*cap_scale
        close(net['total']*cap_scale,expected,'SPEF D_NET total')
    return {'status':'SPEF_values_and_totals_verified','net_sections':len(nets)}
