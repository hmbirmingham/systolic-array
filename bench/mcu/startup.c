/* Minimal Cortex-M4 startup: vector table, .data copy, .bss zero, main.
 * Deliberately standalone — this repo does not depend on my STM32 project. */
#include <stdint.h>

extern uint32_t _sidata, _sdata, _edata, _sbss, _ebss, _estack;
extern int main(void);

void Reset_Handler(void)
{
    uint32_t *src = &_sidata, *dst = &_sdata;
    while (dst < &_edata) *dst++ = *src++;
    for (dst = &_sbss; dst < &_ebss; dst++) *dst = 0;
    main();
    for (;;) { }
}

static void Default_Handler(void) { for (;;) { } }

/* Only the entries this benchmark can reach. Anything else faults into
 * Default_Handler, which is what I want while measuring. */
__attribute__((section(".isr_vector"), used))
void (* const vector_table[])(void) = {
    (void (*)(void)) &_estack,
    Reset_Handler,
    Default_Handler,   /* NMI */
    Default_Handler,   /* HardFault */
    Default_Handler,   /* MemManage */
    Default_Handler,   /* BusFault */
    Default_Handler,   /* UsageFault */
};
