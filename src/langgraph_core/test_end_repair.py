import re

code_fsm = """
always @(*) begin
    case (current_state)
        IDLE: begin
            if (IN == 1'b1) begin
                next_state = S1;
            end else begin
                next_state = IDLE;
            end
        end
        S5: begin
            if (IN == 1'b1) begin
                next_state = S1;
            end else begin
                next_state = IDLE;
            end
        end
        default: next_state = IDLE;
endcase

always @(posedge CLK or negedge RST) begin
    if (!RST) begin
        MATCH <= 1'b0;
    end else begin
        MATCH <= (next_state == S5) && (IN == 1'b1);
    end
end
endmodule
"""

code_sig = """
    always @(posedge clk or negedge rst_n) begin
        if (~rst_n) begin
            state <= 1'b0;
            wave <= 5'b0;
        end
        else begin
            case (state)
                1'b0: begin
                    wave <= wave + 1'b1;
                end
                1'b1: begin
                    wave <= wave - 1'b1;
                end
        endcase
    end
endmodule
"""

def _fix_missing_end(code_text):
    lines = code_text.splitlines()
    output = []
    begin_count = 0
    end_count = 0
    
    for line in lines:
        s = line.strip()
        
        is_top_level = re.match(r'^\s*(always|assign|initial|endmodule|module)\b', line)
        missing = begin_count - end_count
        
        if is_top_level and missing > 0:
            for _ in range(missing):
                output.append(line[:len(line) - len(line.lstrip())] + "end // Auto-repaired")
            begin_count = 0
            end_count = 0
            
        begin_count += len(re.findall(r'\bbegin\b', s))
        end_count += len(re.findall(r'\bend\b', s))
        
        output.append(line)
        
    return '\n'.join(output)

print("FSM FIXED:")
print(_fix_missing_end(code_fsm))

print("\nSIG FIXED:")
print(_fix_missing_end(code_sig))

