// Synthesizable wrapper: the array plus a shift-chain readout.
//
// `systolic_4x4` exposes all sixteen accumulators as one flat vector. That is
// the right shape for verifying arithmetic and the wrong shape for a device:
// 16 x ACC_W is 512 bits, and an iCE40 HX8K has about 206 I/O. This wrapper
// reads the accumulators out one word per cycle instead, which is what makes
// the design placeable and what a host link would eventually drive (ADR-0005).
//
// Readout order is row-major, PE(i,j) at i*N + j, matching acc_flat's layout so
// the two agree by construction rather than by convention.
//
// `read_start` latches all sixteen accumulators at once, so the array may
// continue into the next tile while the previous result shifts out. The capture
// is a snapshot; it does not stall the array.

module systolic_4x4_top #(
    parameter int DATA_W = 8,
    parameter int ACC_W  = 32,
    parameter int N      = 4
) (
    input  logic                clk,
    input  logic                rst_n,
    // Array control, passed straight through. `clear` must be a single-cycle
    // pulse on the first enabled cycle of a tile: it is not gated by `en`, so
    // holding it while stalled would zero the accumulators (ADR-0004).
    input  logic                en,
    input  logic                clear,
    input  logic [N*DATA_W-1:0] a_in_flat,
    input  logic [N*DATA_W-1:0] b_in_flat,
    // Readout. Pulse `read_start`, then take one word per cycle while
    // `result_valid` is high. N*N words, row-major.
    input  logic                read_start,
    output logic [ACC_W-1:0]    result,
    output logic                result_valid,
    output logic                read_done
);

    localparam int WORDS    = N * N;
    localparam int CNT_W    = $clog2(WORDS + 1);

    logic [WORDS*ACC_W-1:0] acc_flat;

    systolic_4x4 #(
        .DATA_W(DATA_W),
        .ACC_W (ACC_W),
        .N     (N)
    ) u_array (
        .clk      (clk),
        .rst_n    (rst_n),
        .en       (en),
        .clear    (clear),
        .a_in_flat(a_in_flat),
        .b_in_flat(b_in_flat),
        .acc_flat (acc_flat)
    );

    logic [WORDS*ACC_W-1:0] shreg;
    logic [CNT_W-1:0]       count;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            shreg <= '0;
            count <= '0;
        end else if (read_start) begin
            // Snapshot every accumulator on one edge. Taking them one at a time
            // would let the array advance mid-readout and mix two tiles.
            shreg <= acc_flat;
            count <= CNT_W'(WORDS);
        end else if (count != '0) begin
            shreg <= shreg >> ACC_W;
            count <= count - 1'b1;
        end
    end

    assign result       = shreg[ACC_W-1:0];
    assign result_valid = (count != '0);
    assign read_done    = (count == '0);

endmodule
