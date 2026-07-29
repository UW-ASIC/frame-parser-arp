# Makefile
# See https://docs.cocotb.org/en/stable/quickstart.html for more info

# defaults
SIM ?= icarus
FST ?= -fst # Use more efficient FST format
TOPLEVEL_LANG ?= verilog
SRC_DIR = $(PWD)/../src
RTL_DIR = $(PWD)/../RTL
PROJECT_SOURCES = project.v

# Unit test for a single RTL module:
#   make -B UNIT=<module_name>
# Compiles everything in ../RTL and runs test_<module_name>.py against the
# Verilog module <module_name>. If the module is named differently from its
# file, add TOPLEVEL=<verilog_module_name> to the command line.
# When UNIT is set, enable cocotb's built-in Icarus wave dump so the waveform
# is written to sim_build/<UNIT>/<UNIT>.fst.
UNIT ?=

ifneq ($(GATES),yes)

ifeq ($(UNIT),)

# RTL simulation of the full design (default, also used by CI):
SIM_BUILD				= sim_build/rtl
VERILOG_SOURCES += $(addprefix $(SRC_DIR)/,$(PROJECT_SOURCES))
VERILOG_SOURCES += $(wildcard $(RTL_DIR)/*.v)
VERILOG_SOURCES += $(PWD)/tb.v
TOPLEVEL = tb
COCOTB_TEST_MODULES = test

else

# RTL simulation of a single module (no tb.v wrapper, drive ports from Python):
SIM_BUILD				= sim_build/$(UNIT)
WAVES = 1
VERILOG_SOURCES += $(wildcard $(RTL_DIR)/*.v)
TOPLEVEL = $(UNIT)
COCOTB_TEST_MODULES = test_$(UNIT)

endif

else

# Gate level simulation:
SIM_BUILD				= sim_build/gl
COMPILE_ARGS    += -DGL_TEST
COMPILE_ARGS    += -DFUNCTIONAL
COMPILE_ARGS    += -DUSE_POWER_PINS
COMPILE_ARGS    += -DSIM
COMPILE_ARGS    += -DUNIT_DELAY=\#1
VERILOG_SOURCES += $(PDK_ROOT)/sky130A/libs.ref/sky130_fd_sc_hd/verilog/primitives.v
VERILOG_SOURCES += $(PDK_ROOT)/sky130A/libs.ref/sky130_fd_sc_hd/verilog/sky130_fd_sc_hd.v

# this gets copied in by the GDS action workflow
VERILOG_SOURCES += $(PWD)/gate_level_netlist.v
VERILOG_SOURCES += $(PWD)/tb.v
TOPLEVEL = tb
COCOTB_TEST_MODULES = test

endif

# Allow sharing configuration between design and testbench via `include`:
COMPILE_ARGS 		+= -I$(SRC_DIR)

# include cocotb's make rules to take care of the simulator setup
include $(shell cocotb-config --makefiles)/Makefile.sim
