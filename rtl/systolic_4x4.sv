// 4x4 output-stationary systolic array.
//
// Sixteen `pe` cells. `a` flows west to east, `b` flows north to south, and
// each cell registers what it forwards, so one hop costs one cycle in both
// directions. That delay is what aligns the operands: with
// PE(i,j).a_in(t) = a_in[i](t-j) and PE(i,j).b_in(t) = b_in[j](t-i), a feeder
// that presents row i delayed by i cycles and column j delayed by j cycles
// gives PE(i,j) the pair (A[i][k], B[k][j]) with k = t-i-j. One k per cycle,
// correctly aligned, with no control logic arranging it (ADR-0001).
//
// Tile control is a single broadcast `clear` at t=0 with `en` held high for the
// whole tile (ADR-0004). PE(i,j) only has real operands during
// t = i+j .. K-1+i+j; outside that window the feeder presents zeros, the
// product is zero, and the accumulator is unchanged. So every cell can run for
// the whole tile and no per-cell start is needed. All 16 accumulators are
// valid at t = K + 2*(N-1).
//
// Ports are packed rather than unpacked arrays: Icarus's support for unpacked
// array ports is uneven, and a flat vector is what cocotb reads most reliably.
// acc_flat holds PE(i,j) at [(i*N + j)*ACC_W +: ACC_W].
//
// The flat accumulator output is deliberate and is not synthesizable onto a
// real part: 16 x 32 bits is 512 pins. `systolic_4x4_top` wraps this with a
// shift-chain readout for synthesis (ADR-0005). This module is the arithmetic.

module systolic_4x4 #(
    parameter int DATA_W = 8,
    parameter int ACC_W  = 32,
    parameter int N      = 4
) (
    input  logic                     clk,
    input  logic                     rst_n,
    input  logic                     en,
    input  logic                     clear,
    // West edge, one operand per row. Row i at [i*DATA_W +: DATA_W].
    input  logic [N*DATA_W-1:0]      a_in_flat,
    // North edge, one operand per column. Column j at [j*DATA_W +: DATA_W].
    input  logic [N*DATA_W-1:0]      b_in_flat,
    output logic [N*N*ACC_W-1:0]     acc_flat
);

    // a_h[i][j] is the operand entering PE(i,j) from the west, so a_h[i][0] is
    // the row's edge input and a_h[i][N] is the east edge, left unconnected.
    logic signed [DATA_W-1:0] a_h [N][N+1];
    logic signed [DATA_W-1:0] b_v [N+1][N];

    genvar i, j;

    generate
        for (i = 0; i < N; i++) begin : g_west_edge
            assign a_h[i][0] = a_in_flat[i*DATA_W +: DATA_W];
        end
        for (j = 0; j < N; j++) begin : g_north_edge
            assign b_v[0][j] = b_in_flat[j*DATA_W +: DATA_W];
        end

        for (i = 0; i < N; i++) begin : g_row
            for (j = 0; j < N; j++) begin : g_col
                logic signed [ACC_W-1:0] acc_ij;

                pe #(
                    .DATA_W(DATA_W),
                    .ACC_W (ACC_W)
                ) u_pe (
                    .clk  (clk),
                    .rst_n(rst_n),
                    .en   (en),
                    .clear(clear),
                    .a_in (a_h[i][j]),
                    .b_in (b_v[i][j]),
                    .a_out(a_h[i][j+1]),
                    .b_out(b_v[i+1][j]),
                    .acc  (acc_ij)
                );

                assign acc_flat[(i*N + j)*ACC_W +: ACC_W] = acc_ij;
            end
        end
    endgenerate

endmodule
