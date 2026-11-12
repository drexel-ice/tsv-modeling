# Palace and Gmsh on Apple Silicon

## Current inspection

The inspected Mac reports native `arm64` macOS. Homebrew, Apple command-line
tools, Python 3.11, and GNU Fortran are available. Palace, Gmsh, Spack, CMake,
and MPI were not found in the checked command paths or Homebrew inventory.
Docker Desktop is present but its engine is not running.

The execution sandbox cannot resolve GitHub and cannot install into system
package locations. No successful Palace or Gmsh installation is claimed.
`work/em_preflight/installation_report.json` records the actual failed probe:
Gmsh's Python module is absent.

## Run the shared user-wide installer

In the user's Terminal:

```sh
cd /path/to/tsv-modeling
bash outputs/openroad_tsv_integration/setup_em_macos.sh
```

This uses the official Spack releases/v1.2 series, requests Palace 0.16.0 with
CUDA disabled, and installs Gmsh 4.15.2 in a dedicated Python virtual environment.
Spack builds the required dependency stack, including CMake and MPI as needed.
Packages, build stages, and caches live under `~/.local/opt/tsv-em/`, independent
of this project. The installer registers `palace`, `gmsh`, `spack`, and
`tsv-em-python` in `~/.local/bin/`, then adds a managed activation block to the
user's shell profile (`~/.zshrc` for the current zsh shell, or `~/.bash_profile`
for bash). It backs up an existing profile before changes, preserves its other
settings, and refuses to overwrite unmanaged command wrappers. It does not
replace the system `python` or `python3`, use sudo, or change OpenROAD. Four build jobs are requested
by default; `TSV_BUILD_JOBS` can override that choice.

The installer preserves the concrete Spack lock and completed installations on
reruns. It records the Spack commit, package specifications, and Python package
versions under `work/em_setup/`. Its complete console log is
`~/.local/opt/tsv-em/logs/install.log`, with a copy at `work/em_setup/install.log`. If concretization or a build fails, use that log to
resolve the actual dependency/compiler error; do not silently change versions.
The Spack source/package repository is fetched over the network, so version
availability and the full build are not locally validated yet.

After the installer passes, open a new Terminal or activate the current shell:

```sh
source "$HOME/.local/opt/tsv-em/activate.sh"
```

The commands then work from any folder. `spack load` is available through the
sourced Spack shell integration. Use `tsv-em-python` when a Python script imports
Gmsh; this selects the shared Gmsh environment without changing your default
Python. This is global for your user account, not an administrator-level install
for every macOS account. The full tools remain usable if the project is moved.
The analytical verification scripts and results remain part of the project.

## Python certificate bootstrap fix

The first installation attempt cloned Spack 1.2.2 and detected the compilers,
but bootstrap downloads failed TLS verification. Spack had selected the Python.org
3.10 interpreter, whose default CA file is missing on this host. The initial
installer selected Homebrew Python for Gmsh but did not pin Spack's interpreter.

The corrected installer exports `SPACK_PYTHON` before sourcing Spack and selects
a valid trusted CA bundle. It enables Spack certificate verification, persists
`config:ssl_certs` in this shared Spack configuration, and supplies the same CA
bundle to Python, curl, and pip subprocesses. The shared shell registration also
retains the chosen Spack interpreter. Certificate and hostname checks remain
mandatory.

A new HTTPS preflight checks GitHub, the Spack mirror and the bootstrap registry
before concretization. Its result is `work/em_setup/tls_preflight.json`. The
local CA validation passed using Homebrew Python 3.11 and 193 trusted CAs. Three
TLS setup tests passed, including rejection of missing and malformed bundles.
Actual network verification still runs in the user's Terminal because the
execution sandbox cannot resolve the download hosts.

Rerun the same installer command; do not delete the Spack checkout or completed
downloads. If a network needs an institution-provided CA bundle, explicitly set
`TSV_CA_BUNDLE` to its trusted PEM file. The installer does not disable SSL
verification or download a replacement CA file from an unverified connection.

## Apple Clang standard C++ header fix

The next user run passed the verified HTTPS checks and began compiling the
Palace dependencies. Berkeley DB, libCEED and ncurses then failed to compile
C++ because Apple Clang could not find standard headers (`iostream`, `cerrno`,
`sstream`, `exception`). This same failure was reproduced with `/usr/bin/clang++`
outside Spack. The headers exist in the selected macOS SDK, but are absent from
the toolchain include directory that this compiler searches by default.

The corrected installer runs `em/macos_compiler_setup.py` through Spack's Python
interface after compiler detection. It first compiles, links and runs a small
C++17 program with the existing compiler flags. If that fails, it tests an explicit
`-isystem <SDK>/usr/include/c++/v1` include. The actual host probe passed with this
flag, and both libCEED C++ translation units that reported missing headers also
passed syntax checks with it.

