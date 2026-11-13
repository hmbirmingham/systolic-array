include ../sim.mk

TOPLEVEL = systolic_4x4
COCOTB_TEST_MODULES = test_transform
VERILOG_SOURCES = $(RTL_DIR)/pe.sv $(RTL_DIR)/systolic_4x4.sv

COMPILE_ARGS += -g2012
# The transform benchmark runs the array at 16 bits, not the 8-bit default.
# ADR-0006: on ECP5 this costs one MULT18X18D per PE either way.
COMPILE_ARGS += -Psystolic_4x4.DATA_W=16

export PYTHONPATH := $(realpath ../../golden):$(PYTHONPATH)

include $(shell cocotb-config --makefiles)/Makefile.sim
