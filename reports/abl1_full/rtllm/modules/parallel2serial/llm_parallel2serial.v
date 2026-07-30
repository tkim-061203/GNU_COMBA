module parallel2serial(
    input clk,
    input rst_n,
    input [3:0] d,
    output reg valid_out,
    output reg dout
);

    reg [3:0] data;
    reg [1:0] cnt;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cnt <= 2'b00;
            valid_out <= 1'b0;
            dout <= 1'b0;
            data <= 4'b0000;
        end else begin
            if (cnt == 2'b00) begin
                data <= d; // Load parallel data
                cnt <= 2'b01; // Set counter to 1 for first output
                valid_out <= 1'b1; // Set valid output
            end else if (cnt < 2'b11) begin
                dout <= data[3]; // Output MSB
                data <= {data[2:0], 1'b0}; // Shift left
                cnt <= cnt + 1; // Increment counter
                valid_out <= 1'b0; // Clear valid output
            end else begin
                dout <= data[3]; // Output last bit
                valid_out <= 1'b0; // Clear valid output after last bit
                cnt <= 2'b00; // Reset counter after last output
            end
        end
    end
endmodule
