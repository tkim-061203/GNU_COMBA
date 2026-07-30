module edge_detect(
    input wire clk,
    input wire rst_n,
    input wire a,
    output reg rise,
    output reg down
);

    reg a_prev;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rise <= 0;
            down <= 0;
            a_prev <= 0;
        end else begin
            // Detect rising edge
            if (a && !a_prev) begin
                rise <= 1;
            end else begin
                rise <= 0;
            end

            // Detect falling edge
            if (!a && a_prev) begin
                down <= 1;
            end else begin
                down <= 0;
            end

            // Store the previous state of a
            a_prev <= a;
        end
    end
endmodule
