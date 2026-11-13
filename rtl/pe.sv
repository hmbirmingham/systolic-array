// Processing element: one multiply-accumulate cell of the systolic array.
//
// Output-stationary dataflow (ADR-0001). Each PE owns one element of the
// result matrix for the whole tile, so the accumulator never moves. Operands
// move instead: `a` travels west to east, `b` travels north to south, and each
// PE forwards what it received one cycle later. That one-cycle forward is what
// creates the diagonal wavefront the array depends on — PE(i,j) must see
// A[i][k] and B[k][j] in the same cycle, and it does because each hop costs
// exactly one cycle in both directions.
//
// Parameterised rather than fixed at 8 bits because the two benchmarks need
// different widths: the 3D transform runs fixed-point at DATA_W=16, the image
// filter at 8.

module pe #(
    parameter int DATA_W = 8,
    parameter int ACC_W  = 32
) (
    input  logic                     clk,
    input  logic                     rst_n,
    // Advance one MAC step. Held low, the PE stalls and keeps its accumulator,
    // which is what lets the array be fed from a slower source without losing
    // partial results.
    input  logic                     en,
    // Zero the accumulator between tiles. Independent of `en` on purpose: a
    // tile boundary should not have to burn a MAC step to clear.
    input  logic                     clear,
    input  logic signed [DATA_W-1:0] a_in,
    input  logic signed [DATA_W-1:0] b_in,
    output logic signed [DATA_W-1:0] a_out,
    output logic signed [DATA_W-1:0] b_out,
    output logic signed [ACC_W-1:0]  acc
);

    // Full-width product, no truncation: DATA_W x DATA_W needs 2*DATA_W bits
    // to hold every signed case, and the worst one is the most negative square
    // (-128 * -128 = +16384), which overflows a 2*DATA_W-1 result.
    logic signed [2*DATA_W-1:0] prod;
    assign prod = a_in * b_in;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            acc   <= '0;
            a_out <= '0;
            b_out <= '0;
        end else begin
            // Clear outranks accumulate. If both arrive together the tile is
            // starting, so the incoming product belongs to the new tile.
            if (clear) acc <= en ? ACC_W'(prod) : '0;
            else if (en) acc <= acc + ACC_W'(prod);

            // The operand pipeline runs whenever the array steps, and is not
            // affected by `clear` — a cleared accumulator still has to pass its
            // neighbours' operands along or the wavefront breaks downstream.
            if (en) begin
                a_out <= a_in;
                b_out <= b_in;
            end
        end
    end

endmodule
