#include <verilated.h>
#include <verilated_vcd_c.h>
#include <stdio.h>
#include <vector>
#include <deque>
#include <time.h>
#include <cmath>
#include <iostream>
#include <Vadder_8bit__Syms.h>
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

class adder_8bitInTx
{
public:
    /* TODO BEGIN 1 */
    u_int32_t a, b;
    u_int8_t cin;
    /* TODO END 1 */
};

class adder_8bitOutTx
{
public:
    /* TODO BEGIN 2 */
    u_int32_t sum;
    u_int8_t cout;
    /* TODO END 2 */
};

class adder_8bitScb
{
private:
    std::deque<adder_8bitInTx *> in_q;

public:
    // Input interface monitor port
    void writeIn(adder_8bitInTx *tx)
    {
        // Push the received transaction item into a queue for later
        in_q.push_back(tx);
    }

    // Output interface monitor port
    void writeOut(adder_8bitOutTx *tx)
    {
        // We should never get any data from the output interface
        // before an input gets driven to the input interface
        if (in_q.empty())
        {
            std::cout << "Fatal Error in adder_8bitScb: empty adder_8bitInTx queue" << std::endl;
            exit(1);
        }

        // Grab the transaction item from the front of the input item queue
        adder_8bitInTx *in;
        in = in_q.front();
        in_q.pop_front();

        /* TODO BEGIN 3 */
        if (!((tx->sum | (tx->cout << 8)) == (in->a + in->b + in->cin)))
        {
            Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
            Debug_printf("\r\n# TODO 3 INPUT TRACE: in->a = 0x%x, in->b = 0x%x, in->cin = 0x%x", in->a, in->b, in->cin);
            Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->cout = 0x%x, tx->sum = 0x%x", tx->cout, tx->sum);

            Debug_printf("\r\n");
            fflush(stdout);

            myexit(0, (tx->sum | (tx->cout << 8)) == (in->a + in->b + in->cin), "TODO 3 Failed: Addition logic result is incorrect")
        }
        /* TODO END 3 */
        delete in;
        delete tx;
    }
};

class adder_8bitInDrv
{
private:
    Vadder_8bit *dut;

public:
    adder_8bitInDrv(Vadder_8bit *dut)
    {
        this->dut = dut;
    }

    void drive(adder_8bitInTx *tx)
    {
        /* TODO BEGIN 4 */
        dut->a = tx->a;
        dut->b = tx->b;
        dut->cin = tx->cin;
        /* TODO END 4 */

        delete tx;
        dut->eval();
    }
};

class adder_8bitInMon
{
private:
    Vadder_8bit *dut;
    adder_8bitScb *scb;

public:
    adder_8bitInMon(Vadder_8bit *dut, adder_8bitScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        adder_8bitInTx *tx = new adder_8bitInTx();

        /* TODO BEGIN 5 */
        tx->a = dut->a;
        tx->b = dut->b;
        tx->cin = dut->cin;
        /* TODO END 5 */

        scb->writeIn(tx);
    }
};

class adder_8bitOutMon
{
private:
    Vadder_8bit *dut;
    adder_8bitScb *scb;

public:
    adder_8bitOutMon(Vadder_8bit *dut, adder_8bitScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        adder_8bitOutTx *tx = new adder_8bitOutTx();

        /* TODO BEGIN 6 */
        tx->sum = dut->sum;
        tx->cout = dut->cout;
        /* TODO END 6 */
        scb->writeOut(tx);
    }
};

adder_8bitInTx *rndAluInTx()
{
    adder_8bitInTx *tx = new adder_8bitInTx();

    /* TODO BEGIN 7 */
    tx->a = rand() & 0xff;
    tx->b = rand() & 0xff;
    tx->cin = rand() & 0x1;

    tx_data_gen_time += 1;
    /* TODO END 7 */
    return tx;
}

int main(int argc, char **argv)
{
    srand(time(NULL));
    Verilated::commandArgs(argc, argv);
    Vadder_8bit *dut = new Vadder_8bit;

    Verilated::traceEverOn(true);
    VerilatedVcdC *m_trace = new VerilatedVcdC;
    dut->trace(m_trace, 5);
    m_trace->open("waveform.vcd");

    adder_8bitInTx *tx;

    // Here we create the driver, scoreboard, input and output monitor blocks
    adder_8bitInDrv *drv = new adder_8bitInDrv(dut);
    adder_8bitScb *scb = new adder_8bitScb();
    adder_8bitInMon *inMon = new adder_8bitInMon(dut, scb);
    adder_8bitOutMon *outMon = new adder_8bitOutMon(dut, scb);
    /* TODO BEGIN 8 */
    while (sim_time < MAX_SIM_TIME)
    {
        // Do all the driving/monitoring on a positive edge

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
