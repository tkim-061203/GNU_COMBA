module multi_8bit(
    input [7:0] A,
    input [7:0] B,
    output reg [15:0] product
);

    integer i;

    always @(*) begin
        product = 16'b0; // Initialize product to 0
        for (i = 0; i < 8; i = i + 1) begin
            if (B[i]) begin
                product = product + ({8'b0, A} << i); // Add A shifted left by i, zero-extend A to 16 bits
            end
        end
    end

endmodule
