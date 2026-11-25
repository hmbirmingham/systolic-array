#include "transform_fx.h"

void tfx_transform_tile(const int16_t m[TFX_N * TFX_N],
                        const int16_t p[TFX_N * TFX_N],
                        int32_t out[TFX_N * TFX_N])
{
    for (int i = 0; i < TFX_N; i++) {
        for (int j = 0; j < TFX_N; j++) {
            /* Accumulate through uint32_t on purpose. int16 * int16 promotes to
             * int, so each product fits; but signed overflow on the sum would be
             * undefined, and the RTL's accumulator wraps. Unsigned wraparound is
             * defined in C and is two's complement, so this reproduces the
             * hardware exactly rather than relying on how the compiler feels
             * about signed overflow. */
            uint32_t acc = 0;
            for (int k = 0; k < TFX_N; k++) {
                int32_t prod = (int32_t)m[i * TFX_N + k] * (int32_t)p[k * TFX_N + j];
                acc += (uint32_t)prod;
            }
            out[i * TFX_N + j] = (int32_t)acc;
        }
    }
}

void tfx_transform_tile_opt(const int16_t m[TFX_N * TFX_N],
                            const int16_t p[TFX_N * TFX_N],
                            int32_t out[TFX_N * TFX_N])
{
    for (int j = 0; j < TFX_N; j++) {
        /* One load per component per point instead of one per MAC. */
        const int32_t p0 = p[0 * TFX_N + j];
        const int32_t p1 = p[1 * TFX_N + j];
        const int32_t p2 = p[2 * TFX_N + j];
        const int32_t p3 = p[3 * TFX_N + j];

        for (int i = 0; i < TFX_N; i++) {
            const int16_t *mr = &m[i * TFX_N];
            /* uint32_t for the same reason as above: the accumulator wraps and
             * signed overflow would be undefined. */
            uint32_t acc = (uint32_t)((int32_t)mr[0] * p0);
            acc += (uint32_t)((int32_t)mr[1] * p1);
            acc += (uint32_t)((int32_t)mr[2] * p2);
            acc += (uint32_t)((int32_t)mr[3] * p3);
            out[i * TFX_N + j] = (int32_t)acc;
        }
    }
}
