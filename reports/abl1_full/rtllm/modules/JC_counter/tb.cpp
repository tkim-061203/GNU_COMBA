#include <verilated.h>
#include <verilated_vcd_c.h>
#include <stdio.h>
#include <vector>
#include <deque>
#include <time.h>
#include <cmath>
#include <iostream>
#include <VJC_counter__Syms.h>
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
            /**/ printf("\r\n");                      \
            /**/ printf(content);                     \
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

class JC_counterInTx
{
public:
    /* TODO BEGIN 1 */
    uint8_t clk, rst_n;
    /* TODO END 1 */
};

class JC_counterOutTx
{
public:
    /* TODO BEGIN 2 */
    uint64_t Q;
    /* TODO END 2 */
};

JC_counterOutTx out_tx_ref;

class JC_counterScb
{
private:
    std::deque<JC_counterInTx *> in_q;

public:
    // Input interface monitor port
    void writeIn(JC_counterInTx *tx)
    {
        // Push the received transaction item into a queue for later
        in_q.push_back(tx);
    }

    // Output interface monitor port
    void writeOut(JC_counterOutTx *tx)
    {
        // We should never get any data from the output interface
        // before an input gets driven to the input interface
        if (in_q.empty())
        {
            std::cout << "Fatal Error in JC_counterScb: empty JC_counterInTx queue" << std::endl;
            exit(1);
        }

        // Grab the transaction item from the front of the input item queue
        JC_counterInTx *in;
        in = in_q.front();
        in_q.pop_front();

        /* TODO BEGIN 3 */
        if (!in->rst_n)
        {
            if (!(tx->Q == 0x0))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->rst_n = 0x%x", in->rst_n);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->Q = 0x%lx", tx->Q);
                Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: Q = 0x%x", 0);
                Debug_printf("\r\n");
                fflush(stdout);

                myexit(0, tx->Q == 0x0, "TODO 3 Failed: Reset logic result of the Verilog module is incorrect")
            }
        }
        else
        {
            uint64_t latchQ = out_tx_ref.Q; // latch old state

            out_tx_ref.Q >>= 1;

            if (!(latchQ & 0x1))
                out_tx_ref.Q |= ((uint64_t)1 << 63);

            if (!(tx->Q == out_tx_ref.Q))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->rst_n = 0x%x", in->rst_n);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->Q = 0x%lx", tx->Q);
                Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: out_tx_ref.Q = 0x%lx", out_tx_ref.Q);
                Debug_printf("\r\n");
                fflush(stdout);

                myexit(1, tx->Q == out_tx_ref.Q, "TODO 3 Failed: Counter Shifting logic result of the Verilog module is incorrect")
            }
        }

        /* TODO END 3 */

        delete in;
        delete tx;
    }
};

class JC_counterInDrv
{
private:
    VJC_counter *dut;

public:
    JC_counterInDrv(VJC_counter *dut)
    {
        this->dut = dut;
    }

    void drive(JC_counterInTx *tx)
    {
        /* TODO BEGIN 4 */
        // myexit(0, "Delete me first before filling this TODO")
        if (tx != NULL)
        {
            dut->rst_n = tx->rst_n;
            delete tx;
        }
        /* TODO END 4 */

        dut->eval();
    }
};

class JC_counterInMon
{
private:
    VJC_counter *dut;
    JC_counterScb *scb;

public:
    JC_counterInMon(VJC_counter *dut, JC_counterScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        JC_counterInTx *tx = new JC_counterInTx();

        /* TODO BEGIN 5 */
        tx->rst_n = dut->rst_n;
        /* TODO END 5 */

        scb->writeIn(tx);
    }
};

class JC_counterOutMon
{
private:
    VJC_counter *dut;
    JC_counterScb *scb;

public:
    JC_counterOutMon(VJC_counter *dut, JC_counterScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        JC_counterOutTx *tx = new JC_counterOutTx();

        /* TODO BEGIN 6 */
        tx->Q = dut->Q;
        /* TODO END 6 */

        scb->writeOut(tx);
    }
};

JC_counterInTx *rndAluInTx()
{
    JC_counterInTx *tx = new JC_counterInTx();
    /* TODO BEGIN 7 */
    if (IS_SIM_TIME_IN_RST(sim_time))
    {
        tx->rst_n = 0;
        out_tx_ref.Q = 0;
    }
    else
        tx->rst_n = 1;
    /* TODO END 7 */

    return tx;
}

int main(int argc, char **argv)
{
    srand(time(NULL));
    Verilated::commandArgs(argc, argv);
    VJC_counter *dut = new VJC_counter;

    Verilated::traceEverOn(true);
    VerilatedVcdC *m_trace = new VerilatedVcdC;
    dut->trace(m_trace, 5);
    m_trace->open("waveform.vcd");

    JC_counterInTx *tx;

    // Here we create the driver, scoreboard, input and output monitor blocks
    JC_counterInDrv *drv = new JC_counterInDrv(dut);
    JC_counterScb *scb = new JC_counterScb();
    JC_counterInMon *inMon = new JC_counterInMon(dut, scb);
    JC_counterOutMon *outMon = new JC_counterOutMon(dut, scb);

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
