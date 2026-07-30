module RAM(
    input clk,
    input rst_n,
    input write_en,
    input [2:0] write_addr,
    input [5:0] write_data,
    input read_en,
    input [2:0] read_addr,
    output reg [5:0] read_data
);

    parameter WIDTH = 6;
    parameter DEPTH = 8;

    reg [WIDTH-1:0] ram_array [0:DEPTH-1]; // Changed RAM to ram_array to avoid naming conflict

    // Write operation
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            // Reset all memory locations to 0
            integer i;
            for (i = 0; i < DEPTH; i = i + 1) begin
                ram_array[i] <= 6'b000000;
            end
        end else if (write_en) begin
            // Write data to RAM at specified address
            ram_array[write_addr] <= write_data;
        end
    end

    // Read operation
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            read_data <= 6'b000000;
        end else if (read_en) begin
            // Read data from RAM at specified address
            read_data <= ram_array[read_addr];
        end else begin
            read_data <= 6'b000000;
        end
    end

endmodule