The initial fix updates the shared Spack user configuration's Apple Clang
`extra_attributes.flags`; the correction below also adds an explicit environment
requirement. Existing flags are preserved; system compilers, SDK files, shell-wide
include paths and OpenROAD are not modified. A temporary workspace configuration
was used to test the actual Spack configuration API. The host's shared compiler
configuration will be updated by the user's installer run.

When flags change, the previous `spack.lock` is backed up and the dependency
solution is regenerated with `concretize --force`. A small owned marker retains
that requirement across interrupted attempts until concretization succeeds.
Downloads and compatible installed packages are reused; dependencies whose
compiler flags changed may rebuild. Do not delete the installation or download
cache. The report is `work/em_setup/compiler_preflight.json`.

The optimizer's loop-vectorization warnings and the configure warnings about
optional/platform features did not cause these failures. The fatal missing C++
headers did. Full dependency rebuild and Palace/Gmsh verification remain pending.

## Ensuring the SDK fix reaches actual dependency builds

The subsequent run revealed that compiler defaults were saved correctly but the
concrete dependency plan reused an older external Apple Clang record. Its C++
package entries still had empty `cxxflags`. The repeated missing-header errors
were the same failure, not a new source incompatibility.

The installer now adds an explicit conditional requirement in this environment:

```yaml
packages:
  all:
    require:
    - spec: cxxflags="-isystem /selected/SDK/usr/include/c++/v1"
      when: '%cxx=apple-clang'
```

This applies directly to every package using Apple Clang for C++, including
C++-only dependencies such as MFEM. It avoids relying on cached compiler defaults
or propagation that depends on identical sets of compiler languages. Existing
root specs, package requirements and options are preserved. The environment YAML
is backed up before changes, then reconcretized with `--force`. Old package
specs lacking the required flags cannot satisfy the new requirement.

Before any dependency compilation, the installer inspects the actual
`spack.lock`. Every non-external C++ package using Apple Clang that still needs a build must
contain the SDK include in its concrete `cxxflags`. Missing flags stop the installer with
package names and write `work/em_setup/concrete_compiler_audit.json`.
A successful standalone compiler probe alone is no longer accepted as evidence
that build flags were applied.

Verification completed locally:

- Five flag/requirement/lockfile unit checks pass, including stale-plan rejection.
- The current stale lockfile is rejected by the actual audit.
- The installed Spack 1.2.2 parser accepts both the requirement and compiler-role
  condition; writing the requirement is idempotent using its actual Python API.
- A real compile, link and execution passes through the installed Spack compiler
  wrapper with `SPACK_CXXFLAGS` set to the SDK include, using the failed libCEED
  build's compiler environment and workspace logs.

Full dependency reconcretization and rebuilding with this corrected configuration
remain pending the user's installer run. No full-install success is claimed.
The existing installation and downloads are retained; packages requiring changed
flags may rebuild. System compiler and SDK files are not changed.

## Reusing already installed dependencies

The next stop was an audit false positive, before compilation started. Eight
packages (`bison`, `expat`, `libffi`, `m4`, `nghttp2`, `openblas`, `zlib-ng`,
`zstd`) had no SDK flags in their older concrete records but were already
successfully installed. They do not compile again during this installer run.
Compiler-role metadata alone is not evidence that an installed package needs
new C++ compilation.

The audit now consults this installation's Spack database. It skips a package
only when its full concrete hash matches an installed record, `installed` is
true, and the recorded prefix directory exists. Wrong hashes, failed/incomplete
installs and missing prefix directories cannot bypass the SDK flag check.
The report lists reused installed packages separately.

The corrected audit passes against the actual current lockfile and install DB:
27 C++ packages needing builds have SDK flags, and eight installed packages are
reused. Seven audit/configuration unit checks pass. This verifies the plan and
reuse decision; actual remaining package builds and Palace/Gmsh numerical
verification still need to complete. The current lock no longer needs to be
regenerated solely because of those eight installed packages.

## OpenSSH build failure with the macOS SDK

The latest retry passed the C++ header checks and reached OpenSSH 10.3p1.
Its source emitted a deprecated `sandbox_init` warning and failed because
`kSBXProfilePureComputation` is absent from the selected SDK. OpenMPI uses
OpenSSH as a runtime dependency. The Mac already provides executable
`/usr/bin/ssh` and `/usr/bin/scp`; the detected SSH version is 10.3p1.

The preflight now registers that detected version in the Palace environment as
an external package with `prefix: /usr` and `buildable: false`. It backs up the
environment and requests reconcretization. A pre-build audit rejects a plan
that still builds OpenSSH from source. No SSH connections are made and no
system SSH files or sandbox settings are modified.

Nine focused configuration/audit tests pass. The installed Spack parser,
YAML write, and repeated registration were checked using a temporary workspace
environment. The existing real lock correctly fails only the new OpenSSH
external check, with no missing SDK flags. Rerun the installer from the project
root to generate the new dependency plan and resume installation. Completed
installations remain available for reuse. Palace/Gmsh verification is pending.

