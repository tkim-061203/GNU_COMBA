module alu(
    input  wire [31:0] a,
    input  wire [31:0] b,
    input  wire [5:0] aluc,
    output reg [31:0] r,
    output wire zero,
    output wire carry,
    output wire negative,
    output wire overflow,
    output reg flag
);

    parameter ADD  = 6'b100000;
    parameter ADDU = 6'b100001;
    parameter SUB  = 6'b100010;
    parameter SUBU = 6'b100011;
    parameter AND  = 6'b100100;
    parameter OR   = 6'b100101;
    parameter XOR  = 6'b100110;
    parameter NOR  = 6'b100111;
    parameter SLT  = 6'b101010;
    parameter SLTU = 6'b101011;
    parameter SLL  = 6'b000000;
    parameter SRL  = 6'b000010;
    parameter SRA  = 6'b000011;
    parameter SLLV = 6'b000100;
    parameter SRLV = 6'b000110;
    parameter SRAV = 6'b000111;
    parameter LUI  = 6'b001111;

    wire signed [31:0] signed_a = a;
    wire signed [31:0] signed_b = b;
    reg [31:0] res;

    assign zero = (res == 32'b0);
    assign negative = res[31];
    assign carry = (aluc == ADD || aluc == ADDU) ? (res < signed_a || res < signed_b) : 1'b0;
    assign overflow = ((aluc == ADD || aluc == SUB) && ((signed_a > 0 && signed_b > 0 && res < 0) || (signed_a < 0 && signed_b < 0 && res >= 0))); 

    always @(*) begin
        case (aluc)
            ADD:  res = a + b;
            ADDU: res = a + b;
            SUB:  res = a - b;
            SUBU: res = a - b;
            AND:  res = a & b;
            OR:   res = a | b;
            XOR:  res = a ^ b;
            NOR:  res = ~(a | b);
            SLT:  begin
                res = (signed_a < signed_b) ? 32'b1 : 32'b0;
                flag = 1'b1;
            end
            SLTU: begin
                res = (a < b) ? 32'b1 : 32'b0;
                flag = 1'b1;
            end
            SLL:  res = b << a[4:0];
            SRL:  res = b >> a[4:0];
            SRA:  res = $signed(b) >>> a[4:0];
            SLLV: res = b << (a & 32'h1F);
            SRLV: res = b >> (a & 32'h1F);
            SRAV: res = $signed(b) >>> (a & 32'h1F);
            LUI:  res = (a & 32'hFFFF) << 16;
            default: res = 32'b0;
        endcase
    end

    always @(*) begin
        r = res;
    end

    always @(*) begin
        if (aluc == SLT || aluc == SLTU) begin
            flag = 1'b1;
        end else begin
            flag = 1'b0;
        end
    end

    // Correcting the carry flag logic
    always @(*) begin
        if (aluc == ADD || aluc == ADDU) begin
            carry = (res < a) ? 1'b1 : 1'b0;
        end
    end

endmodule
