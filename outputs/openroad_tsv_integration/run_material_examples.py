"""Run the original tungsten native RC case and a separate copper DC case."""
import argparse
import json
from pathlib import Path
from make_native_fixture import create
from run_native import run

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--openroad', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if output.exists():
        raise ValueError('Choose a new output directory; existing results are preserved')
    output.mkdir(parents=True)
    summary = {}
    for material, filename, fixture in [('tungsten','native_config.json','native_fixture'),
                                         ('copper','copper_config.json','copper_fixture')]:
        source = output/f'{material}_input.odb'
        create(args.openroad, source, profile=material)
        config = json.loads((ROOT/'examples'/filename).read_text())
        result = run(args.openroad, source, output/f'{material}_results.odb', config,
                     output/f'{material}.json', native_rc=material=='tungsten',
                     liberty_files=[ROOT/'examples'/fixture/'landing.lib'])
        summary[material] = {'status':result['status'], 'native_rc_injected':result['native_rc_injected'],
                             'r_ohm':[row['r_ohm'] for row in result['tsvs']],
                             'capacitance_available':all(row['c_ground_farad'] is not None for row in result['tsvs'])}
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
    print(output/'summary.json')


if __name__=='__main__':
    main()
