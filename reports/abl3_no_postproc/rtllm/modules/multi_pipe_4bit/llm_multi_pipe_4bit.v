module multi_pipe_4bit(
    input clk,
    input rst_n,
    input [3:0] mul_a,
    input [3:0] mul_b,
    output reg [7:0] mul_out
);

    parameter size = 4;
    reg [7:0] partial_products [0:size-1];
    reg [7:0] sum_reg;
    integer i;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            // Reset condition
            mul_out <= 8'd0;
            sum_reg <= 8'd0;
            for (i = 0; i < size; i = i + 1) begin
                partial_products[i] <= 8'd0;
            end
        end else begin
            // Generate partial products
            for (i = 0; i < size; i = i + 1) begin
                if (mul_b[i]) begin
                    partial_products[i] <= {mul_a, 4'b0} >> (size - 1 - i); // Corrected shift direction
                end else begin
                    partial_products[i] <= 8'd0;
                end
            end

            // Add partial products
            sum_reg <= 8'd0;
            for (i = 0; i < size; i = i + 1) begin
                sum_reg <= sum_reg + partial_products[i];
            end

            // Update final product output
            mul_out <= sum_reg;
        end
    end
endmodule
