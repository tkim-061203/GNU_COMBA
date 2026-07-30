#include <verilated.h>
#include <verilated_vcd_c.h>
#include <stdio.h>
#include <vector>
#include <deque>
#include <time.h>
#include <cmath>
#include <iostream>
#include <Vmulti_16bit__Syms.h>
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

class multi_16bitInTx
{
public:
    /* TODO BEGIN 1 */
    uint8_t clk,
        rst_n,
        start;
    uint32_t ain,
        bin;
    /* TODO END 1 */
};

class multi_16bitOutTx
{
public:
    /* TODO BEGIN 2 */
    uint64_t yout;
    uint8_t done;
    /* TODO END 2 */
};

multi_16bitInTx in_tx_ref;
multi_16bitOutTx out_tx_ref;

class multi_16bitScb
{
private:
    std::deque<multi_16bitInTx *> in_q;

public:
    // Input interface monitor port
    void writeIn(multi_16bitInTx *tx)
    {
        // Push the received transaction item into a queue for later
        in_q.push_back(tx);
    }

    // Output interface monitor port
    void writeOut(multi_16bitOutTx *tx)
    {
        // We should never get any data from the output interface
        // before an input gets driven to the input interface
        if (in_q.empty())
        {
            std::cout << "Fatal Error in multi_16bitScb: empty multi_16bitInTx queue" << std::endl;
            exit(1);
        }

        // Grab the transaction item from the front of the input item queue
        multi_16bitInTx *in;
        in = in_q.front();
        in_q.pop_front();

        /* TODO BEGIN 3 */
        if (!in->rst_n)
        {
            if (!(tx->yout == 0 && tx->done == 0))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->ain = %x, in->bin = %x, in->rst_n = %x, in->start = %x", in->ain, in->bin, in->rst_n, in->start);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->done = %x, tx->yout = %lx", tx->done, tx->yout);
                Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: done = %x, yout = %x", 0, 0);

                Debug_printf("\r\n");
                fflush(stdout);

                myexit(0, tx->yout == 0 && tx->done == 0, "TODO 3 Failed: Reset logic result of the Verilog module")
            }
            else if (tx->done)
            {
                if (!(tx->yout == ((uint64_t)in->ain * in->bin)))
                {
                    uint64_t yout = (uint64_t)in->ain * in->bin;
                    Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                    Debug_printf("\r\n# TODO 3 INPUT TRACE: in->ain = %x, in->bin = %x, in->rst_n = %x, in->start = %x", in->ain, in->bin, in->rst_n, in->start);
                    Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->done = %x, tx->yout = %lx", tx->done, tx->yout);
                    Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: tx->done = %x, yout = %lx", tx->done, yout);

                    Debug_printf("\r\n");
                    fflush(stdout);

                    myexit(1, tx->yout == (in->ain * in->bin), "TODO 3 Failed: Multiplication logic result of the Verilog module")
                }
            }
        }
        /* TODO END 3 */

        delete in;
        delete tx;
    }
};

class multi_16bitInDrv
{
private:
    Vmulti_16bit *dut;

public:
    multi_16bitInDrv(Vmulti_16bit *dut)
    {
        this->dut = dut;
    }

    void drive(multi_16bitInTx *tx)
    {
        /* TODO BEGIN 4 */
        if (tx != NULL)
        {
            dut->ain = tx->ain;
            dut->bin = tx->bin;
            dut->rst_n = tx->rst_n;
            dut->start = tx->start;
            delete tx;
        }
        /* TODO END 4 */

        dut->eval();
    }
};

class multi_16bitInMon
{
private:
    Vmulti_16bit *dut;
    multi_16bitScb *scb;

public:
    multi_16bitInMon(Vmulti_16bit *dut, multi_16bitScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        multi_16bitInTx *tx = new multi_16bitInTx();

        /* TODO BEGIN 5 */
        tx->ain = dut->ain;
        tx->bin = dut->bin;
        tx->rst_n = dut->rst_n;
        tx->start = dut->start;
        /* TODO END 5 */

        scb->writeIn(tx);
    }
};

class multi_16bitOutMon
{
private:
    Vmulti_16bit *dut;
    multi_16bitScb *scb;

public:
    multi_16bitOutMon(Vmulti_16bit *dut, multi_16bitScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        multi_16bitOutTx *tx = new multi_16bitOutTx();

        /* TODO BEGIN 6 */
        tx->done = dut->done;
        tx->yout = dut->yout;
        /* TODO END 6 */

        scb->writeOut(tx);
    }
};

multi_16bitInTx *rndAluInTx()
{
    multi_16bitInTx *tx = new multi_16bitInTx();
    /* TODO BEGIN 7 */
    if (IS_SIM_TIME_IN_RST(sim_time))
        tx->rst_n = 0;
    else if (sim_time > VERIF_START_TIME)
    {
        tx->rst_n = !out_tx_ref.done;
        in_tx_ref.start = 1;

        if (out_tx_ref.done)
        {
            in_tx_ref.ain = rand() % 0xffff;
            in_tx_ref.bin = rand() % 0xffff;
        }

        tx->start = in_tx_ref.start;
        tx->ain = in_tx_ref.ain;
        tx->bin = in_tx_ref.bin;
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
    Vmulti_16bit *dut = new Vmulti_16bit;

    Verilated::traceEverOn(true);
    VerilatedVcdC *m_trace = new VerilatedVcdC;
    dut->trace(m_trace, 5);
    m_trace->open("waveform.vcd");

    multi_16bitInTx *tx;

    // Here we create the driver, scoreboard, input and output monitor blocks
    multi_16bitInDrv *drv = new multi_16bitInDrv(dut);
    multi_16bitScb *scb = new multi_16bitScb();
    multi_16bitInMon *inMon = new multi_16bitInMon(dut, scb);
    multi_16bitOutMon *outMon = new multi_16bitOutMon(dut, scb);

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
        out_tx_ref.done = dut->done;

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
