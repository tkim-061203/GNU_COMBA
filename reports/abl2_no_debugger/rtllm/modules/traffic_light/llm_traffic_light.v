module traffic_light(
    input wire rst_n,
    input wire clk,
    input wire pass_request,
    output reg [7:0] clock,
    output reg red,
    output reg yellow,
    output reg green
);

    // State enumeration
    typedef enum reg [1:0] {
        idle = 2'b00,
        s1_red = 2'b01,
        s2_yellow = 2'b10,
        s3_green = 2'b11
    } state_t;

    // Registers
    reg [7:0] cnt;
    state_t state, next_state;
    reg p_red, p_yellow, p_green;

    // State transition logic
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= idle;
            cnt <= 8'd10; // Initialize counter on reset
        end else begin
            state <= next_state;
        end
    end

    // Next state logic
    always @(*) begin
        case (state)
            idle: begin
                next_state = s1_red;
            end
            s1_red: begin
                if (cnt == 0) begin
                    next_state = s3_green;
                end else begin
                    next_state = s1_red;
                end
            end
            s2_yellow: begin
                if (cnt == 0) begin
                    next_state = s1_red;
                end else begin
                    next_state = s2_yellow;
                end
            end
            s3_green: begin
                if (cnt == 0) begin
                    next_state = s2_yellow;
                end else begin
                    next_state = s3_green;
                end
            end
            default: begin
                next_state = idle;
            end
        endcase
    end

    // Counter logic
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cnt <= 8'd10;
        end else begin
            if (pass_request && green) begin
                cnt <= 8'd10;
            end else if (!green && p_green) begin
                cnt <= 8'd60;
            end else if (!yellow && p_yellow) begin
                cnt <= 8'd5;
            end else if (!red && p_red) begin
                cnt <= 8'd10;
            end else begin
                if (cnt > 0) begin
                    cnt <= cnt - 1;
                end
            end
        end
    end

    // Output logic
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            p_red <= 0;
            p_yellow <= 0;
            p_green <= 0;
            red <= 0;
            yellow <= 0;
            green <= 0;
        end else begin
            p_red <= red;
            p_yellow <= yellow;
            p_green <= green;
            case (state)
                s1_red: begin
                    red <= 1;
                    yellow <= 0;
                    green <= 0;
                end
                s2_yellow: begin
                    red <= 0;
                    yellow <= 1;
                    green <= 0;
                end
                s3_green: begin
                    red <= 0;
                    yellow <= 0;
                    green <= 1;
                end
                default: begin
                    red <= 0;
                    yellow <= 0;
                    green <= 0;
                end
            endcase
        end
    end

    // Assign clock output
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            clock <= 8'd10; // Reset clock
        end else begin
            clock <= cnt; // Assign current counter value to clock
        end
    end

    // Adjust the counter initialization to ensure correct output
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cnt <= 8'd10; // Reset counter
        end else if (state == s1_red) begin
            cnt <= 8'd60; // Set counter for red light duration
        end
    end

endmodule
