module adder_pipe_64bit(
    input wire clk,
    input wire rst_n,
    input wire i_en,
    input wire [63:0] adda,
    input wire [63:0] addb,
    output reg [64:0] result,
    output reg o_en
);

    reg [63:0] a_reg, b_reg;
    reg [64:0] sum_reg;
    reg i_en_reg;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            a_reg <= 64'b0;
            b_reg <= 64'b0;
            sum_reg <= 65'b0;
            i_en_reg <= 1'b0;
            o_en <= 1'b0;
            result <= 65'b0; // Initialize result to zero on reset
        end else begin
            if (i_en) begin
                a_reg <= adda;
                b_reg <= addb;
                sum_reg <= a_reg + b_reg;
                i_en_reg <= 1'b1;
            end
            if (i_en_reg) begin
                result <= sum_reg;
                o_en <= 1'b1;
                i_en_reg <= 1'b0;
            end else begin
                o_en <= 1'b0;
            end
        end
    end
endmodule
