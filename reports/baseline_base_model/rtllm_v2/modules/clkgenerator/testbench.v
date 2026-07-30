module clkgenerator_tb;

    wire clk_tb; // Clock signal from the DUT (must be a wire, not reg)
    reg res = 1'b0;
    integer error = 0;
    integer k;
    // Instantiate the clkgenerator module
    clkgenerator clkgenerator_inst (
        .clk(clk_tb)
    );

    initial begin
        // Sample 2ns BEFORE each expected toggle (toggles at 5,10,15,...)
        // so the check never races with the DUT's edge.
        #3;
        for (k = 0; k < 20; k = k + 1) begin
            if (res !== clk_tb) begin
                error = error + 1;
                $display("Failed at t=%0t: clk=%b, expected=%b", $time, clk_tb, res);
            end
            res = res + 1;
            #5;
        end
        if (error == 0) begin
            $display("=========== Your Design Passed ===========");
        end
        else begin
            $display("=========== Test completed with %d failures ===========", error);
        end
        $finish;
    end

endmodule
