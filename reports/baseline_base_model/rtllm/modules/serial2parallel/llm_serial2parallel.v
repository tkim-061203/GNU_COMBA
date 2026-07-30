module serial2parallel(
    input wire clk,
    input wire rst_n,
    input wire din_serial,
    input wire din_valid,
    output reg [7:0] dout_parallel,
    output reg dout_valid
);

    reg [3:0] cnt;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cnt <= 0;
            dout_parallel <= 8'b0;
            dout_valid <= 0;
        end else begin
            if (din_valid) begin
                dout_parallel <= {dout_parallel[6:0], din_serial};
                cnt <= cnt + 1;
                if (cnt == 7) begin
                    dout_valid <= 1;
                end else begin
                    dout_valid <= 0;
                end
            end
            if (cnt == 7) begin
                cnt <= 0; // Reset counter after 8 bits
                dout_valid <= 0; // Reset dout_valid after output is read
            end
        end
    end

endmodule
