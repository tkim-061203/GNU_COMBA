#include <verilated.h>
#include <verilated_vcd_c.h>
#include <stdio.h>
#include <vector>
#include <deque>
#include <time.h>
#include <cmath>
#include <iostream>
#include <Vadder_32bit__Syms.h>
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

class adder_32bitInTx
{
public:
    /* TODO BEGIN 1 */
    u_int64_t A, B;
    /* TODO END 1 */
};

class adder_32bitOutTx
{
public:
    /* TODO BEGIN 2 */
    u_int64_t S;
    u_int8_t C32;
    /* TODO END 2 */
};

class adder_32bitScb
{
private:
    std::deque<adder_32bitInTx *> in_q;

public:
    // Input interface monitor port
    void writeIn(adder_32bitInTx *tx)
    {
        // Push the received transaction item into a queue for later
        in_q.push_back(tx);
    }

    // Output interface monitor port
    void writeOut(adder_32bitOutTx *tx)
    {
        // We should never get any data from the output interface
        // before an input gets driven to the input interface
        if (in_q.empty())
        {
            std::cout << "Fatal Error in adder_32bitScb: empty adder_32bitInTx queue" << std::endl;
            exit(1);
        }

        // Grab the transaction item from the front of the input item queue
        adder_32bitInTx *in;
        in = in_q.front();
        in_q.pop_front();

        /* TODO BEGIN 3 */
        if (!((tx->S | (tx->C32 << 32)) == (in->A + in->B)))
        {
            uint64_t sum_and_carry = in->A + in->B;
            uint32_t S = sum_and_carry;
            uint8_t C32 = sum_and_carry >> 32;

            Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
            Debug_printf("\r\n# TODO 3 INPUT TRACE: in->A = 0x%x, in->B = 0x%x", in->A, in->B);
            Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->C32 = 0x%x, tx->S = 0x%x", tx->C32, tx->S);
            Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: C32 = 0x%x, S = 0x%x", C32, S);

            Debug_printf("\r\n");
            fflush(stdout);

            myexit(0, (tx->S | (tx->C32 << 32)) == (in->A + in->B), "TODO 3 Failed: Addition logic result of the Verilog module is incorrect")
        }
        /* TODO END 3 */

        delete in;
        delete tx;
    }
};

class adder_32bitInDrv
{
private:
    Vadder_32bit *dut;

public:
    adder_32bitInDrv(Vadder_32bit *dut)
    {
        this->dut = dut;
    }

    void drive(adder_32bitInTx *tx)
    {
        /* TODO BEGIN 4 */
        dut->A = tx->A;
        dut->B = tx->B;
        /* TODO END 4 */

        delete tx;
        dut->eval();
    }
};

class adder_32bitInMon
{
private:
    Vadder_32bit *dut;
    adder_32bitScb *scb;

public:
    adder_32bitInMon(Vadder_32bit *dut, adder_32bitScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        adder_32bitInTx *tx = new adder_32bitInTx();

        /* TODO BEGIN 5 */
        tx->A = dut->A;
        tx->B = dut->B;
        /* TODO END 5 */

        scb->writeIn(tx);
    }
};

class adder_32bitOutMon
{
private:
    Vadder_32bit *dut;
    adder_32bitScb *scb;

public:
    adder_32bitOutMon(Vadder_32bit *dut, adder_32bitScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        adder_32bitOutTx *tx = new adder_32bitOutTx();

        /* TODO BEGIN 6 */
        tx->S = dut->S;
        tx->C32 = dut->C32;
        /* TODO END 6 */

        scb->writeOut(tx);
    }
};

adder_32bitInTx *rndAluInTx()
{
    adder_32bitInTx *tx = new adder_32bitInTx();
    /* TODO BEGIN 7 */
    tx->A = random();
    tx->B = random();
    /* TODO END 7 */

    tx_data_gen_time += 1;
    return tx;
}

int main(int argc, char **argv)
{
    srand(time(NULL));
    Verilated::commandArgs(argc, argv);
    Vadder_32bit *dut = new Vadder_32bit;

    Verilated::traceEverOn(true);
    VerilatedVcdC *m_trace = new VerilatedVcdC;
    dut->trace(m_trace, 5);
    m_trace->open("waveform.vcd");

    adder_32bitInTx *tx;

    // Here we create the driver, scoreboard, input and output monitor blocks
    adder_32bitInDrv *drv = new adder_32bitInDrv(dut);
    adder_32bitScb *scb = new adder_32bitScb();
    adder_32bitInMon *inMon = new adder_32bitInMon(dut, scb);
    adder_32bitOutMon *outMon = new adder_32bitOutMon(dut, scb);

    /* TODO BEGIN 8 */

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
