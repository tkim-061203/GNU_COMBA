#include <verilated.h>
#include <verilated_vcd_c.h>
#include <stdio.h>
#include <vector>
#include <deque>
#include <time.h>
#include <cmath>
#include <iostream>
#include <Vmulti_pipe_8bit__Syms.h>
#include <assert.h>

using namespace std;

#define IS_SIM_TIME_IN_RST(sim_time) (sim_time >= 3 && sim_time < 6)
#define MAX_SIM_TIME 300
#define VERIF_START_TIME 7
#ifndef NO_FALTAL_TB
#define myexit(index, condition, content) \
    {                                     \
        assert(condition && content);     \
    }
#else
uint8_t NO_FALTAL_indexs[20] = {0};
#define myexit(index, condition, content)             \
    {                                                 \
        if (!(condition) && !NO_FALTAL_indexs[index]) \
        {                                             \
            printf("\r\n");                           \
            printf(content);                          \
            NO_FALTAL_indexs[index] = 1;              \
        }                                             \
        fflush(stdout);                               \
    }
#endif
int Debug_printf(const char *fmt, ...)
{
#ifndef NO_FALTAL_TB
    int done;
    va_list args;
    va_start(args, fmt);

    done = vprintf(fmt, args);

    va_end(args);
    return done;
#else
    return 0;
#endif
}

vluint64_t sim_time = 0;
vluint64_t tx_data_gen_time = 0;

class multi_pipe_8bitInTx
{
public:
    /* TODO BEGIN 1 */
    uint8_t clk, rst_n, mul_en_in;
    uint32_t mul_a,
        mul_b;
    /* TODO END 1 */
};

class multi_pipe_8bitOutTx
{
public:
    /* TODO BEGIN 2 */
    uint8_t mul_en_out;
    uint32_t mul_out;
    /* TODO END 2 */
};

multi_pipe_8bitInTx in_tx_ref;
multi_pipe_8bitOutTx out_tx_ref;

class multi_pipe_8bitScb
{
private:
    std::deque<multi_pipe_8bitInTx *> in_q;

public:
    // Input interface monitor port
    void writeIn(multi_pipe_8bitInTx *tx)
    {
        // Push the received transaction item into a queue for later
        in_q.push_back(tx);
    }

    // Output interface monitor port
    void writeOut(multi_pipe_8bitOutTx *tx)
    {
        // We should never get any data from the output interface
        // before an input gets driven to the input interface
        if (in_q.empty())
        {
            std::cout << "Fatal Error in multi_pipe_8bitScb: empty multi_pipe_8bitInTx queue" << std::endl;
            exit(1);
        }

        // Grab the transaction item from the front of the input item queue
        multi_pipe_8bitInTx *in;
        in = in_q.front();
        in_q.pop_front();

        /* TODO BEGIN 3 */
        if (!in->rst_n)
        {
            if (!(tx->mul_en_out == 0 && tx->mul_out == 0))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->mul_a = %x, in->mul_b = %x, in->mul_en_in = %x, in->rst_n = %x", in->mul_a, in->mul_b, in->mul_en_in, in->rst_n);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->mul_en_out = %x, tx->mul_out = %x", tx->mul_en_out, tx->mul_out);
                Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: mul_en_out = %x, mul_out = %x", 0, 0);

                Debug_printf("\r\n");
                fflush(stdout);

                myexit(0, tx->mul_en_out == 0 && tx->mul_out == 0, "TODO 3 Failed: Reset logic result of the Verilog module is incorrect")
            }
        }
        else if (tx->mul_en_out)
        {
            if (!(tx->mul_out == (in->mul_a * in->mul_b)))
            {
                uint32_t mul_out = in->mul_a * in->mul_b;
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->mul_a = %x, in->mul_b = %x, in->mul_en_in = %x, in->rst_n = %x", in->mul_a, in->mul_b, in->mul_en_in, in->rst_n);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->mul_en_out = %x, tx->mul_out = %x", tx->mul_en_out, tx->mul_out);
                Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: tx->mul_en_out = %x, mul_out = %x", tx->mul_en_out, mul_out);

                Debug_printf("\r\n");
                fflush(stdout);

                myexit(1, tx->mul_out == (in->mul_a * in->mul_b), "TODO 3 Failed: Multiplication logic result of the Verilog module is incorrect when the (mul_en_out) is on")
            }
        }

        /* TODO END 3 */

        delete in;
        delete tx;
    }
};

class multi_pipe_8bitInDrv
{
private:
    Vmulti_pipe_8bit *dut;

public:
    multi_pipe_8bitInDrv(Vmulti_pipe_8bit *dut)
    {
        this->dut = dut;
    }

