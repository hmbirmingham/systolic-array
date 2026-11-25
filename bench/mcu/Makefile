# Cortex-M4 baseline for the transform benchmark.
#
#   make check    build for the host and cross-check against the Python model
#   make          build the firmware
#   make flash    write it to the board over ST-LINK
#   make read     halt and read the results block
#
# Self-contained: no sources, headers or scripts from any other project.

TARGET  = transform_bench
PREFIX  = arm-none-eabi-
CC      = $(PREFIX)gcc
OBJCOPY = $(PREFIX)objcopy
SIZE    = $(PREFIX)size

# No FPU flags: the transform is pure integer, so the hard-float ABI would only
# change the calling convention. -O2 because a baseline should be optimised;
# gcc uses the M4's SMULBB/SMLABB for the int16 multiply-accumulates.
ARCH    = -mcpu=cortex-m4 -mthumb
CFLAGS  = $(ARCH) -O2 -std=c11 -Wall -Wextra -ffreestanding -fno-common
LDFLAGS = $(ARCH) -T stm32f411.ld -nostdlib -nostartfiles -Wl,-Map=$(TARGET).map

SRCS   = startup.c bench_main.c transform_fx.c
RESULTS_ADDR = 0x2001F000

all: $(TARGET).bin

$(TARGET).elf: $(SRCS) stm32f411.ld
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $(SRCS)
	$(SIZE) $@

$(TARGET).bin: $(TARGET).elf
	$(OBJCOPY) -O binary $< $@

flash: $(TARGET).bin
	st-flash --reset write $< 0x08000000

# Read the six-word results block. The first word is 0x5A5A0001 once the run
# has finished; anything else means it has not.
read:
	openocd -f interface/stlink.cfg -f target/stm32f4x.cfg \
	  -c "init; reset halt; resume; sleep 500; halt; mdw $(RESULTS_ADDR) 6; shutdown"

check: host_check
	@echo "run the cross-check from the repo root:"
	@echo "  .venv/bin/python bench/mcu/crosscheck.py"

host_check: transform_fx.c host_check.c transform_fx.h
	cc -O2 -std=c11 -Wall -Wextra -o $@ transform_fx.c host_check.c

clean:
	rm -f $(TARGET).elf $(TARGET).bin $(TARGET).map host_check

.PHONY: all flash read check clean
