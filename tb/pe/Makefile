include ../sim.mk

TOPLEVEL = pe
COCOTB_TEST_MODULES = test_pe
VERILOG_SOURCES = $(RTL_DIR)/pe.sv

# Icarus needs to be told this is SystemVerilog; it defaults to Verilog-2005
# and rejects always_ff, logic and typed parameters.
COMPILE_ARGS += -g2012

# The golden models live outside tb/, and they are the point of the suite.
export PYTHONPATH := $(realpath ../../golden):$(PYTHONPATH)

include $(shell cocotb-config --makefiles)/Makefile.sim
