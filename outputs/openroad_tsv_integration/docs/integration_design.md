# Geometry-aware TSV parasitics in native 3D OpenDB

> Research-workspace record: some commands and evidence paths below refer to
> internal tools or archived results not distributed in this repository. For
> supported publication-checkout commands, use the
> [repository quick start](../../../README.md).


Status: pinned-source audit and native OpenDB property roundtrip verified,
2026-11-11. OpenROAD commit 08a3714d61a4ae7f2f5d8535c080ccd8871b16b2;
OpenSTA submodule f8e13cbf12d02a07a2d1ec4a64f3e6985b747eab.

This document records the baseline audit. The current native RC source changes
and validation status are described in [native_rc.md](native_rc.md).

## Verified build update

The macOS CLI binary runs. An upstream two-die 3Dblox example loaded successfully,
with 6 unfolded bumps, 4 unfolded nets, and assembly scale 2000 DBU/um. A separate
synthetic two-TSV terminal fixture then passed native geometry export, OpenDB double
property metadata extraction, Python equation evaluation, JSON property storage,
and readback in a new OpenROAD process. The repeated run yields identical results.
The original input bytes remain unchanged. Eleven adapter tests pass; the separate
optional direct-Python-module test remains skipped.

The installed executable is Tcl-based. This revision ships Python bindings through
a separate Bazel target; python/openroad/BUILD hardcodes the wheel platform to
linux_x86_64. The verified macOS route is therefore native_transport.tcl plus
run_native.py, not `openroad -python` or a Linux-labeled wheel installed on macOS.

Pinned-source findings:

- src/rcx/src/multiChipExtractor.cpp creates two zero-capacitance terminal nodes
  and a resistor from assembly rules; it supports exactly two bumps per bond net.
- src/rcx/src/multiChipSpefWriter.cpp emits *D_NET, *CONN and *RES, but no *CAP.
  Nonzero node C alone would therefore not export actual shunt capacitors.
- src/rcx/src/extSpef.cpp scales stored capacitance by 0.001 for PF and resistance
  by 0.001 for KOHM, establishing fF/ohm as the current SPEF export contract.
- src/odb/src/swig/common/containers.i includes unfolded geometry collections but
  lacks WRAP_DB_CONTAINER entries for dbChipCapNode and dbChipRSeg. Direct class
  creation is available in Tcl; collection iteration needs a binding fix/test.
- No dbChipCCSeg class or matching schema object exists in the inspected checkout.
- src/dbSta/test includes read_db and cross-die SPEF test collateral for later STA
  checks. No custom fixture is needed merely to exercise upstream 3D loading.

The synthetic fixture is a transport/model metadata test, not an EM validation or
physical routing result. Ground-plane spacing is explicit metadata. The current adapter inserts native R, ground C and chip coupling objects, with
ODB/SPEF roundtrip and cross-die timing regressions. The copper Palace benchmark
has completed extraction and native insertion. See `native_rc.md`,
`copper_palace.md`, and `pr_readiness.md` for current evidence and remaining checks.

The initial design below is retained with this status update taking precedence.

## Source alignment and repository choice

The supplied `ICCAD_3dic-paper.pdf`, Section 2.2.2, describes separate per-die and
bond extraction, scalar chip-level RC storage, negligible bump capacitance in the
present extraction pass, and future ground/coupling C and inductive support. Its
3D model uses dbChip masters, dbChipInst placements, dbChipRegion interfaces,
dbChipBump wrappers around dbInst pads, dbChipConn physical bonds, and dbChipNet
logical connections. The supplied slides 7-11 show that same hierarchy and cross-die
RC/STA use. Slides 21 and 24 link TaiWei and OpenROAD-Research. The paper references
upstream OpenROAD's 3D documentation and names the research repository as a future
distribution route for some work. It does not specify an exact Git commit.

