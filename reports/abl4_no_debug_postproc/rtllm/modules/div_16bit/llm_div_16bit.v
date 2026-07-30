module div_16bit(
    input [15:0] A,  // 16-bit dividend
    input [7:0] B,   // 8-bit divisor
    output reg [15:0] result, // 16-bit quotient
    output reg [15:0] odd     // 16-bit remainder
);

    reg [15:0] a_reg;
    reg [7:0] b_reg;
    reg [15:0] remainder;
    integer i;

    always @(*) begin
        a_reg = A;
        b_reg = B;
        result = 0;
        remainder = 0;

        for (i = 15; i >= 0; i = i - 1) begin
            remainder = {remainder[14:0], a_reg[i]}; // Shift in the next bit of the dividend
            if (remainder >= {8'b0, b_reg}) begin
                remainder = remainder - {8'b0, b_reg}; // Subtract divisor from remainder
                result[i] = 1; // Set quotient bit
            end
        end
        odd = remainder; // Final remainder
    end

endmodule