## PETSc C++ preprocessor failure

The subsequent attempt successfully built OpenMPI, Hypre, GSLIB, Sundials,
ParMETIS, SuperLU_DIST and MFEM. PETSc 3.25.2 then failed its C++ preprocessor
check. Its detailed `configure.log` shows `mpic++ -E` failing to include
`cstdlib`. Compilation received `CXXFLAGS`, but preprocessing used separate
flags. Replaying the failed build environment reproduced the failure. Adding
the SDK include to `SPACK_CPPFLAGS` made the same MPI preprocessing probe pass.

The installer now adds a PETSc-only conditional `cppflags` requirement to the
Spack environment. It retains the existing C++ compilation requirement and
system OpenSSH registration. This records the fix in the concrete package spec
and forces a new plan, while leaving installed unrelated dependencies available
for reuse. The pre-build audit also checks PETSc's preprocessing flags.

Eleven configuration/audit tests pass. The installed Spack parser and repeated
YAML update pass in a temporary environment. The full PETSc build and Palace
numerical smoke test still require rerunning the installer in Terminal.
PETSc's default C/Fortran optimization warnings do not cause this failure.

## PETSc requirement precedence correction

The next audit stopped before building: PETSc had `cppflags` but lacked
`cxxflags`. Spack 1.2.2 selects a package-specific `require` list in place of the
`all` list. The earlier PETSc-only preprocessing requirement therefore removed
its inherited compilation requirement. The installer now puts both `cxxflags`
and `cppflags` in the same conditional PETSc requirement, and automatically
upgrades the previous preprocessing-only entry. The audit remains enabled.

Twelve focused tests pass, including migration and idempotence. Spack's actual
requirement-selection method and spec parser confirm both flags are present in
the effective PETSc requirement. A candidate lock with those flags passes the
audit; this candidate check does not replace actual Spack reconcretization.
The real dependency plan and full build remain pending a Terminal rerun.

## What verification does

The installer then runs `em/verify_installation.py`, which:

1. Confirms native macOS ARM64 execution and Gmsh's actual dylib architecture.
2. Checks the actual Palace solver binary architecture and launcher.
3. Generates two real 3D Gmsh meshes for a coaxial capacitor.
4. Checks Palace's JSON configuration and executes both electrostatic solves.
5. Reads `terminal-C.csv` with its explicit farad unit header.
6. Requires less than 1% analytical error on the fine mesh and less than 1%
   change between the two mesh results.

The smoke geometry has inner radius 1 µm, outer radius 5 µm, length 10 µm and
relative permittivity 3.9. Inner and outer cylindrical surfaces are terminal and
ground boundaries. The axial ends have zero normal electric displacement. Thus
its reference is the cylindrical-capacitor formula
`C = 2*pi*epsilon0*epsilon_r*length/log(b/a)` without end fringing.
This smoke geometry is an installation/numerical check, not a TSV process model.

The report is `work/em_verification/installation_report.json`. It must contain
`status: installation_and_analytic_smoke_verified` before claiming successful
installation. Failures retain the report and individual command logs. Input
JSON, meshes and solver outputs remain available in the same directory.

To rerun verification after installation without rebuilding:

```sh
"$HOME/.local/opt/tsv-em/python/bin/python" outputs/openroad_tsv_integration/em/verify_installation.py --palace "$HOME/.local/opt/tsv-em/palace_env/.spack-env/view/bin/palace" --output-dir work/em_verification
```

Three parser tests and three registration tests pass locally; the installer
passes `bash -n`. Registration tests use temporary directories and do not
modify actual home or shell configuration files. These checks
are separate from executing Gmsh/Palace, which is still pending.

## Proceeding to TSV extraction

After the analytical smoke passes, construct the two-TSV silicon/oxide geometry
and an explicit reference conductor. Record whether the silicon is treated as a
linear dielectric or as a semiconductor with a separately specified depletion
model. Refine the thin liners and test mesh and domain-size convergence. The
initial linear dielectric benchmark must not be described as bias-dependent
semiconductor extraction.

Extract the full Maxwell matrix, convert it to ground/mutual branch capacitance,
and attach the solver inputs, mesh and output hashes to the material reference.
The material adapter now accepts the `palace_electrostatic` provenance kind
with geometry/context binding and evidence hashes; see [copper_palace.md](copper_palace.md). No Q3D
identity should be assigned to Palace results. Actual TSV meshing and extraction
remain dependent on successful installation; no TSV field-solver values exist yet.

## Official references

- [Palace installation](https://awslabs.github.io/palace/stable/install/)
- [Palace 0.16 configuration and mesh scale](https://awslabs.github.io/palace/v0.16.0/config/model/)
- [Palace boundary conditions](https://awslabs.github.io/palace/v0.16.0/config/boundaries/)
- [Palace solver controls](https://awslabs.github.io/palace/v0.16.0/config/solver/)
- [Gmsh releases, including macOS ARM and Python packages](https://gmsh.info/#Download)
