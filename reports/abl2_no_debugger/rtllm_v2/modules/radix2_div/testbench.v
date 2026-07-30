`timescale 1ns/1ps

module radix2_div_tb;
    reg clk;
    reg rst;
    reg [7:0] dividend, divisor;
    reg sign;
    reg opn_valid;
    reg res_ready;
    wire res_valid;
    wire [15:0] result;

    // Instantiate the radix2_div module
    radix2_div uut (
        .clk(clk),
        .rst(rst),
        .dividend(dividend),
        .divisor(divisor),
        .sign(sign),
        .opn_valid(opn_valid),
        .res_valid(res_valid),
        .res_ready(res_ready),
        .result(result)
    );

    integer i;
    integer error = 0;
    reg [7:0] a_test [0:7];
    reg [7:0] b_test [0:7];
    reg [15:0] expected_result [0:7];
    reg sign_test [0:7];

    initial begin
        clk = 0;
        forever #5 clk = ~clk;
    end

    initial begin
        // Initialize test vectors
        a_test[0] = 8'd100; b_test[0] = 8'd10; sign_test[0] = 0; expected_result[0] = {8'd0, 8'd10};
        a_test[1] = -8'd100; b_test[1] = 8'd10; sign_test[1] = 1; expected_result[1] = {8'd0, -8'd10};
        a_test[2] = 8'd100; b_test[2] = -8'd10; sign_test[2] = 1; expected_result[2] = {8'd0, -8'd10};
        a_test[3] = -8'd100; b_test[3] = -8'd10; sign_test[3] = 1; expected_result[3] = {8'd0, 8'd10};
        a_test[4] = 8'd123; b_test[4] = 8'd123; sign_test[4] = 0; expected_result[4] = {8'd0, 8'd1};
        a_test[5] = 8'd0; b_test[5] = 8'd123; sign_test[5] = 0; expected_result[5] = {8'd0, 8'd0};
        a_test[6] = 8'd123; b_test[6] = 8'd251; sign_test[6] = 0; expected_result[6] = {8'd123, 8'd0};
        a_test[7] = 8'd255; b_test[7] = 8'd7; sign_test[7] = 0; expected_result[7] = {8'd3, 8'd36};

        // Initialize
        rst = 1;
        opn_valid = 0;
        res_ready = 1;
        #20;
        rst = 0;

        // Drive all stimulus at negedge so it never races the DUT's posedge
        // sampling (the old '#10 after wait(res_valid)' resynced the driver
        // onto posedge times and corrupted operand capture).
        for (i = 0; i < 8; i = i + 1) begin
            @(negedge clk);
            dividend = a_test[i];
            divisor = b_test[i];
            sign = sign_test[i];
            opn_valid = 1;
            @(negedge clk);
            opn_valid = 0;

            // Wait for result
            wait(res_valid);
            @(negedge clk);

            // Check result
            if (result !== expected_result[i]) begin
                error = error + 1;
                $display("Error: dividend=%d, divisor=%d, sign=%b, expected=%h, got=%h", a_test[i], b_test[i], sign_test[i], expected_result[i], result);
            end
        end

        // Display final result
        if (error == 0) begin
            $display("===========Your Design Passed===========");
        end else begin
            $display("===========Failed=========== (%0d errors)", error);
        end

        $finish;
    end

    // Watchdog: broken DUTs that never assert res_valid must not hang the sim
    initial begin
        #20000;
        $display("===========Error: testbench timeout waiting for res_valid===========");
        $finish;
    end
endmodule