    void drive(multi_pipe_8bitInTx *tx)
    {
        /* TODO BEGIN 4 */
        if (tx != NULL)
        {
            dut->rst_n = tx->rst_n;
            dut->mul_a = tx->mul_a;
            dut->mul_b = tx->mul_b;
            dut->mul_en_in = tx->mul_en_in;
            delete tx;
        }
        /* TODO END 4 */

        dut->eval();
    }
};

class multi_pipe_8bitInMon
{
private:
    Vmulti_pipe_8bit *dut;
    multi_pipe_8bitScb *scb;

public:
    multi_pipe_8bitInMon(Vmulti_pipe_8bit *dut, multi_pipe_8bitScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        multi_pipe_8bitInTx *tx = new multi_pipe_8bitInTx();

        /* TODO BEGIN 5 */
        tx->rst_n = dut->rst_n;
        tx->mul_a = dut->mul_a;
        tx->mul_b = dut->mul_b;
        tx->mul_en_in = dut->mul_en_in;
        /* TODO END 5 */

        scb->writeIn(tx);
    }
};

class multi_pipe_8bitOutMon
{
private:
    Vmulti_pipe_8bit *dut;
    multi_pipe_8bitScb *scb;

public:
    multi_pipe_8bitOutMon(Vmulti_pipe_8bit *dut, multi_pipe_8bitScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        multi_pipe_8bitOutTx *tx = new multi_pipe_8bitOutTx();

        /* TODO BEGIN 6 */
        tx->mul_en_out = dut->mul_en_out;
        tx->mul_out = dut->mul_out;
        /* TODO END 6 */

        scb->writeOut(tx);
    }
};

multi_pipe_8bitInTx *rndAluInTx()
{
    multi_pipe_8bitInTx *tx = new multi_pipe_8bitInTx();
    /* TODO BEGIN 7 */
    if (IS_SIM_TIME_IN_RST(sim_time))
        tx->rst_n = 0;

    else if (sim_time > VERIF_START_TIME)
    {
        tx->rst_n = !out_tx_ref.mul_en_out;
        in_tx_ref.mul_en_in = 1;

        if (out_tx_ref.mul_en_out)
        {
            in_tx_ref.mul_a = rand() % 0xff;
            in_tx_ref.mul_b = rand() % 0xff;
        }

        tx->mul_a = in_tx_ref.mul_a;
        tx->mul_b = in_tx_ref.mul_b;
        tx->mul_en_in = in_tx_ref.mul_en_in;
    }
    else
    {
        delete tx;
        return NULL;
    }
    /* TODO END 7 */

    return tx;
}

int main(int argc, char **argv)
{
    srand(time(NULL));
    Verilated::commandArgs(argc, argv);
    Vmulti_pipe_8bit *dut = new Vmulti_pipe_8bit;

    Verilated::traceEverOn(true);
    VerilatedVcdC *m_trace = new VerilatedVcdC;
    dut->trace(m_trace, 5);
    m_trace->open("waveform.vcd");

    multi_pipe_8bitInTx *tx;

    // Here we create the driver, scoreboard, input and output monitor blocks
    multi_pipe_8bitInDrv *drv = new multi_pipe_8bitInDrv(dut);
    multi_pipe_8bitScb *scb = new multi_pipe_8bitScb();
    multi_pipe_8bitInMon *inMon = new multi_pipe_8bitInMon(dut, scb);
    multi_pipe_8bitOutMon *outMon = new multi_pipe_8bitOutMon(dut, scb);

    /* TODO BEGIN 8 */
    while (sim_time < MAX_SIM_TIME)
    {
        dut->clk ^= 1;

        // Do all the driving/monitoring on a positive edge
        if ((dut->clk == 1 || IS_SIM_TIME_IN_RST(sim_time)) && sim_time)
        {

            tx = rndAluInTx();
            // Generate a randomised transaction item of type AluInTx

            // Pass the transaction item to the ALU input interface driver,
            // which drives the input interface based on the info in the
            // transaction item
            drv->drive(tx);

            // Monitor the input interface
            inMon->monitor();

            // Monitor the output interface
            outMon->monitor();
        }
        else
            dut->eval();
        out_tx_ref.mul_en_out = dut->mul_en_out;
        // end of positive edge processing

        m_trace->dump(sim_time);
        sim_time++;
    }
    /* TODO END 8 */
    m_trace->close();
    delete dut;
    delete outMon;
    delete inMon;
    delete scb;
    delete drv;
    exit(EXIT_SUCCESS);
    return 0;
}
