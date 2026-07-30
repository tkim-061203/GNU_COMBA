#include <verilated.h>
#include <verilated_vcd_c.h>
#include <stdio.h>
#include <vector>
#include <deque>
#include <time.h>
#include <cmath>
#include <iostream>
#include <Vcounter_12__Syms.h>
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

class counter_12InTx
{
public:
    /* TODO BEGIN 1 */
    uint8_t rst_n,
        valid_count;
    /* TODO END 1 */
};

class counter_12OutTx
{
public:
    /* TODO BEGIN 2 */
    uint8_t out;
    /* TODO END 2 */
};

counter_12InTx in_tx_ref;
counter_12OutTx out_tx_ref;

class counter_12Scb
{
private:
    std::deque<counter_12InTx *> in_q;

public:
    // Input interface monitor port
    void writeIn(counter_12InTx *tx)
    {
        // Push the received transaction item into a queue for later
        in_q.push_back(tx);
    }

    // Output interface monitor port
    void writeOut(counter_12OutTx *tx)
    {
        // We should never get any data from the output interface
        // before an input gets driven to the input interface
        if (in_q.empty())
        {
            std::cout << "Fatal Error in counter_12Scb: empty counter_12InTx queue" << std::endl;
            exit(1);
        }

        // Grab the transaction item from the front of the input item queue
        counter_12InTx *in;
        in = in_q.front();
        in_q.pop_front();

        /* TODO BEGIN 3 */
        if (!in->rst_n)
        {
            if (!(tx->out == 0x0))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->rst_n = 0x%x, in->valid_count = 0x%x", in->rst_n, in->valid_count);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->out = 0x%x", tx->out);
                Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: out = 0x%x", 0);

                Debug_printf("\r\n");
                fflush(stdout);

                myexit(0, tx->out == 0x0, "TODO 3 Failed: Reset logic result of the Verilog module is incorrect")
            }
        }
        else
        {
            out_tx_ref.out += in->valid_count;
            out_tx_ref.out %= 12;

            if (!(tx->out == out_tx_ref.out))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->rst_n = 0x%x, in->valid_count = 0x%x", in->rst_n, in->valid_count);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->out = 0x%x", tx->out);
                Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: out_tx_ref.out = 0x%x", out_tx_ref.out);
                Debug_printf("\r\n");
                fflush(stdout);

                myexit(1, tx->out == out_tx_ref.out, "TODO 3 Failed: Count logic result of the Verilog module is incorrect")
            }
        }
        /* TODO END 3 */

        delete in;
        delete tx;
    }
};

class counter_12InDrv
{
private:
    Vcounter_12 *dut;

public:
    counter_12InDrv(Vcounter_12 *dut)
    {
        this->dut = dut;
    }

    void drive(counter_12InTx *tx)
    {
        /* TODO BEGIN 4 */
        if (tx != NULL)
        {
            dut->rst_n = tx->rst_n;
            dut->valid_count = tx->valid_count;
            delete tx;
        }
        /* TODO END 4 */

        dut->eval();
    }
};

class counter_12InMon
{
private:
    Vcounter_12 *dut;
    counter_12Scb *scb;

public:
    counter_12InMon(Vcounter_12 *dut, counter_12Scb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        counter_12InTx *tx = new counter_12InTx();

        /* TODO BEGIN 5 */
        tx->rst_n = dut->rst_n;
        tx->valid_count = dut->valid_count;
        /* TODO END 5 */

        scb->writeIn(tx);
    }
};

class counter_12OutMon
{
private:
    Vcounter_12 *dut;
    counter_12Scb *scb;

public:
    counter_12OutMon(Vcounter_12 *dut, counter_12Scb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        counter_12OutTx *tx = new counter_12OutTx();

        /* TODO BEGIN 6 */
        tx->out = dut->out;
        /* TODO END 6 */

        scb->writeOut(tx);
    }
};

counter_12InTx *rndAluInTx()
{
    counter_12InTx *tx = new counter_12InTx();
    /* TODO BEGIN 7 */
    if (IS_SIM_TIME_IN_RST(sim_time))
    {
        in_tx_ref.rst_n = 0;
        out_tx_ref.out = 0;
    }

    else if (sim_time >= VERIF_START_TIME)
    {
        in_tx_ref.rst_n = 1;
        in_tx_ref.valid_count = rand() % 2;
    }

    else
    {
        delete tx;
        return NULL;
    }
    tx->valid_count = in_tx_ref.valid_count;
    tx->rst_n = in_tx_ref.rst_n;
    /* TODO END 7 */
    return tx;
}

int main(int argc, char **argv)
{
    srand(time(NULL));
    Verilated::commandArgs(argc, argv);
    Vcounter_12 *dut = new Vcounter_12;

    Verilated::traceEverOn(true);
    VerilatedVcdC *m_trace = new VerilatedVcdC;
    dut->trace(m_trace, 5);
    m_trace->open("waveform.vcd");

    counter_12InTx *tx;

    // Here we create the driver, scoreboard, input and output monitor blocks
    counter_12InDrv *drv = new counter_12InDrv(dut);
    counter_12Scb *scb = new counter_12Scb();
    counter_12InMon *inMon = new counter_12InMon(dut, scb);
    counter_12OutMon *outMon = new counter_12OutMon(dut, scb);

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
