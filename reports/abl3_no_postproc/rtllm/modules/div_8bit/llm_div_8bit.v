module div_8bit(
    input clk,
    input rst,
    input sign,
    input [7:0] dividend,
    input [7:0] divisor,
    input opn_valid,
    input res_ready,
    output reg res_valid,
    output reg [15:0] result
);

    reg [7:0] abs_dividend;
    reg [7:0] abs_divisor;
    reg [7:0] NEG_DIVISOR;
    reg [15:0] SR;
    reg [3:0] cnt;
    reg start_cnt;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            res_valid <= 0;
            result <= 0;
            cnt <= 0;
            start_cnt <= 0;
            SR <= 0;
        end else begin
            if (opn_valid && !res_valid) begin
                abs_dividend <= (sign && dividend[7]) ? ~dividend + 1 : dividend;
                abs_divisor <= (sign && divisor[7]) ? ~divisor + 1 : divisor;
                NEG_DIVISOR <= ~abs_divisor + 1;
                SR <= {abs_dividend, 1'b0};
                cnt <= 1;
                start_cnt <= 1;
                res_valid <= 0;
            end

            if (start_cnt) begin
                if (cnt == 8) begin
                    start_cnt <= 0;
                    res_valid <= 1;
                    result <= {SR[7:0], SR[15:8]}; // Fix: Set result to {remainder, quotient}
                end else begin
                    // Perform division step
                    SR <= {SR[14:0], 1'b0}; // Shift left
                    if (SR[15:8] >= abs_divisor) begin
                        SR[15:8] <= SR[15:8] + NEG_DIVISOR;
                        SR[7:0] <= SR[7:0] | 1'b1; // Set quotient bit
                    end
                    cnt <= cnt + 1;
                end
            end

            if (res_valid && res_ready) begin
                res_valid <= 0;
            end
        end
    end
endmodule