| Repository | Role for this work | Status |
| --- | --- | --- |
| https://github.com/The-OpenROAD-Project/OpenROAD | Recommended first API baseline for native 3D ODB and chip RC objects | Pinned checkout and compiled CLI verified |
| https://github.com/ieee-ceda-datc/OpenROAD-Research | Research distribution and possible paper-specific branch | Public README inspected; feature parity unverified |
| https://github.com/CODA-Team/TaiWei | Larger implementation flow and pinned tool dependencies | Public README inspected; not selected as the low-level database baseline |

Public TaiWei instructions describe an integration/2610 branch for 3D synthesis,
placement and CTS. That does not establish it as the chiplet extraction revision.
Do not choose it merely because the slides link TaiWei. Once a checkout is obtained,
record full commit IDs and submodule IDs, then inspect applicable project instructions,
the actual 3D bindings, extraction code, test fixtures and serialization schema.

## Proposed execution boundary

1. Load an assembly .odb with its per-die technologies and 3D hierarchy.
2. Resolve each actual TSV conductor and its terminal mappings. Keep TSVs, bumps,
   hybrid bonds and ordinary BEOL vias as distinct physical categories.
3. Read unfolded coordinates in the assembly frame. Read or explicitly supply core
   geometry, materials, liner/depletion inputs, and reference-conductor information.
4. Evaluate R and C with an identified model/version and documented valid domain.
   Record L values for research storage, without claiming STA consumes them.
5. Store research results with units and provenance. Once the physical and database
   contracts are verified, build an owned chip-level RC network and export bond SPEF.
6. Stitch with die-internal parasitics through the existing terminal mappings and
   validate complete cross-die timing. Update affected results after layout changes.

The executable bridge currently implements selected endpoint extraction, explicit
metadata lookup, scalar model calls, pair calculations and property persistence.
The Tcl property path and native parasitic-network insertion are verified.
Cross-die timing response and SPEF import have registered regressions.

## Input mapping and gaps

“Available” below means documented public API, not verified in a pinned binary.

| Model input | Documented source / extraction approach | Gap or restriction |
| --- | --- | --- |
| Physical occurrence identity | unfolded chip getChipInstPath plus pad dbInst name | Preserve full paths for repeated masters |
| Global terminal position | dbUnfoldedChipBumpInst.getGlobalPosition | Verify compiled Point3D binding and coordinate convention |
| Coordinate scale | dbDatabase.getDbuPerMicron for assembly coordinates | Per-die local geometry needs its own block scale |
| TSV length | Difference between validated conductor-end coordinates | Die thickness and dbChipConn thickness are not general TSV lengths |
| Conductor diameter | Explicit conductor-shape metadata or new typed TSV field | A bump/master bounding box can include landing metal and keepouts |
| Liner thickness | Process/TSV technology metadata | No standardized TSV liner getter established by inspected APIs |
| Ground spacing | Distance to a designated physical reference surface, or explicit process input | Must identify actual reference conductor; die Z alone is insufficient |
| Reference identity | Reference-net/plane binding | Preserve reference identity, not just a distance |
| Pitch and edge spacing | Neighbor search in common global coordinates | Pitch != edge gap; equal-rod model only in prototype |
| Material/conductivity | TSV process model | Do not infer tungsten from the original model's default |
| Substrate permittivity/doping | Process model/technology metadata | Ordinary LEF routing layer properties are not sufficient |
| Liner permittivity | Process model | Python model currently fixes original silicon/oxide constants |
| Temperature, corner, frequency | Explicit analysis context | Require metadata even if initial extraction is single-corner |
| Electrical endpoint net | dbUnfoldedChipNet.getConnectedBumps and getChipNet | Resolve logical connectivity separately from physical dbChipConn |

Prototype properties have SI suffixes for geometry and cm3 suffixes for density.
They are proposed namespaced conventions, not claimed existing schema fields.
Results do not silently promote a missing input to zero. All config fallbacks are
identified in per-result provenance. Missing physical metadata is a schema/process
kit problem even when a numerical result could be stored today.

