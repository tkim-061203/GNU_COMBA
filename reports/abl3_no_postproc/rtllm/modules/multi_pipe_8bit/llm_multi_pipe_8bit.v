module multi_pipe_8bit(
    input wire clk,
    input wire rst_n,
    input wire mul_en_in,
    input wire [7:0] mul_a,
    input wire [7:0] mul_b,
    output reg mul_en_out,
    output reg [15:0] mul_out
);

    reg mul_en_out_reg;
    reg [7:0] mul_a_reg;
    reg [7:0] mul_b_reg;
    reg [15:0] partial_products [0:7];
    reg [15:0] mul_out_reg;

    integer i;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            mul_en_out_reg <= 1'b0;
            mul_a_reg <= 8'b0;
            mul_b_reg <= 8'b0;
            mul_out_reg <= 16'b0;
            mul_out <= 16'b0;
            mul_en_out <= 1'b0; // Ensure output is reset
        end else begin
            mul_en_out_reg <= mul_en_in;
            if (mul_en_in) begin
                mul_a_reg <= mul_a;
                mul_b_reg <= mul_b;
            end
        end
    end

    always @(*) begin
        for (i = 0; i < 8; i = i + 1) begin
            partial_products[i] = (mul_b_reg[i] ? mul_a_reg : 8'b0) << i;
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            mul_out_reg <= 16'b0;
        end else if (mul_en_out_reg) begin
            mul_out_reg <= 16'b0;
            for (i = 0; i < 8; i = i + 1) begin
                mul_out_reg <= mul_out_reg + partial_products[i];
            end
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            mul_out <= 16'b0;
            mul_en_out <= 1'b0; // Ensure output is reset
        end else begin
            mul_en_out <= mul_en_out_reg;
            if (mul_en_out_reg) begin
                mul_out <= mul_out_reg;
            end else begin
                mul_out <= 16'b0;
            end
        end
    end

endmodule
