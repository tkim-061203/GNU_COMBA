#include <verilated.h>
#include <verilated_vcd_c.h>
#include <stdio.h>
#include <vector>
#include <deque>
#include <time.h>
#include <cmath>
#include <iostream>
#include <Vdiv_16bit__Syms.h>
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

class div_16bitInTx
{
public:
    /* TODO BEGIN 1 */
    uint16_t A;
    uint8_t B;
    /* TODO END 1 */
};

class div_16bitOutTx
{
public:
    /* TODO BEGIN 2 */
    uint16_t result, odd;
    /* TODO END 2 */
};

class div_16bitScb
{
private:
    std::deque<div_16bitInTx *> in_q;

public:
    // Input interface monitor port
    void writeIn(div_16bitInTx *tx)
    {
        // Push the received transaction item into a queue for later
        in_q.push_back(tx);
    }

    // Output interface monitor port
    void writeOut(div_16bitOutTx *tx)
    {
        // We should never get any data from the output interface
        // before an input gets driven to the input interface
        if (in_q.empty())
        {
            std::cout << "Fatal Error in div_16bitScb: empty div_16bitInTx queue" << std::endl;
            exit(1);
        }

        // Grab the transaction item from the front of the input item queue
        div_16bitInTx *in;
        in = in_q.front();
        in_q.pop_front();

        /* TODO BEGIN 3 */

        // calculation
        if (in->B != 0)
        {
            uint16_t quotient, remainer;
            quotient = in->A / in->B;
            remainer = in->A - quotient * in->B;
            if (!((tx->result == quotient) && (tx->odd == remainer)))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->A = 0x%x, in->B = 0x%x", in->A, in->B);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->odd = 0x%x, tx->result = 0x%x", tx->odd, tx->result);
                Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: remainder = 0x%x, quotient = 0x%x", remainer, quotient);
                Debug_printf("\r\n");
                fflush(stdout);

                myexit(0, (tx->result == quotient) && (tx->odd == remainer), "TODO 3 Failed: Division logic result of the Verilog module is incorrect")
            }
        }
        else
        {
            if (!((tx->result == 0xffff) && (tx->odd == in->A)))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->A = 0x%x, in->B = 0x%x", in->A, in->B);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->odd = 0x%x, tx->result = 0x%x", tx->odd, tx->result);
                Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: odd = 0x%x, result = 0x%x", 0xffff, in->A);
                Debug_printf("\r\n");
                fflush(stdout);

                myexit(1, (tx->result == 0xffff) && (tx->odd == in->A), "TODO 3 Failed: Zero-Division logic result of the Verilog module is incorrect")
            }
        }

        // printf("\r\n# TODO 3 OUTPUT TRACE: 0x%x", (tx->odd == remainer) && (tx->result == quotient));
        /* TODO END 3 */

        delete in;
        delete tx;
    }
};

class div_16bitInDrv
{
private:
    Vdiv_16bit *dut;

public:
    div_16bitInDrv(Vdiv_16bit *dut)
    {
        this->dut = dut;
    }

    void drive(div_16bitInTx *tx)
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

class div_16bitInMon
{
private:
    Vdiv_16bit *dut;
    div_16bitScb *scb;

public:
    div_16bitInMon(Vdiv_16bit *dut, div_16bitScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        div_16bitInTx *tx = new div_16bitInTx();

        /* TODO BEGIN 5 */
        tx->A = dut->A;
        tx->B = dut->B;
        /* TODO END 5 */

        scb->writeIn(tx);
    }
};

class div_16bitOutMon
{
private:
    Vdiv_16bit *dut;
    div_16bitScb *scb;

public:
    div_16bitOutMon(Vdiv_16bit *dut, div_16bitScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        div_16bitOutTx *tx = new div_16bitOutTx();

        /* TODO BEGIN 6 */
        tx->odd = dut->odd;
        tx->result = dut->result;
        /* TODO END 6 */

        scb->writeOut(tx);
    }
};

div_16bitInTx *rndAluInTx()
{
    div_16bitInTx *tx = new div_16bitInTx();
    /* TODO BEGIN 7 */
    tx->A = rand();
    tx->B = rand();
    /* TODO END 7 */
    return tx;
}

int main(int argc, char **argv)
{
    srand(time(NULL));
    Verilated::commandArgs(argc, argv);
    Vdiv_16bit *dut = new Vdiv_16bit;

    Verilated::traceEverOn(true);
    VerilatedVcdC *m_trace = new VerilatedVcdC;
    dut->trace(m_trace, 5);
    m_trace->open("waveform.vcd");

    div_16bitInTx *tx;

    // Here we create the driver, scoreboard, input and output monitor blocks
    div_16bitInDrv *drv = new div_16bitInDrv(dut);
    div_16bitScb *scb = new div_16bitScb();
    div_16bitInMon *inMon = new div_16bitInMon(dut, scb);
    div_16bitOutMon *outMon = new div_16bitOutMon(dut, scb);

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
