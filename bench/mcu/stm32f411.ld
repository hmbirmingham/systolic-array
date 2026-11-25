/* Minimal linker script for STM32F411RE. Written for this benchmark so the
 * repo stays self-contained: nothing here comes from my STM32 project. */
MEMORY
{
  FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 512K
  SRAM (rwx) : ORIGIN = 0x20000000, LENGTH = 128K
}

_estack = ORIGIN(SRAM) + LENGTH(SRAM);

SECTIONS
{
  .isr_vector : { KEEP(*(.isr_vector)) } > FLASH

  .text : {
    *(.text*)
    *(.rodata*)
    . = ALIGN(4);
  } > FLASH

  _sidata = LOADADDR(.data);
  .data : {
    . = ALIGN(4);
    _sdata = .;
    *(.data*)
    . = ALIGN(4);
    _edata = .;
  } > SRAM AT > FLASH

  .bss : {
    . = ALIGN(4);
    _sbss = .;
    *(.bss*)
    *(COMMON)
    . = ALIGN(4);
    _ebss = .;
  } > SRAM

  /* The result block lands at a fixed address so openocd can read it without
   * parsing symbols. NOLOAD matters: without it the section gets a load address
   * up in SRAM and objcopy pads the flat binary from 0x08000000 to 0x2001F018,
   * which is a 402 MB .bin. Nothing initialises it, so main clears the guard
   * word before measuring. */
  .results 0x2001F000 (NOLOAD) : { KEEP(*(.results)) } > SRAM
}
