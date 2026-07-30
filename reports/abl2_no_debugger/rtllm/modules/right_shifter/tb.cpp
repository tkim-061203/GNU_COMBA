#include <verilated.h>
#include <verilated_vcd_c.h>
#include <stdio.h>
#include <vector>
#include <deque>
#include <time.h>
#include <cmath>
#include <iostream>
#include <Vright_shifter__Syms.h>
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

class right_shifterInTx
{
public:
    /* TODO BEGIN 1 */
    uint8_t clk, d;
    /* TODO END 1 */
};

class right_shifterOutTx
{
public:
    /* TODO BEGIN 2 */
    uint8_t q;
    /* TODO END 2 */
};

right_shifterOutTx out_tx_ref;

class right_shifterScb
{
private:
    std::deque<right_shifterInTx *> in_q;

public:
    // Input interface monitor port
    void writeIn(right_shifterInTx *tx)
    {
        // Push the received transaction item into a queue for later
        in_q.push_back(tx);
    }

    // Output interface monitor port
    void writeOut(right_shifterOutTx *tx)
    {
        // We should never get any data from the output interface
        // before an input gets driven to the input interface
        if (in_q.empty())
        {
            std::cout << "Fatal Error in right_shifterScb: empty right_shifterInTx queue" << std::endl;
            exit(1);
        }

        // Grab the transaction item from the front of the input item queue
        right_shifterInTx *in;
        in = in_q.front();
        in_q.pop_front();

        /* TODO BEGIN 3 */
        out_tx_ref.q >>= 1;
        out_tx_ref.q |= (in->d << 7);

        if (!(tx->q == out_tx_ref.q))
        {
            Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
            Debug_printf("\r\n# TODO 3 INPUT TRACE: in->d = 0x%x", in->d);
            Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->q = 0x%x", tx->q);
            Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: out_tx_ref.q = 0x%x", out_tx_ref.q);

            Debug_printf("\r\n");
            fflush(stdout);

            myexit(0, tx->q == tx->q, "TODO 3 Failed: Shift logic result of the Verilog module is incorrect")
        }

        /* TODO END 3 */

        delete in;
        delete tx;
    }
};

class right_shifterInDrv
{
private:
    Vright_shifter *dut;

public:
    right_shifterInDrv(Vright_shifter *dut)
    {
        this->dut = dut;
    }

    void drive(right_shifterInTx *tx)
    {
        /* TODO BEGIN 4 */
        if (tx != NULL)
        {
            dut->d = tx->d;
            delete tx;
        }
        /* TODO END 4 */

        dut->eval();
    }
};

class right_shifterInMon
{
private:
    Vright_shifter *dut;
    right_shifterScb *scb;

public:
    right_shifterInMon(Vright_shifter *dut, right_shifterScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        right_shifterInTx *tx = new right_shifterInTx();

        /* TODO BEGIN 5 */
        tx->d = dut->d;
        /* TODO END 5 */

        scb->writeIn(tx);
    }
};

class right_shifterOutMon
{
private:
    Vright_shifter *dut;
    right_shifterScb *scb;

public:
    right_shifterOutMon(Vright_shifter *dut, right_shifterScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        right_shifterOutTx *tx = new right_shifterOutTx();

        /* TODO BEGIN 6 */
        tx->q = dut->q;
        /* TODO END 6 */

        scb->writeOut(tx);
    }
};

right_shifterInTx *rndAluInTx()
{
    right_shifterInTx *tx = new right_shifterInTx();
    /* TODO BEGIN 7 */
    if (sim_time >= VERIF_START_TIME)
    {
        tx->d = rand() % 2;
    }
    else if (sim_time < VERIF_START_TIME)
    {
        tx->d = 0;
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
    Vright_shifter *dut = new Vright_shifter;

    Verilated::traceEverOn(true);
    VerilatedVcdC *m_trace = new VerilatedVcdC;
    dut->trace(m_trace, 5);
    m_trace->open("waveform.vcd");

    right_shifterInTx *tx;

    // Here we create the driver, scoreboard, input and output monitor blocks
    right_shifterInDrv *drv = new right_shifterInDrv(dut);
    right_shifterScb *scb = new right_shifterScb();
    right_shifterInMon *inMon = new right_shifterInMon(dut, scb);
    right_shifterOutMon *outMon = new right_shifterOutMon(dut, scb);

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
