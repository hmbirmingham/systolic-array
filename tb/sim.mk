# Shared simulation settings for every cocotb testbench in this repo.
# Include this from a test Makefile before Makefile.sim:
#
#   include ../sim.mk
#   TOPLEVEL = pe
#   COCOTB_TEST_MODULES = test_pe
#   include $(shell cocotb-config --makefiles)/Makefile.sim

OSS_CAD_SUITE ?= $(HOME)/oss-cad-suite

# Reach the real Icarus binaries. Everything in $(OSS_CAD_SUITE)/bin is a bash
# wrapper that exports PYTHONHOME to the suite's own bundled Python 3.11, which
# has no numpy — so cocotb would load the wrong interpreter and my golden models
# would be unavailable. libexec/ holds the actual executables.
ICARUS_BIN_DIR ?= $(OSS_CAD_SUITE)/libexec

# cocotb 2.x renamed MODULE. Using the old name still works but warns.
# Test Makefiles set COCOTB_TEST_MODULES, never MODULE.

SIM ?= icarus
TOPLEVEL_LANG ?= verilog

# Capture this file's own directory immediately.
#
# `RTL_DIR ?= ... $(lastword $(MAKEFILE_LIST)) ...` looks right and is not:
# `?=` defines a RECURSIVE variable, so MAKEFILE_LIST is read when RTL_DIR is
# first used — which happens after cocotb's Makefile.sim and its own includes
# have been pulled in. By then lastword points at a makefile inside
# site-packages, `../rtl` does not exist beside it, realpath returns empty, and
# the build fails with "No rule to make target `/pe.sv'".
#
# `:=` here pins the directory at parse time while leaving RTL_DIR overridable.
SIM_MK_DIR := $(dir $(lastword $(MAKEFILE_LIST)))
RTL_DIR ?= $(realpath $(SIM_MK_DIR)/../rtl)

# Dump waves by default so there's always something to open in GTKWave.
WAVES ?= 1
