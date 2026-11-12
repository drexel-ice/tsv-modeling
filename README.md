# TSV modeling

Companion TSV models and OpenDB integration for OpenROAD, prepared for
`drexel-ICE/tsv-modeling`.

- Original tungsten TSV equations with explicit research conventions.
- Copper bulk DC resistance and externally referenced ground/coupling capacitance.
- Palace/Gmsh electrostatic extraction for the two-TSV dielectric benchmark.
- OpenDB geometry/process metadata transport, native RC insertion, and assembly SPEF export.

## Citation and detailed guide

Please reference the following publications when using these models:

1. I. Savidis and E. G. Friedman, “Closed-form expressions of 3-D via resistance, inductance, and capacitance,” *IEEE Transactions on Electron Devices*, vol. 56, no. 9, pp. 1873–1881, September 2009.
   DOI: [10.1109/TED.2009.2026200](https://doi.org/10.1109/TED.2009.2026200).
2. I. Savidis, S. M. Alam, A. Jain, S. Pozder, R. E. Jones, and R. Chatterjee, “Electrical modeling and characterization of through-silicon vias (TSVs) for 3-D integrated circuits,” *Microelectronics Journal*, vol. 41, no. 1, pp. 9–16, January 2010.
   DOI: [10.1016/j.mejo.2009.10.006](https://doi.org/10.1016/j.mejo.2009.10.006).
3. I. Savidis and E. G. Friedman, “Electrical modeling and characterization of 3-D vias,” *Proceedings of the IEEE International Symposium on Circuits and Systems*, pp. 784–787, May 2008.
   DOI: [10.1109/ISCAS.2008.4541535](https://doi.org/10.1109/ISCAS.2008.4541535).


The [companion README](outputs/openroad_tsv_integration/README.md) preserves the
project's detailed documentation and citation wording. Start with the commands
below for this publication checkout. The scripts retain their tested
`outputs/openroad_tsv_integration/` paths; `repos/` and `work/` are local,
git-ignored directories.

## Offline quick start

Python 3.10 or newer is required. The offline equations and bridge need no
third-party Python packages. From this repository's root:

```sh
mkdir -p work
python3 outputs/openroad_tsv_integration/run_bridge.py --config outputs/openroad_tsv_integration/examples/config.json --fixture outputs/openroad_tsv_integration/examples/endpoints.json --report work/offline_demo.json
python3 -m unittest discover -s outputs/openroad_tsv_integration/tests -v
```

Native-binary tests skip unless `OPENROAD_BIN` is set; native RC tests additionally
require `TSV_RUN_NATIVE_RC=1`. The optional direct Python `odb` test has its own
runtime/input requirements. Offline passing tests are not a field-solver or
OpenROAD integration validation.

## OpenROAD dependency

The core extension is developed separately in
[isavidis/OpenROAD](https://github.com/isavidis/OpenROAD), branch
`tsv/native-rc-coupling-upstream`, local reviewed commit
`19a6ccadfb3a159f39993fa95e5dd087ebcad225`. Publication of that branch has not yet
been verified. The companion can be prepared independently using the bundled
patch against upstream commit `b56f3a6a26fcab9c6f86604358ae5ac0a9a28ce1`:

```sh
python3 outputs/openroad_tsv_integration/checkout_openroad.py --destination repos/OpenROAD-pr-ready --ref b56f3a6a26fcab9c6f86604358ae5ac0a9a28ce1
```

Read `repos/OpenROAD-pr-ready/AGENTS.md` and applicable repository instructions
before modifying the checkout. Then apply the patch from this repository's root:

```sh
git -C repos/OpenROAD-pr-ready apply ../../outputs/openroad_tsv_integration/patches/native_rc_coupling.patch
git -C repos/OpenROAD-pr-ready submodule update --init --recursive
cd repos/OpenROAD-pr-ready
bazelisk build --//:platform=cli //:openroad
cd ../..
```

Use the dependency setup required by OpenROAD for your platform. The patch adds
schema **143**. Existing prototype databases with the private schema-142 layout
are incompatible; generate fresh inputs with the executable you will use.
Neither a clone of current upstream `master` alone nor an unpatched binary
provides the required coupling API.

## Run native TSV insertion

From the repository root, with the patched CLI built and unused output paths:

```sh
python3 outputs/openroad_tsv_integration/make_native_fixture.py --profile tungsten --openroad repos/OpenROAD-pr-ready/bazel-bin/openroad --output-odb work/tsv_input.odb
python3 outputs/openroad_tsv_integration/run_native.py --native-rc --openroad repos/OpenROAD-pr-ready/bazel-bin/openroad --input-odb work/tsv_input.odb --output-odb work/tsv_rc.odb --config outputs/openroad_tsv_integration/examples/native_config.json --report work/tsv_rc.json --liberty outputs/openroad_tsv_integration/examples/native_fixture/landing.lib
OPENROAD_BIN="$PWD/repos/OpenROAD-pr-ready/bazel-bin/openroad" TSV_RUN_NATIVE_RC=1 python3 -m unittest discover -s outputs/openroad_tsv_integration/tests -v
```

Extraction is explicitly invoked. Finding two die SPEFs does not trigger it.
The example's passive marker library is synthetic; supply the actual design's
Liberty libraries and timing constraints for analysis of a real design.

## Copper capacitance and documentation

- [Material choices and reference requirements](outputs/openroad_tsv_integration/docs/materials.md).
- [Copper Palace/Gmsh extraction](outputs/openroad_tsv_integration/docs/copper_palace.md), including explicit schema-143 executable/input selection.
- [macOS Palace/Gmsh installation](outputs/openroad_tsv_integration/docs/palace_gmsh_setup.md).
- [Native database mapping and SPEF behavior](outputs/openroad_tsv_integration/docs/native_rc.md).
- [Detailed OpenROAD core changes](outputs/openroad_tsv_integration/review/PR_CHANGE_DETAILS.md).

Historical `results/`, review logs, PR-preparation tooling, and private ODBs
mentioned in the preserved research documentation belong to the separate
research archive and are not included in this publication checkout. Current
runtime instructions are in this root README and the extraction guides.

## Physical scope

The tungsten capacitance equation/subscript discrepancy remains unresolved;
explicit model conventions preserve the reproduction assumptions. Copper uses
bulk DC resistance and supplied reference capacitance. The Palace benchmark is
a linear, lossless dielectric enclosure with grounded sidewalls and insulated
axial ends. It does not model depletion, substrate conduction, contact resistance,
or end fringing, and is not a foundry-qualified process model.

## License

Original TSV companion code and documentation are licensed under
[Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International
(CC BY-NC-SA 4.0)](https://creativecommons.org/licenses/by-nc-sa/4.0/), matching
`drexel-ice/EDA-schema`. See [LICENCE](LICENCE) for the full terms.

This license requires attribution, limits use to noncommercial purposes, and
requires shared adaptations to use the same license, subject to its terms.
Please also reference the three publications listed above when using the models.

The bundled OpenROAD patch and upstream-derived material retain their applicable
upstream licensing. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and
[LICENSES/OpenROAD-LICENSE](LICENSES/OpenROAD-LICENSE).
