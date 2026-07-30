module adder_32bit(
    input [32:1] A,
    input [32:1] B,
    output [32:1] S,
    output C32
);
    wire [0:0] c_intermediate; // Intermediate carry signals between 16-bit blocks

    // First 16-bit CLA block (lower half)
    cla_16bit cla_lower(
        .a(A[16:1]),
        .b(B[16:1]),
        .cin(1'b0),
        .sum(S[16:1]),
        .cout(c_intermediate[0]),
        .p_group(),
        .g_group()
    );

    // Second 16-bit CLA block (upper half)
    cla_16bit cla_upper(
        .a(A[32:17]),
        .b(B[32:17]),
        .cin(c_intermediate[0]),
        .sum(S[32:17]),
        .cout(C32),
        .p_group(),
        .g_group()
    );
endmodule

module cla_16bit(
    input [15:0] a,
    input [15:0] b,
    input cin,
    output [15:0] sum,
    output cout,
    output p_group,
    output g_group
);
    wire [3:0] p_4bit; // Propagate signals for 4-bit blocks
    wire [3:0] g_4bit; // Generate signals for 4-bit blocks
    wire [3:0] c_16bit; // Intermediate carry signals

    // First 4-bit block
    cla_4bit cla_block0(
        .a(a[3:0]),
        .b(b[3:0]),
        .cin(cin),
        .sum(sum[3:0]),
        .cout(c_16bit[0]),
        .p_group(p_4bit[0]),
        .g_group(g_4bit[0])
    );

    // Second 4-bit block
    cla_4bit cla_block1(
        .a(a[7:4]),
        .b(b[7:4]),
        .cin(c_16bit[0]),
        .sum(sum[7:4]),
        .cout(c_16bit[1]),
        .p_group(p_4bit[1]),
        .g_group(g_4bit[1])
    );

    // Third 4-bit block
    cla_4bit cla_block2(
        .a(a[11:8]),
        .b(b[11:8]),
        .cin(c_16bit[1]),
        .sum(sum[11:8]),
        .cout(c_16bit[2]),
        .p_group(p_4bit[2]),
        .g_group(g_4bit[2])
    );

    // Fourth 4-bit block
    cla_4bit cla_block3(
        .a(a[15:12]),
        .b(b[15:12]),
        .cin(c_16bit[2]),
        .sum(sum[15:12]),
        .cout(c_16bit[3]),
        .p_group(p_4bit[3]),
        .g_group(g_4bit[3])
    );

    // Group Propagate and Generate calculations
    assign p_group = p_4bit[0] & p_4bit[1] & p_4bit[2] & p_4bit[3];
    assign g_group = g_4bit[3] | 
                    (g_4bit[2] & p_4bit[3]) | 
                    (g_4bit[1] & p_4bit[3] & p_4bit[2]) | 
                    (g_4bit[0] & p_4bit[3] & p_4bit[2] & p_4bit[1]);

    // Carry out
    assign cout = c_16bit[3];
endmodule

module cla_4bit(
    input [3:0] a,
    input [3:0] b,
    input cin,
    output [3:0] sum,
    output cout,
    output p_group,
    output g_group
);
    wire [3:0] p; // Propagate signals
    wire [3:0] g; // Generate signals
    wire [4:0] c; // Carry signals

    // Generate and Propagate calculations
    assign p = a ^ b;
    assign g = a & b;

    // Carry calculations
    assign c[0] = cin;
    assign c[1] = g[0] | (p[0] & c[0]);
    assign c[2] = g[1] | (p[1] & c[1]);
    assign c[3] = g[2] | (p[2] & c[2]);
    assign c[4] = g[3] | (p[3] & c[3]);

    // Sum calculations
    assign sum = p ^ {c[3:0]};

    // Group Propagate and Generate
    assign p_group = p[0] & p[1] & p[2] & p[3];
    assign g_group = g[3] | (g[2] & p[3]) | (g[1] & p[3] & p[2]) | (g[0] & p[3] & p[2] & p[1]);

    // Carry out
    assign cout = c[4];
endmodule
