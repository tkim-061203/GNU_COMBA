#include <verilated.h>
#include <verilated_vcd_c.h>
#include <stdio.h>
#include <vector>
#include <deque>
#include <time.h>
#include <cmath>
#include <iostream>
#include <Vmulti_8bit__Syms.h>
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

class multi_8bitInTx
{
public:
    /* TODO BEGIN 1 */
    uint16_t A, B;
    /* TODO END 1 */
};

class multi_8bitOutTx
{
public:
    /* TODO BEGIN 2 */
    uint32_t product;
    /* TODO END 2 */
};

class multi_8bitScb
{
private:
    std::deque<multi_8bitInTx *> in_q;

public:
    // Input interface monitor port
    void writeIn(multi_8bitInTx *tx)
    {
        // Push the received transaction item into a queue for later
        in_q.push_back(tx);
    }

    // Output interface monitor port
    void writeOut(multi_8bitOutTx *tx)
    {
        // We should never get any data from the output interface
        // before an input gets driven to the input interface
        if (in_q.empty())
        {
            std::cout << "Fatal Error in multi_8bitScb: empty multi_8bitInTx queue" << std::endl;
            exit(1);
        }

        // Grab the transaction item from the front of the input item queue
        multi_8bitInTx *in;
        in = in_q.front();
        in_q.pop_front();

        /* TODO BEGIN 3 */
        if (!(tx->product == (in->A * in->B)))
        {
            Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
            Debug_printf("\r\n# TODO 3 INPUT TRACE: , in->A = %x, in->B = %x", in->A, in->B);
            Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->product = %x", tx->product);

            Debug_printf("\r\n");
            fflush(stdout);

            myexit(0, tx->product == (in->A * in->B), "TODO 3 Failed: Multiplication output logic result of the Verilog module is incorrect when valid_out is on")
        }
        /* TODO END 3 */

        delete in;
        delete tx;
    }
};

class multi_8bitInDrv
{
private:
    Vmulti_8bit *dut;

public:
    multi_8bitInDrv(Vmulti_8bit *dut)
    {
        this->dut = dut;
    }

    void drive(multi_8bitInTx *tx)
    {
        /* TODO BEGIN 4 */
        if (tx != NULL)
        {
            dut->A = tx->A;
            dut->B = tx->B;
            delete tx;
        }
        /* TODO END 4 */

        dut->eval();
    }
};

class multi_8bitInMon
{
private:
    Vmulti_8bit *dut;
    multi_8bitScb *scb;

public:
    multi_8bitInMon(Vmulti_8bit *dut, multi_8bitScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        multi_8bitInTx *tx = new multi_8bitInTx();

        /* TODO BEGIN 5 */
        tx->A = dut->A;
        tx->B = dut->B;
        /* TODO END 5 */

        scb->writeIn(tx);
    }
};

class multi_8bitOutMon
{
private:
    Vmulti_8bit *dut;
    multi_8bitScb *scb;

public:
    multi_8bitOutMon(Vmulti_8bit *dut, multi_8bitScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        multi_8bitOutTx *tx = new multi_8bitOutTx();

        /* TODO BEGIN 6 */
        tx->product = dut->product;
        /* TODO END 6 */

        scb->writeOut(tx);
    }
};

multi_8bitInTx *rndAluInTx()
{
    multi_8bitInTx *tx = new multi_8bitInTx();
    /* TODO BEGIN 7 */
    tx->A = rand() & 0xff;
    tx->B = rand() & 0xff;
    /* TODO END 7 */

    return tx;
}

int main(int argc, char **argv)
{
    srand(time(NULL));
    Verilated::commandArgs(argc, argv);
    Vmulti_8bit *dut = new Vmulti_8bit;

    Verilated::traceEverOn(true);
    VerilatedVcdC *m_trace = new VerilatedVcdC;
    dut->trace(m_trace, 5);
    m_trace->open("waveform.vcd");

    multi_8bitInTx *tx;

    // Here we create the driver, scoreboard, input and output monitor blocks
    multi_8bitInDrv *drv = new multi_8bitInDrv(dut);
    multi_8bitScb *scb = new multi_8bitScb();
    multi_8bitInMon *inMon = new multi_8bitInMon(dut, scb);
    multi_8bitOutMon *outMon = new multi_8bitOutMon(dut, scb);

    /* TODO BEGIN 8 */
    while (sim_time < MAX_SIM_TIME)
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
