# Synthetic 3D terminal fixture. This is not an EM-qualified physical TSV layout.
read_3dbx $::env(TSV_3DBX)
set db [ord::get_db]
odb::dbStringProperty_create [$db getChip] drexel_fixture_kind synthetic_tsv_transport_test
set profile tungsten
if {[info exists ::env(TSV_FIXTURE_PROFILE)]} { set profile $::env(TSV_FIXTURE_PROFILE) }
set diameter 0.000020
set liner 0.000001
if {$profile eq "copper"} { set diameter 0.000005; set liner 0.0000002 }
foreach ub [$db getUnfoldedChipBumpInsts] {
  set inst [[[$ub getChipBumpInst] getChipBump] getInst]
  foreach {name value} {
    ground_spacing_m 0.000010
    acceptors_cm3 1.0e15
    intrinsic_cm3 1.5e10
    temperature_k 300.0
  } {
    odb::dbDoubleProperty_create $inst "org.drexel.tsv.research.v1.$name" $value
  }
  odb::dbDoubleProperty_create $inst org.drexel.tsv.research.v1.diameter_m $diameter
  odb::dbDoubleProperty_create $inst org.drexel.tsv.research.v1.liner_m $liner
  odb::dbStringProperty_create $inst org.drexel.tsv.research.v1.conductor $profile
  if {$profile eq "copper"} {
    odb::dbDoubleProperty_create $inst org.drexel.tsv.research.v1.conductivity_s_m 5.8e7
  }
}
write_db $::env(TSV_OUTPUT_ODB)
puts "TSV_FIXTURE_PASS"
