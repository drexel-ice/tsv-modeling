# Owned native RC insertion. Ground and coupling capacitances use fF; R uses ohms.
namespace eval tsv {
  variable owner org.drexel.tsv.native.v1.owner
  variable vias {}
  variable pairs {}
  variable endpoints {}
  variable nets {}
  variable validated {}
  variable nodes {}
}
proc tsv::tag {object} {
  variable owner
  set prop [odb::dbStringProperty_find $object $owner]
  if {$prop eq "NULL"} { return "" }
  return [$prop getValue]
}
proc tsv::set_tag {object value} {
  variable owner
  set prop [odb::dbStringProperty_find $object $owner]
  if {$prop eq "NULL"} {
    set prop [odb::dbStringProperty_create $object $owner $value]
    if {$prop eq "NULL"} { error "Cannot assign native RC ownership" }
  } else { $prop setValue $value }
}
proc tsv::key {path pad} {
  return "\[[json_strings $path],[json_string $pad]\]"
}
proc tsv::plan_via {id source_path source_pad target_path target_pad r cg} {
  variable vias
  if {[dict exists $vias $id]} { error "Duplicate TSV id" }
  if {[llength $source_path] != 1 || [llength $target_path] != 1} {
    error "Native RC v1 requires direct children of the top chip"
  }
  foreach value [list $r $cg] {
    if {![string is double -strict $value] || $value < 0 || $value > 3.4028234e38} {
      error "Native parasitics must be nonnegative and fit float storage"
    }
  }
  dict set vias $id [list [key $source_path $source_pad] [key $target_path $target_pad] $r $cg]
}
proc tsv::plan_pair {left right cc} {
  variable pairs
  if {![string is double -strict $cc] || $cc < 0 || $cc > 3.4028234e38} {
    error "Invalid native coupling value"
  }
  lappend pairs [list $left $right $cc]
}
proc tsv::preflight {db} {
  variable vias
  variable pairs
  variable endpoints
  variable nets
  variable validated
  if {[info commands ::odb::dbChipCCSeg_create] eq ""} {
    error "Rebuild OpenROAD with the native TSV coupling patch first"
  }
  $db constructUnfoldedModel
  foreach ub [$db getUnfoldedChipBumpInsts] {
    dict set endpoints [endpoint_identity $ub] [$ub getChipBumpInst]
  }
  foreach unet [$db getUnfoldedChipNets] {
    set net [$unet getChipNet]
    foreach ub [$unet getConnectedBumps] { dict set nets [endpoint_identity $ub] $net }
  }
  set top [$db getChip]
  foreach resistor [$top getChipRSegs] {
    set id [tag $resistor]
    if {$id ne "" && ![dict exists $vias $id]} {
      error "Previously owned TSV $id is absent from this batch; explicit cleanup required"
    }
  }
  set planned_nets {}
  dict for {id spec} $vias {
    lassign $spec source target r cg
    if {![dict exists $endpoints $source] || ![dict exists $endpoints $target]
        || ![dict exists $nets $source] || ![dict exists $nets $target]} {
      error "TSV endpoint not found: $id"
    }
    set net [dict get $nets $source]
    if {$net ne [dict get $nets $target] || [$net getChip] ne $top
        || [$net getNumBumpInsts] != 2} {
      error "TSV $id must occupy one two-terminal top-level chip net"
    }
    if {[dict exists $planned_nets $net]} { error "Multiple TSV specifications share one chip net" }
    dict set planned_nets $net $id
    set source_bump [dict get $endpoints $source]
    set target_bump [dict get $endpoints $target]
    set caps [$net getChipCapNodes]
    set resistors [$net getChipRSegs]
    set source_node "NULL"
    set target_node "NULL"
    set resistor "NULL"
    if {[llength $caps] || [llength $resistors]} {
      if {[llength $caps] != 2 || [llength $resistors] != 1} {
        error "TSV $id has a conflicting native RC topology"
      }
      foreach cap $caps {
        if {[tag $cap] ne $id} { error "Refusing to replace unowned capacitance on $id" }
        if {[$cap getChipBumpInst] eq $source_bump} { set source_node $cap }
        if {[$cap getChipBumpInst] eq $target_bump} { set target_node $cap }
      }
      set resistor [lindex $resistors 0]
      if {$source_node eq "NULL" || $target_node eq "NULL" || [tag $resistor] ne $id
          || [$resistor getSourceCapNode] ne $source_node || [$resistor getTargetCapNode] ne $target_node} {
        error "Refusing to replace unowned or differently connected resistance on $id"
      }
    }
    dict set validated $id [list $net $source_bump $target_bump $source_node $target_node $resistor $r $cg]
  }
  foreach coupling [$top getChipCCSegs] {
    set a [[$coupling getSourceCapNode] getChipNet]
    set b [[$coupling getTargetCapNode] getChipNet]
    if {[tag $coupling] eq "" && ([dict exists $planned_nets $a] || [dict exists $planned_nets $b])} {
      error "Refusing to replace a net with unowned coupling capacitance"
    }
  }
  set seen_pairs {}
  foreach pair $pairs {
    lassign $pair a b cc
    set key [lsort [list $a $b]]
    if {[dict exists $seen_pairs $key]} { error "Duplicate TSV coupling pair" }
    dict set seen_pairs $key 1
    if {$a eq $b || ![dict exists $validated $a] || ![dict exists $validated $b]} {
      error "Invalid coupling endpoints"
    }
    if {[lindex [dict get $validated $a] 0] eq [lindex [dict get $validated $b] 0]} {
      error "Same-net coupling is diagnostic only"
    }
  }
}
proc tsv::apply {db} {
  variable validated
  variable nodes
  variable pairs
  set top [$db getChip]
  # Replace this extractor's coupling contributions; preserve all unowned elements.
  foreach coupling [$top getChipCCSegs] {
    if {[tag $coupling] ne ""} { odb::dbChipCCSeg_destroy $coupling }
  }
  dict for {id entry} $validated {
    lassign $entry net source_bump target_bump source target resistor r cg
    if {$source eq "NULL"} {
      set source [odb::dbChipCapNode_create $net]
      $source setChipBumpInst $source_bump
      set_tag $source $id
      set target [odb::dbChipCapNode_create $net]
      $target setChipBumpInst $target_bump
      set_tag $target $id
      set resistor [odb::dbChipRSeg_create $net $source $target]
      set_tag $resistor $id
    }
    $source setCapacitance [expr {$cg / 2.0}]
    $target setCapacitance [expr {$cg / 2.0}]
    $resistor setResistance $r
    dict set nodes $id [list $source $target]
  }
  foreach pair $pairs {
    lassign $pair a b cc
    # Equal-height TSVs: split the total pair C equally across the two ends.
    foreach left [dict get $nodes $a] right [dict get $nodes $b] {
      set coupling [odb::dbChipCCSeg_create $left $right]
      $coupling setCapacitance [expr {$cc / 2.0}]
      set_tag $coupling [json_strings [list $a $b]]
    }
  }
}
proc tsv::node_name {node} {
  set bump [$node getChipBumpInst]
  if {$bump eq "NULL"} { return "" }
  set chip_inst [[ $bump getChipRegionInst] getChipInst]
  set master [$bump getChipBump]
  set net [$master getNet]
  foreach iterm [[$master getInst] getITerms] {
    if {[$iterm getNet] eq $net} {
      return "[$chip_inst getName]/[$iterm getName :]"
    }
  }
  return ""
}
