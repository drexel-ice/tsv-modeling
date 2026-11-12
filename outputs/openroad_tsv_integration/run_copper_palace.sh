#!/usr/bin/env bash
# Extract two-TSV benchmark C, check convergence, and validate native RC/SPEF.
set -euo pipefail
TSV_WORKSPACE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TSV_TOOLS="${TSV_EM_PREFIX:-$HOME/.local/opt/tsv-em}"
TSV_OUTPUT="${1:-$TSV_WORKSPACE/work/copper_palace_extraction}"
TSV_OPENROAD="${OPENROAD_BIN:-$TSV_WORKSPACE/repos/OpenROAD/bazel-bin/openroad}"
TSV_INPUT="${TSV_ODB_INPUT:-$TSV_WORKSPACE/work/tsv_material_examples/copper_input.odb}"
if [[ ! -f "$TSV_INPUT" ]]; then
  echo "Copper input ODB missing: $TSV_INPUT. Run run_material_examples.py first or set TSV_ODB_INPUT." >&2
  exit 1
fi
PYTHONDONTWRITEBYTECODE=1 "$TSV_TOOLS/python/bin/python" \
  "$TSV_WORKSPACE/outputs/openroad_tsv_integration/em/extract_tsv_capacitance.py" \
  --openroad "$TSV_OPENROAD" \
  --palace "$TSV_TOOLS/palace_env/.spack-env/view/bin/palace" \
  --input-odb "$TSV_INPUT" --output-dir "$TSV_OUTPUT"
