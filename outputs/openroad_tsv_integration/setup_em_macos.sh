#!/usr/bin/env bash
# Shared user-wide, CPU-only Palace/Gmsh setup. Run in the user's Terminal.
set -euo pipefail
TSV_WORKSPACE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TSV_TOOLS="${TSV_EM_PREFIX:-$HOME/.local/opt/tsv-em}"
if [[ "$(uname -s)" != Darwin || "$(uname -m)" != arm64 ]]; then
  echo "This installer targets native Apple Silicon macOS (arm64)." >&2
  exit 1
fi
command -v git >/dev/null
xcrun --find clang >/dev/null
TSV_PYTHON="${TSV_PYTHON:-/opt/homebrew/bin/python3.11}"
if [[ ! -x "$TSV_PYTHON" ]]; then TSV_PYTHON="$(command -v python3)"; fi
mkdir -p "$TSV_TOOLS/logs" "$TSV_WORKSPACE/work/em_setup"
exec > >(tee -a "$TSV_TOOLS/logs/install.log" "$TSV_WORKSPACE/work/em_setup/install.log") 2>&1
trap 'echo "Setup stopped at line $LINENO. See work/em_setup/install.log. Rerunning preserves completed installations." >&2' ERR
export SPACK_USER_CONFIG_PATH="$TSV_TOOLS/spack_config"
export SPACK_USER_CACHE_PATH="$TSV_TOOLS/spack_cache"
export SPACK_SYSTEM_CONFIG_PATH="$TSV_TOOLS/spack_system_config"
export PIP_CACHE_DIR="$TSV_TOOLS/pip_cache"
export PYTHONPYCACHEPREFIX="$TSV_TOOLS/pycache"
mkdir -p "$SPACK_USER_CONFIG_PATH" "$SPACK_USER_CACHE_PATH" "$SPACK_SYSTEM_CONFIG_PATH"

# Set the Spack interpreter BEFORE sourcing setup-env.sh, which otherwise picks
# the first python3 on PATH (the Python.org interpreter has no CA bundle here).
export SPACK_PYTHON="$TSV_PYTHON"
TSV_CA_BUNDLE="$("$TSV_PYTHON" "$TSV_WORKSPACE/outputs/openroad_tsv_integration/em/tls_setup.py" --print-bundle)"
export SSL_CERT_FILE="$TSV_CA_BUNDLE"
export CURL_CA_BUNDLE="$TSV_CA_BUNDLE"
export REQUESTS_CA_BUNDLE="$TSV_CA_BUNDLE"
export PIP_CERT="$TSV_CA_BUNDLE"
"$TSV_PYTHON" "$TSV_WORKSPACE/outputs/openroad_tsv_integration/em/tls_setup.py" \
  --check-network --report "$TSV_WORKSPACE/work/em_setup/tls_preflight.json"

# Official Palace instructions recommend the Spack releases/v1.2 series.
if [[ ! -d "$TSV_TOOLS/spack/.git" ]]; then
  git clone --depth=2 --branch releases/v1.2 https://github.com/spack/spack.git "$TSV_TOOLS/spack"
fi
set +u
source "$TSV_TOOLS/spack/share/spack/setup-env.sh"
set -u
spack --version
spack config --scope user add "config:ssl_certs:$TSV_CA_BUNDLE"
spack config --scope user add "config:verify_ssl:true"
spack compiler find /opt/homebrew/bin /usr/bin
mkdir -p "$TSV_TOOLS/palace_env"
# Create a reproducible environment once. Reuse its concrete lock on reruns.
"$TSV_PYTHON" - "$TSV_TOOLS" <<'PY'
from pathlib import Path
import json,sys
root=Path(sys.argv[1]);target=root/'palace_env/spack.yaml'
if not target.exists():
    data={'spack':{'specs':['palace@0.16.0~cuda'],'view':True,
                   'concretizer':{'unify':True},
                   'config':{'install_tree':{'root':str(root/'packages')},
                             'build_stage':[str(root/'build_stage')]}}}
    target.write_text(json.dumps(data,indent=2)+'\n')
PY
spack python "$TSV_WORKSPACE/outputs/openroad_tsv_integration/em/macos_compiler_setup.py" \
  --report "$TSV_WORKSPACE/work/em_setup/compiler_preflight.json" \
  --environment "$TSV_TOOLS/palace_env" --install-db "$TSV_TOOLS/packages/.spack-db/index.json"
if "$TSV_PYTHON" - "$TSV_WORKSPACE/work/em_setup/compiler_preflight.json" <<'PY_CHECK'
import json,sys
raise SystemExit(0 if json.load(open(sys.argv[1]))['reconcretize_required'] else 1)
PY_CHECK
then
  spack -e "$TSV_TOOLS/palace_env" concretize --force
  rm -f "$TSV_TOOLS/palace_env/.tsv-sdk-reconcretize-required"
else
  spack -e "$TSV_TOOLS/palace_env" concretize
fi
"$TSV_PYTHON" "$TSV_WORKSPACE/outputs/openroad_tsv_integration/em/macos_compiler_setup.py" \
  --audit-lock --environment "$TSV_TOOLS/palace_env" --install-db "$TSV_TOOLS/packages/.spack-db/index.json" \
  --report "$TSV_WORKSPACE/work/em_setup/concrete_compiler_audit.json"
spack -e "$TSV_TOOLS/palace_env" install -j "${TSV_BUILD_JOBS:-4}"
spack -e "$TSV_TOOLS/palace_env" find -dlv > "$TSV_WORKSPACE/work/em_setup/spack-specs.txt"
git -C "$TSV_TOOLS/spack" rev-parse HEAD > "$TSV_WORKSPACE/work/em_setup/spack-commit.txt"

if [[ ! -x "$TSV_TOOLS/python/bin/python" ]]; then
  "$TSV_PYTHON" -m venv "$TSV_TOOLS/python"
fi
"$TSV_TOOLS/python/bin/python" -m pip install --disable-pip-version-check 'gmsh==4.15.2'
"$TSV_TOOLS/python/bin/python" -m pip freeze > "$TSV_WORKSPACE/work/em_setup/python-packages.txt"
"$TSV_TOOLS/python/bin/python" "$TSV_WORKSPACE/outputs/openroad_tsv_integration/em/verify_installation.py" \
  --palace "$TSV_TOOLS/palace_env/.spack-env/view/bin/palace" \
  --output-dir "$TSV_WORKSPACE/work/em_verification"
"$TSV_TOOLS/python/bin/python" "$TSV_WORKSPACE/outputs/openroad_tsv_integration/em/register_user_tools.py" \
  --prefix "$TSV_TOOLS" --python "$TSV_PYTHON"
echo "Palace and Gmsh verification passed. Report: work/em_verification/installation_report.json"
echo "Shared installation: $TSV_TOOLS"
echo "Open a new Terminal, or activate this shell with: . \"$TSV_TOOLS/activate.sh\""
