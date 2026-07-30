module RAM # (
    parameter WIDTH=6, 
    parameter DEPTH=8
) (
	input clk,
	input rst_n,
	
	input write_en,
	input [$clog2(DEPTH)-1:0]write_addr,
	input [WIDTH-1:0]write_data,
	
	input read_en,
	input [$clog2(DEPTH)-1:0]read_addr,
	output reg [WIDTH-1:0]read_data
);
    
    //defination
    reg [WIDTH-1:0] internal_RAM [DEPTH-1:0];

    //output 
    integer i;
    always@(posedge clk or negedge rst_n)begin
        if(!rst_n) begin
               for(i = 0; i < DEPTH; i = i + 1) begin
                   internal_RAM[i] <= 'd0;
               end
        end
        else if(write_en) 
            internal_RAM[write_addr] <= write_data;
    end
    always@(posedge clk or negedge rst_n)begin
        if(!rst_n) 
            read_data <= 'd0;
        else if(read_en) 
            read_data <= internal_RAM[read_addr];
        else 
            read_data <= 'd0;
    end
endmodule
