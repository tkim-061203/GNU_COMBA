`timescale 1ns / 1ps

module alu(
    input [31:0] a,
    input [31:0] b,
    input [5:0] aluc,
    output [31:0] r,
    output zero,
    output reg carry,
    output negative,
    output reg overflow,
    output flag
    );
    
    parameter ADD = 6'b100000;
    parameter ADDU = 6'b100001;
    parameter SUB = 6'b100010;
    parameter SUBU = 6'b100011;
    parameter AND = 6'b100100;
    parameter OR = 6'b100101;
    parameter XOR = 6'b100110;
    parameter NOR = 6'b100111;
    parameter SLT = 6'b101010;
    parameter SLTU = 6'b101011;
    parameter SLL = 6'b000000;
    parameter SRL = 6'b000010;
    parameter SRA = 6'b000011;
    parameter SLLV = 6'b000100;
    parameter SRLV = 6'b000110;
    parameter SRAV = 6'b000111;
    parameter LUI = 6'b001111;
      
    wire signed [31:0] a_signed;
    wire signed [31:0] b_signed;    
  
    reg [32:0] res;
    
    assign a_signed = a;
    assign b_signed = b;
    assign r = res[31:0];
    
    assign flag = (aluc == SLT || aluc == SLTU) ? ((aluc == SLT) ? (a_signed < b_signed) : (a < b)) : 1'b0;
    assign zero = (res[31:0] == 32'b0) ? 1'b1 : 1'b0;
    assign negative = r[31];

    always @ (*)
    begin
        carry    = 0;
        overflow = 0;
        case(aluc)
            ADD: begin
                res = a_signed + b_signed;
                carry = res[32];
                overflow = ((~a[31] & ~b[31] & r[31]) | (a[31] & b[31] & ~r[31]));
            end
            ADDU: begin
                res = a + b;
                carry = res[32];
                overflow = 0;
            end
            SUB: begin 
                res = a_signed - b_signed;
                carry = res[32];
                overflow = ((a[31] & ~b[31] & ~r[31]) | (~a[31] & ~b[31] & r[31]));
            end
            SUBU: begin 
                res = a - b;
                carry = res[32];
                overflow = 0;
            end
            AND: begin
                res = {1'b0, a} & {1'b0, b};
            end
            OR: begin
                res = {1'b0, a} | {1'b0, b};
            end
            XOR: begin
                res = {1'b0, a} ^ {1'b0, b};
            end
            NOR: begin
                res = ~({1'b0, a} | {1'b0, b});
            end
            SLT: begin
                res = a_signed < b_signed ? 1 : 0;
            end
            SLTU: begin
                res = a < b ? 1 : 0;
            end
            SLL: begin
                res = {1'b0, b} << {1'b0, a};
            end
            SRL: begin
                res = {1'b0, b} >> {1'b0, a};
            end
            SRA: begin
                res = {1'b0, b_signed} >>> {1'b0, a_signed};
            end
            SLLV: begin
                res = {1'b0, b} << {28'b0, a[4:0]};
            end
            SRLV: begin
                res = {1'b0, b} >> {28'b0, a[4:0]};
            end
            SRAV: begin
                res = {1'b0,b_signed} >>> {28'b0, a_signed[4:0]};
            end
            LUI: begin
                res = {1'b0, a[15:0], 16'h0000};
            end
            default:
            begin
                res = 33'b0;
            end
        endcase
    end
endmodule
