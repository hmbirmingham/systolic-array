/* Cortex-M4 baseline for the 4x4 homogeneous transform.
 *
 * Measures with DWT->CYCCNT, which counts core clocks, so the figure does not
 * depend on the clock the part is running at. No clock setup: the F411 comes
 * out of reset on the 16 MHz HSI and stays there. Cycles per point is the
 * comparison that means something against the array's 2.50.
 *
 * Input tiles are built BEFORE the timed region. A first version generated them
 * inside it, with a multiply and a modulo per element, and measured 220.8
 * cycles/point — 13.8 cycles per multiply-accumulate on a core whose SMLABB is
 * one cycle. That was input generation, not the transform. An empty pass over
 * the same tiles is timed separately so the loop and memory cost can be
 * subtracted rather than assumed negligible.
 *
 * Results land in a fixed SRAM block (see the linker script) and the program
 * then spins, so openocd can halt and read them without a UART.
 */
#include <stdint.h>
#include "transform_fx.h"

#define DWT_CTRL      (*(volatile uint32_t *)0xE0001000u)
#define DWT_CYCCNT    (*(volatile uint32_t *)0xE0001004u)
#define DEMCR         (*(volatile uint32_t *)0xE000EDFCu)
#define DEMCR_TRCENA  (1u << 24)
#define DWT_CYCCNTENA (1u << 0)

#define TILES  256u
#define POINTS (TILES * 4u)

struct results {
    uint32_t magic;                  /* 0 until the run finishes */
    uint32_t tiles;
    uint32_t points;
    uint32_t cycles_naive;           /* rolled k loop */
    uint32_t cycles_opt;             /* unrolled k, point hoisted */
    uint32_t cycles_overhead;        /* same loop, no transform */
    uint32_t cycles_x1000_naive;     /* per point, net of overhead */
    uint32_t cycles_x1000_opt;
    uint32_t checksum;               /* guards against elimination */
};

__attribute__((section(".results"), used))
volatile struct results g_results;

/* The same transform the RTL benchmark uses: rotation (0.3, -0.7, 1.1) rad,
 * translation (10, -5, 2) m, quantized to Q1.14 with the translation column
 * divided by w = 8. Generated from golden/transform_ref.py, not hand-written,
 * so the baseline measures the same arithmetic the array does. */
static const int16_t k_matrix[16] = {
      5684, -15364,   -259,  20480,
     11168,   4320, -11183, -10240,
     10555,   3703,  11971,   4096,
         0,      0,      0,   2048,
};

static int16_t g_tiles[TILES][16];
static volatile uint32_t g_sink;

int main(void)
{
    /* .results is NOLOAD, so this is whatever was in SRAM. Clear the guard
     * first: a reader must not mistake stale memory for a finished run. */
    g_results.magic = 0;

    DEMCR |= DEMCR_TRCENA;
    DWT_CYCCNT = 0;
    DWT_CTRL |= DWT_CYCCNTENA;

    /* Build the inputs outside the timed region. */
    for (uint32_t t = 0; t < TILES; t++) {
        for (int i = 0; i < 12; i++)
            g_tiles[t][i] = (int16_t)(((int32_t)(t * 31u + (uint32_t)i * 7u) & 0x3FFF) - 8192);
        g_tiles[t][12] = g_tiles[t][13] = g_tiles[t][14] = g_tiles[t][15] = 2048; /* w, Q7.8 */
    }

    int32_t out[16];
    uint32_t checksum = 0;

    /* Warm flash prefetch and the branch predictor. */
    tfx_transform_tile(k_matrix, g_tiles[0], out);

    uint32_t t0 = DWT_CYCCNT;
    for (uint32_t t = 0; t < TILES; t++) {
        tfx_transform_tile(k_matrix, g_tiles[t], out);
        checksum += (uint32_t)out[0] ^ (uint32_t)out[15];
    }
    uint32_t t1 = DWT_CYCCNT;

    tfx_transform_tile_opt(k_matrix, g_tiles[0], out);   /* warm */
    uint32_t t4 = DWT_CYCCNT;
    for (uint32_t t = 0; t < TILES; t++) {
        tfx_transform_tile_opt(k_matrix, g_tiles[t], out);
        checksum += (uint32_t)out[0] ^ (uint32_t)out[15];
    }
    uint32_t t5 = DWT_CYCCNT;

    /* Same loop shape and the same memory traffic, without the transform, so
     * the loop and load cost can be subtracted. */
    uint32_t sink = 0;
    uint32_t t2 = DWT_CYCCNT;
    for (uint32_t t = 0; t < TILES; t++) {
        sink += (uint32_t)g_tiles[t][0] ^ (uint32_t)g_tiles[t][15];
    }
    uint32_t t3 = DWT_CYCCNT;
    g_sink = sink;

    uint32_t naive = t1 - t0;
    uint32_t opt = t5 - t4;
    uint32_t overhead = t3 - t2;
    uint32_t net_naive = naive > overhead ? naive - overhead : 0u;
    uint32_t net_opt = opt > overhead ? opt - overhead : 0u;

    g_results.tiles = TILES;
    g_results.points = POINTS;
    g_results.cycles_naive = naive;
    g_results.cycles_opt = opt;
    g_results.cycles_overhead = overhead;
    g_results.cycles_x1000_naive = (uint32_t)(((uint64_t)net_naive * 1000u) / POINTS);
    g_results.cycles_x1000_opt = (uint32_t)(((uint64_t)net_opt * 1000u) / POINTS);
    g_results.checksum = checksum;
    g_results.magic = 0x5A5A0003u;   /* written last; 3 = both variants */

    for (;;) { }
}
