#!/bin/bash
# whoami
# $1 -h
# yosys -p 'read_verilog top.v; read_verilog -D ICE40_HX -lib -specify +/ice40/cells_sim.v; hierarchy -check; proc; stat'
$1 -p 'read_verilog top.v; hierarchy -simcheck -auto-top; tee -o out.json stat -json'