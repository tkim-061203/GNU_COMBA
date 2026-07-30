module dual_port_RAM #(parameter DEPTH = 16, parameter WIDTH = 8) (
    input wclk,
    input wenc,
    input [$clog2(DEPTH)-1:0] waddr,
    input [WIDTH-1:0] wdata,
    input rclk,
    input renc,
    input [$clog2(DEPTH)-1:0] raddr,
    output reg [WIDTH-1:0] rdata
);
    reg [WIDTH-1:0] RAM_MEM [0:DEPTH-1];

    always @(posedge wclk) begin
        if (wenc) begin
            RAM_MEM[waddr] <= wdata;
        end
    end

    always @(posedge rclk) begin
        if (renc) begin
            rdata <= RAM_MEM[raddr];
        end
    end
endmodule

module asyn_fifo #(parameter WIDTH = 8, parameter DEPTH = 16) (
    input wclk,
    input rclk,
    input wrstn,
    input rrstn,
    input winc,
    input rinc,
    input [WIDTH-1:0] wdata,
    output reg wfull,
    output reg rempty,
    output reg [WIDTH-1:0] rdata
);

    localparam ADDR_WIDTH = $clog2(DEPTH);
    reg [ADDR_WIDTH-1:0] waddr_bin, raddr_bin;
    reg [ADDR_WIDTH-1:0] wptr, rptr;
    reg [ADDR_WIDTH-1:0] wptr_buff, rptr_buff;
    reg wenc;

    // Dual-port RAM instance
    dual_port_RAM #(DEPTH, WIDTH) ram (
        .wclk(wclk),
        .wenc(wenc),
        .waddr(waddr_bin),
        .wdata(wdata),
        .rclk(rclk),
        .renc(rinc),
        .raddr(raddr_bin),
        .rdata(rdata)
    );

    // Write pointer logic
    always @(posedge wclk or negedge wrstn) begin
        if (!wrstn) begin
            waddr_bin <= 0;
            wptr <= 0;
            wenc <= 0;
        end else if (winc) begin
            waddr_bin <= wptr; // Use wptr for addressing
            wenc <= 1; // Enable write
            wptr <= wptr + 1; // Increment write pointer
        end else begin
            wenc <= 0; // Disable write when not writing
        end
    end

    // Read pointer logic
    always @(posedge rclk or negedge rrstn) begin
        if (!rrstn) begin
            raddr_bin <= 0;
            rptr <= 0;
        end else if (rinc) begin
            raddr_bin <= rptr; // Use rptr for addressing
            rptr <= rptr + 1; // Increment read pointer
        end
    end

    // Gray code conversion
    wire [ADDR_WIDTH-1:0] wptr_gray = (wptr >> 1) ^ wptr;
    wire [ADDR_WIDTH-1:0] rptr_gray = (rptr >> 1) ^ rptr;

    // Pointer buffers for synchronization
    always @(posedge wclk) begin
        wptr_buff <= wptr_gray;
    end

    always @(posedge rclk) begin
        rptr_buff <= rptr_gray;
    end

    // Full and empty signal generation
    always @* begin
        wfull = (wptr_buff[ADDR_WIDTH-1] ^ rptr_buff[ADDR_WIDTH-1]) && (wptr_buff[ADDR_WIDTH-2:0] == rptr_buff[ADDR_WIDTH-2:0]);
        rempty = (wptr_buff == rptr_buff);
    end
endmodule
