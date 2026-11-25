/* Host harness: read tiles on stdin, print accumulators on stdout.
 *
 * Exists so the C transform can be held against golden/transform_ref.py before
 * it is trusted as a baseline. Input is one tile per line, 32 integers: 16
 * matrix entries then 16 point entries, row-major. Output is 16 accumulators.
 */
#include <stdio.h>
#include <stdint.h>
#include "transform_fx.h"

int main(void)
{
    int16_t m[16], p[16];
    int32_t out[16];
    long v;

    for (;;) {
        for (int i = 0; i < 16; i++) {
            if (scanf("%ld", &v) != 1) return 0;
            m[i] = (int16_t)v;
        }
        for (int i = 0; i < 16; i++) {
            if (scanf("%ld", &v) != 1) return 1;
            p[i] = (int16_t)v;
        }
        int32_t out_opt[16];
        tfx_transform_tile(m, p, out);
        tfx_transform_tile_opt(m, p, out_opt);
        /* The two implementations must agree with each other as well as with
         * the Python model, or one of them is not the baseline I measured. */
        for (int i = 0; i < 16; i++) {
            if (out[i] != out_opt[i]) {
                fprintf(stderr, "opt disagrees at %d: %ld vs %ld\n",
                        i, (long)out[i], (long)out_opt[i]);
                return 2;
            }
        }
        for (int i = 0; i < 16; i++)
            printf("%ld%c", (long)out[i], i == 15 ? '\n' : ' ');
    }
}
