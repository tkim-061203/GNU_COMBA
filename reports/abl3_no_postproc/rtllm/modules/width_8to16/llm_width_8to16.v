module width_8to16(
    input wire clk,
    input wire rst_n,
    input wire valid_in,
    input wire [7:0] data_in,
    output reg valid_out,
    output reg [15:0] data_out
);

    reg [7:0] data_lock;
    reg data_ready;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            data_out <= 16'b0;
            valid_out <= 1'b0;
            data_lock <= 8'b0;
            data_ready <= 1'b0;
        end else begin
            if (valid_in) begin
                if (!data_ready) begin
                    // Store the first valid data
                    data_lock <= data_in;
                    data_ready <= 1'b1;
                    valid_out <= 1'b0; // Output not valid yet
                end else begin
                    // Concatenate the stored data and the new data
                    data_out <= {data_lock, data_in};
                    valid_out <= 1'b1; // Output is valid
                    data_ready <= 1'b0; // Reset the ready flag
                end
            end
        end
    end

endmodule
