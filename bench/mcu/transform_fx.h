/* Fixed-point 4x4 homogeneous transform, matching golden/transform_ref.py.
 *
 * Same formats as ADR-0002: the matrix is Q1.14, the points Q7.8, and the
 * accumulator is 32 bits. This is the baseline the array is measured against,
 * and it is also a second independent implementation of the same arithmetic —
 * if it disagrees with the Python model on any vector, one of them is wrong.
 *
 * No hardware in this header. The same object builds for the host and for the
 * M4, so the cross-check runs natively before anything is flashed.
 */
#ifndef TRANSFORM_FX_H
#define TRANSFORM_FX_H

#include <stdint.h>

#define TFX_N 4

/* out[i][j] = sum_k m[i][k] * p[k][j], row-major, accumulated in 32 bits.
 *
 * The accumulator wraps, deliberately, because rtl/pe.sv's does: four
 * full-scale 16-bit products sum to 2^32 and ACC_W is 32. A reference that
 * promoted to 64 bits would disagree with correct RTL at the corner, which is
 * exactly where a reference has to be right (ADR-0002).
 */
void tfx_transform_tile(const int16_t m[TFX_N * TFX_N],
                        const int16_t p[TFX_N * TFX_N],
                        int32_t out[TFX_N * TFX_N]);

/* Same result, unrolled over k with the point's four components hoisted into
 * locals. The straightforward version above leaves the k loop rolled, so each
 * multiply-accumulate pays two loads, a compare and a taken branch; an M4 has
 * no branch predictor, so that dominates. Comparing the array against the naive
 * version would flatter the array, so both are measured. */
void tfx_transform_tile_opt(const int16_t m[TFX_N * TFX_N],
                            const int16_t p[TFX_N * TFX_N],
                            int32_t out[TFX_N * TFX_N]);

#endif /* TRANSFORM_FX_H */