## Electrical result mapping

| Result | Existing documented storage | Work required |
| --- | --- | --- |
| TSV series R | dbChipRSeg.setResistance(float), endpoints are dbChipCapNode objects | Verify units, source/target binding, attribution, and replace-vs-add behavior |
| Ground C | dbChipCapNode.setCapacitance(float) | Existing scalar field: no new ground-C object is required; populate consistently |
| Coupling C between chip-level nodes | No chip-level equivalent in pinned public headers/schema | Propose dbChipCCSeg or equivalent |
| Die-internal coupling C | dbCCSeg | Existing per-block object does not by itself solve cross-chip endpoint ownership |
| Self L | No native chip-level inductor identified; paper describes this as future work | Research property now; future typed inductor and consuming analysis support |
| Mutual L | No native chip-level mutual element identified | Pair relation, orientation/sign convention and consuming RLC engine needed |
| Provenance/geometry | Generic dbDoubleProperty/dbStringProperty | Prototype storage available; standardized process/conductor schema recommended |

Documented chip RC setters are scalar floats with no corner argument. This suggests
a needed corner extension for this API, but exact version and internal storage must
be inspected before proposing a patch. Public documentation snapshots differ in
age; method existence must be verified against the locked source and compiled SWIG
module. C++ support does not guarantee Python binding availability.

## Missing-schema proposals for maintainers

These names and objects are proposals, not APIs used by the executable prototype.

- **Typed TSV process definition**, for example dbTechTSVModel: conductor and liner
  material identifiers, conductivity/permittivity, liner thickness, doping, model
  calibration domain, temperature/frequency convention, and model version.
- **Typed physical conductor occurrence**, for example dbTSV: core shape or diameter,
  conductor-end geometry, process definition, die/assembly occurrence ownership and
  terminal/net mapping. Avoid overloading a chip-level isTsv flag into a per-via model.
- **Reference surface binding**: actual net/plane identity, surface geometry and
  coordinate frame, enabling a reproducible ground-distance calculation.
- **Chip-level coupling element**, for example dbChipCCSeg: two dbChipCapNode
  references, capacitance per corner, symmetric iteration from both nets, unique
  pair ownership, destruction/remapping rules and consistency checks.
- **Corner-aware chip parasitics**: explicit R/C units and analysis-corner lookup,
  with common conversion rules in API, SPEF writer/reader and STA boundary.
- **Future inductance elements**: series self L and mutual relation with reference
  directions and sign. Storing an L value is insufficient to make RC-only STA
  evaluate inductive behavior.

A real patch will need schema-generator definitions, object-type registration,
database tables and iterators, serialization/version migration, object lifetime and
destroy callbacks, SWIG exposure, memory accounting, regression fixtures and tests.
For coupling C, include SPEF export/import and a consuming parasitic-network path;
otherwise it remains only stored data. Do not add a second ground-C scalar simply
because the current extraction pass leaves existing node capacitance at zero.

## Native RC insertion design to implement after the checkout

Use one modeled conductor segment with resistance R between its two true terminals.
A first-order pi approximation may split total ground C as C/2 on each terminal;
that is a modeling choice requiring validation, not an exact spatial distribution.
Preserve a coupling capacitor as a positive two-terminal element. Do not add it
again to both ground nodes, and do not replace a true coupling relation with an
undocumented grounded approximation. Same-net structures need a consistent circuit
reduction policy, not an unconditional inter-net capacitor.

Keep R, Cground and Ccoupling contributions attributed to their extractor and model
version. Re-extraction must replace only owned contributions and leave unrelated
OpenRCX/die parasitics intact. Avoid double counting preexisting lumped TSV models,
landing-pad RC, bond R, or driver/load pin capacitances. Repeated placements need
occurrence-correct electrical nodes even when the folded master is shared.

Before enabling native insertion:

