include ../sim.mk

TOPLEVEL = systolic_4x4_top
COCOTB_TEST_MODULES = test_top
VERILOG_SOURCES = $(RTL_DIR)/pe.sv $(RTL_DIR)/systolic_4x4.sv $(RTL_DIR)/systolic_4x4_top.sv

COMPILE_ARGS += -g2012

export PYTHONPATH := $(realpath ../../golden):$(PYTHONPATH)

include $(shell cocotb-config --makefiles)/Makefile.sim
