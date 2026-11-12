# Tcl transport for the Python TSV equations, using a compiled OpenROAD binary.
# TSV_MODE: export, store, verify. Paths arrive through environment variables.
proc json_string {value} {
  set out {"}
  foreach ch [split $value ""] {
    scan $ch %c code
    switch -- $ch {
      "\"" { append out {\"} }
      "\\" { append out {\\} }
      default {
        if {$code < 32} {
          append out [format {\u%04x} $code]
        } else { append out $ch }
      }
    }
  }
  append out {"}
  return $out
}
proc json_strings {items} {
  set out {}
  foreach item $items { lappend out [json_string $item] }
  return "\[[join $out ,]\]"
}
proc endpoint_identity {ub} {
  set path {}
  foreach ci [[[$ub getParentRegion] getParentChip] getChipInstPath] {
    lappend path [$ci getName]
  }
  set inst [[[$ub getChipBumpInst] getChipBump] getInst]
  return "\[[json_strings $path],[json_string [$inst getName]]\]"
}
set db [ord::get_db]
read_db $::env(TSV_INPUT_ODB)
set top [$db getChip]
set property_name org.drexel.tsv.research.v1.results
switch -- $::env(TSV_MODE) {
  export {
    $db constructUnfoldedModel
    set endpoints {}
    foreach ub [$db getUnfoldedChipBumpInsts] {
      set xyz [$ub getGlobalPosition]
      set inst [[[$ub getChipBumpInst] getChipBump] getInst]
      set metadata {}
      foreach name {diameter_m liner_m ground_spacing_m acceptors_cm3 intrinsic_cm3 temperature_k conductivity_s_m} {
        set prop [odb::dbDoubleProperty_find $inst "org.drexel.tsv.research.v1.$name"]
        if {$prop ne "NULL"} {
          lappend metadata "[json_string $name]:[format %.17g [$prop getValue]]"
        }
      }
      foreach name {conductor substrate ground_reference} {
        set prop [odb::dbStringProperty_find $inst "org.drexel.tsv.research.v1.$name"]
        if {$prop ne "NULL"} { lappend metadata "[json_string $name]:[json_string [$prop getValue]]" }
      }
      lappend endpoints "{\"identity\":[endpoint_identity $ub],\"position_dbu\":\[[join $xyz ,]\],\"metadata\":\{[join $metadata ,]\}}"
    }
    set nets {}
    foreach unet [$db getUnfoldedChipNets] {
      set members {}
      foreach ub [$unet getConnectedBumps] { lappend members [endpoint_identity $ub] }
      lappend nets "{\"name\":[json_string [[$unet getChipNet] getName]],\"members\":\[[join $members ,]\]}"
    }
    set f [open $::env(TSV_TRANSFER_FILE) w]
    fconfigure $f -encoding utf-8
    puts $f "{\"dbu_per_micron\":[$db getDbuPerMicron],\"endpoints\":\[[join $endpoints ,]\],\"nets\":\[[join $nets ,]\]}"
    close $f
    puts "TSV_EXPORT_PASS"
  }
  store {
    if {[info exists ::env(TSV_NATIVE_PLAN)]} {
      source [file join [file dirname [info script]] native_rc.tcl]
      source $::env(TSV_NATIVE_PLAN)
      tsv::preflight $db
      tsv::apply $db
      write_spef -assembly_only $::env(TSV_SPEF_FILE)
    }
    set f [open $::env(TSV_TRANSFER_FILE) r]
    fconfigure $f -encoding utf-8
    set value [read $f]
    close $f
    set prop [odb::dbStringProperty_find $top $property_name]
    if {$prop eq "NULL"} {
      set prop [odb::dbStringProperty_create $top $property_name $value]
      if {$prop eq "NULL"} { error "Cannot create TSV property" }
    } else { $prop setValue $value }
    write_db $::env(TSV_OUTPUT_ODB)
    puts "TSV_STORE_PASS"
  }
  verify {
    set prop [odb::dbStringProperty_find $top $property_name]
    if {$prop eq "NULL"} { error "TSV property is missing after read_db" }
    set f [open $::env(TSV_TRANSFER_FILE) w]
    fconfigure $f -encoding utf-8
    puts $f [$prop getValue]
    close $f
    puts "TSV_VERIFY_PASS"
  }
  inspect {
    source [file join [file dirname [info script]] native_rc.tcl]
    set caps {}
    foreach node [$top getChipCapNodes] {
      lappend caps "{\"id\":[$node getId],\"net\":[json_string [[$node getChipNet] getName]],\"owner\":[json_string [tsv::tag $node]],\"spef_name\":[json_string [tsv::node_name $node]],\"c_ff\":[format %.17g [$node getCapacitance]]}"
    }
    set resistors {}
    foreach r [$top getChipRSegs] {
      lappend resistors "{\"owner\":[json_string [tsv::tag $r]],\"source\":[[$r getSourceCapNode] getId],\"target\":[[$r getTargetCapNode] getId],\"r_ohm\":[format %.17g [$r getResistance]]}"
    }
    set couplings {}
    foreach c [$top getChipCCSegs] {
      lappend couplings "{\"owner\":[json_string [tsv::tag $c]],\"source\":[[$c getSourceCapNode] getId],\"target\":[[$c getTargetCapNode] getId],\"c_ff\":[format %.17g [$c getCapacitance]]}"
    }
    set f [open $::env(TSV_TRANSFER_FILE) w]
    fconfigure $f -encoding utf-8
    puts $f "{\"cap_nodes\":\[[join $caps ,]\],\"resistors\":\[[join $resistors ,]\],\"couplings\":\[[join $couplings ,]\]}"
    close $f
    puts "TSV_INSPECT_PASS"
  }
  spef_check {
    source $::env(TSV_TRANSFER_FILE)
    read_spef -keep_capacitive_coupling $::env(TSV_SPEF_FILE)
    report_parasitic_annotation
    puts "TSV_SPEF_CHECK_PASS"
  }
  default { error "Unknown TSV_MODE" }
}
