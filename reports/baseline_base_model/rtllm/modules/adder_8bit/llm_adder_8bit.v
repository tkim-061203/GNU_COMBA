module adder_8bit(
    input [7:0] a,
    input [7:0] b,
    input cin,
    output [7:0] sum,
    output cout
);

    wire [6:0] carry_out_temp; // Temporary carry wire

    // Full adder for bit 0
    assign sum[0] = a[0] ^ b[0] ^ cin;
    assign carry_out_temp[0] = (a[0] & b[0]) | (cin & (a[0] ^ b[0]));

    // Full adder for bit 1
    assign sum[1] = a[1] ^ b[1] ^ carry_out_temp[0];
    assign carry_out_temp[1] = (a[1] & b[1]) | (carry_out_temp[0] & (a[1] ^ b[1]));

    // Full adder for bit 2
    assign sum[2] = a[2] ^ b[2] ^ carry_out_temp[1];
    assign carry_out_temp[2] = (a[2] & b[2]) | (carry_out_temp[1] & (a[2] ^ b[2]));

    // Full adder for bit 3
    assign sum[3] = a[3] ^ b[3] ^ carry_out_temp[2];
    assign carry_out_temp[3] = (a[3] & b[3]) | (carry_out_temp[2] & (a[3] ^ b[3]));

    // Full adder for bit 4
    assign sum[4] = a[4] ^ b[4] ^ carry_out_temp[3];
    assign carry_out_temp[4] = (a[4] & b[4]) | (carry_out_temp[3] & (a[4] ^ b[4]));

    // Full adder for bit 5
    assign sum[5] = a[5] ^ b[5] ^ carry_out_temp[4];
    assign carry_out_temp[5] = (a[5] & b[5]) | (carry_out_temp[4] & (a[5] ^ b[5]));

    // Full adder for bit 6
    assign sum[6] = a[6] ^ b[6] ^ carry_out_temp[5];
    assign carry_out_temp[6] = (a[6] & b[6]) | (carry_out_temp[5] & (a[6] ^ b[6]));

    // Full adder for bit 7
    assign sum[7] = a[7] ^ b[7] ^ carry_out_temp[6];
    assign cout = (a[7] & b[7]) | (carry_out_temp[6] & (a[7] ^ b[7]));

endmodule
