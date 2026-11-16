include ../sim.mk

TOPLEVEL = systolic_4x4
COCOTB_TEST_MODULES = test_array_4x4
VERILOG_SOURCES = $(RTL_DIR)/pe.sv $(RTL_DIR)/systolic_4x4.sv

COMPILE_ARGS += -g2012

export PYTHONPATH := $(realpath ../../golden):$(PYTHONPATH)

include $(shell cocotb-config --makefiles)/Makefile.sim
