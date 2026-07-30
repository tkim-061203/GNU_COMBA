module fsm(
    input wire IN,
    input wire CLK,
    input wire RST,
    output reg MATCH
);

    // State encoding
    typedef enum reg [2:0] {
        S0, // Initial state
        S1, // Detected 1
        S2, // Detected 10
        S3, // Detected 100
        S4  // Detected 1001
    } state_t;

    state_t current_state, next_state;

    // State transition logic
    always @(*) begin
        case (current_state)
            S0: next_state = (IN) ? S1 : S0;
            S1: next_state = (IN) ? S1 : S2;
            S2: next_state = (IN) ? S3 : S0;
            S3: next_state = (IN) ? S4 : S0;
            S4: next_state = (IN) ? S1 : S0;
            default: next_state = S0;
        endcase
    end

    // State update on clock edge
    always @(posedge CLK or posedge RST) begin
        if (RST) begin
            current_state <= S0;
            MATCH <= 0;
        end else begin
            current_state <= next_state;
            // Set MATCH signal
            if (current_state == S4 && IN) begin
                MATCH <= 1;
            end else if (current_state == S0) begin
                MATCH <= 0;
            end else if (current_state == S1 && IN) begin
                MATCH <= 1; // Set MATCH when in state S1 and IN is 1
            end else begin
                MATCH <= 0; // Ensure MATCH is reset in other states
            end
        end
    end

endmodule
