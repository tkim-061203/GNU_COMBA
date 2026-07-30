module cla_16bit(input [15:0] A, input [15:0] B, input Cin, output [15:0] S, output Cout);
    wire [15:0] P, G;
    wire [15:0] C;
    assign P = A ^ B; // Propagate
    assign G = A & B; // Generate
    assign C[0] = Cin;
    genvar i;
    generate
        for (i = 0; i < 15; i = i + 1) begin: carry_gen
            assign C[i + 1] = G[i] | (P[i] & C[i]);
        end
    endgenerate
    assign S = P ^ C; // Adjusted to use full C size
    assign Cout = G[15] | (P[15] & C[15]); // Use G[15] for Cout
endmodule

module adder_32bit(input [31:0] A, input [31:0] B, output [31:0] S, output C32);
    wire [15:0] S0, S1;
    wire C0;
    wire C1; // Changed from wire [15:0] to wire for single bit carry-out

    // Instantiate two 16-bit CLA blocks
    cla_16bit cla0(.A(A[15:0]), .B(B[15:0]), .Cin(1'b0), .S(S0), .Cout(C0));
    cla_16bit cla1(.A(A[31:16]), .B(B[31:16]), .Cin(C0), .S(S1), .Cout(C1));

    // Combine results
    assign S = {S1, S0};
    assign C32 = C1; // Use the carry from the second CLA directly
endmodule
