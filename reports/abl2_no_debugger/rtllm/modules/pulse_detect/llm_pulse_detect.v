module pulse_detect(
    input clk,
    input rst_n,
    input data_in,
    output reg data_out
);

    // State encoding
    typedef enum reg [1:0] {
        IDLE = 2'b00,
        HIGH = 2'b01,
        LOW = 2'b10
    } state_t;

    state_t state, next_state;

    // Sequential logic for state transition
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= IDLE;
            data_out <= 0;
        end else begin
            state <= next_state;
        end
    end

    // Combinational logic for next state
    always @(*) begin
        case (state)
            IDLE: begin
                if (data_in) begin
                    next_state = HIGH;
                end else begin
                    next_state = IDLE;
                end
            end
            HIGH: begin
                if (!data_in) begin
                    next_state = LOW;
                end else begin
                    next_state = HIGH;
                end
            end
            LOW: begin
                if (data_in) begin
                    next_state = HIGH;
                end else begin
                    next_state = IDLE;
                end
            end
            default: begin
                next_state = IDLE;
            end
        endcase
    end

    // Output logic based on state
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            data_out <= 0; // Reset output
        end else begin
            if (state == LOW && next_state == IDLE) begin
                data_out <= 1; // Set data_out to 1 at the end of a pulse
            end else begin
                data_out <= 0; // Reset output when not in pulse
            end
        end
    end
endmodule