1. Inspect the selected dbChipCapNode/dbChipRSeg implementation, OpenRCX writer and
   dbSta/SPEF reader to establish units with an independent 1-ohm/1-fF micro-example.
2. Check terminal mapping from each TSV conductor to die dbBTerm/dbITerm boundaries.
   Physical contact is not enough to infer net identity.
3. Verify the existing network topology and define ownership/idempotence behavior.
4. Reconcile the capacitance equation/unit issue. The 2009 equations and empirical
   fit cannot be silently converted to SI while claiming unchanged calibration.
5. Confirm model suitability for the actual material and geometry. The 2009 tungsten
   TSV fits are not automatically valid for copper hybrid bonds, submicron pads,
   different dielectrics, or arbitrary arrays.
6. Test .odb write/read, SPEF write/read, and end-to-end stitched STA; a property
   roundtrip alone does not validate electrical consumption.

The paper's Figure 5 annotates bond SPEF as top scope/read first. Current dbNetwork
source comments likewise state that reading the top-scope file later can replace
and discard prior per-die contributions. Treat SPEF read order as a testable contract.

## Verification completed and outstanding

Completed locally: offline two-TSV example; 10 adapter unit tests covering geometry,
DBU conversion, full occurrence paths, connectivity validation, physical metadata,
material rejection, idempotent property operations and unsupported pair reporting.
The 7 original equation tests also pass, including 510 archived numerical regressions.

Unexecuted: compiled Python binding verification, native RC insertion, coupling
schema patch, OpenRCX/SPEF
roundtrip, cross-die STA, large-design runtime and Q3D recalibration. The supplied
native .odb test is skipped until its runtime and design/config fixture are available.

Minimum next design fixture: a small 3D assembly .odb (or its 3Dblox/LEF/DEF input
collateral), two explicitly identified TSVs with true terminal mappings and process
metadata, and the matching OpenROAD binary/source commit. A face-to-face bump-only
fixture will verify database access but does not validate TSV physical extraction.

## Public sources inspected

- https://github.com/The-OpenROAD-Project/OpenROAD
- https://github.com/ieee-ceda-datc/OpenROAD-Research
- https://github.com/CODA-Team/TaiWei
- https://openroad.readthedocs.io/en/latest/doxygen_output/html/classodb_1_1dbDatabase.html
- https://openroad.readthedocs.io/en/latest/doxygen_output/html/classodb_1_1dbChip.html
- https://openroad.readthedocs.io/en/latest/doxygen_output/html/classodb_1_1dbChipBump.html
- https://openroad.readthedocs.io/en/latest/doxygen_output/html/classodb_1_1dbUnfoldedChipBumpInst.html
- https://openroad.readthedocs.io/en/latest/doxygen_output/html/classodb_1_1dbUnfoldedChipRegionInst.html
- https://openroad.readthedocs.io/en/latest/doxygen_output/html/classodb_1_1dbUnfoldedChipInst.html
- https://openroad.readthedocs.io/en/latest/doxygen_output/html/classodb_1_1dbUnfoldedChipNet.html
- https://openroad.readthedocs.io/en/latest/doxygen_output/html/classodb_1_1dbChipCapNode.html
- https://openroad.readthedocs.io/en/latest/doxygen_output/html/classodb_1_1dbChipRSeg.html
- https://openroad.readthedocs.io/en/latest/doxygen_output/html/classodb_1_1dbDoubleProperty.html
- https://openroad.readthedocs.io/en/latest/doxygen_output/html/classodb_1_1dbStringProperty.html
- https://openroad.readthedocs.io/en/latest/main/src/README.html
- https://github.com/The-OpenROAD-Project/OpenROAD/blob/master/src/dbSta/include/db_sta/dbNetwork.hh

Uploaded sources inspected locally:
`inputs/ICCAD2026-3DIC_slides/ICCAD_3dic-paper.pdf` and
`inputs/ICCAD2026-3DIC_slides/ICCAD_3dic_v5-slides.pdf`.
