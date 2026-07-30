module JC_counter(
    input clk,
    input rst_n,
    output reg [63:0] Q
);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            Q <= 64'b0; // Reset condition
        end else begin
            if (Q[0] == 1'b0) begin
                Q <= {Q[62:0], 1'b1}; // Increment: Shift right and append 1
            end else begin
                Q <= {Q[62:0], 1'b0}; // Decrement: Shift right and append 0
            end
        end
    end

    // Initialize the counter to the first state after reset
    initial begin
        Q = 64'b0; // Ensure Q starts at 0
    end

endmodule
