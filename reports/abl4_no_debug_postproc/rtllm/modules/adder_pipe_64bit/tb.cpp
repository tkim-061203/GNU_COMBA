#include <verilated.h>
#include <verilated_vcd_c.h>
#include <stdio.h>
#include <vector>
#include <deque>
#include <time.h>
#include <cmath>
#include <iostream>
#include <Vadder_pipe_64bit__Syms.h>
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

class adder_pipe_64bitInTx
{
public:
    /* TODO BEGIN 1 */
    uint8_t clk,
        rst_n,
        i_en;
    __uint128_t adda, addb;
    /* TODO END 1 */
};
adder_pipe_64bitInTx in_tx_ref;

class adder_pipe_64bitOutTx
{
public:
    /* TODO BEGIN 2 */
    uint8_t o_en;
    __uint128_t result;
    /* TODO END 2 */
};
adder_pipe_64bitOutTx out_tx_ref;

class adder_pipe_64bitScb
{
private:
    std::deque<adder_pipe_64bitInTx *> in_q;

public:
    // Input interface monitor port
    void writeIn(adder_pipe_64bitInTx *tx)
    {
        // Push the received transaction item into a queue for later
        in_q.push_back(tx);
    }

    // Output interface monitor port
    void writeOut(adder_pipe_64bitOutTx *tx)
    {
        // We should never get any data from the output interface
        // before an input gets driven to the input interface
        if (in_q.empty())
        {
            std::cout << "Fatal Error in adder_pipe_64bitScb: empty adder_pipe_64bitInTx queue" << std::endl;
            exit(1);
        }

        // Grab the transaction item from the front of the input item queue
        adder_pipe_64bitInTx *in;
        in = in_q.front();
        in_q.pop_front();

        /* TODO BEGIN 3 */
        if (!in->rst_n)
        {
            if (!(tx->result == 0 && tx->o_en == 0))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->adda = 0x%08lx %08lx, in->addb = 0x%08lx %08lx, in->i_en = 0x%x", uint64_t(in->adda >> 32), (uint64_t)in->adda, uint64_t(in->addb >> 32), (uint64_t)in->addb, (uint32_t)in->i_en);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->result = 0x%01x %08lx %08lx, tx->o_en = 0x%x", uint32_t(tx->result >> 64), uint64_t(tx->result >> 32), (uint64_t)tx->result, (uint32_t)tx->o_en);

                Debug_printf("\r\n");
                fflush(stdout);

                myexit(0, tx->result == 0 && tx->o_en == 0, "TODO 3 Failed: Reset logic result of the Verilog module is incorrect when (o_en) is asserted")
            }
        }
        else if (tx->o_en)
            if (!(tx->result == (in->adda + in->addb)))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->adda = 0x%08lx %08lx, in->addb = 0x%08lx %08lx, in->i_en = 0x%x", uint64_t(in->adda >> 32), (uint64_t)in->adda, uint64_t(in->addb >> 32), (uint64_t)in->addb, (uint32_t)in->i_en);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->result = 0x%01x %08lx %08lx, tx->o_en = 0x%x", uint32_t(tx->result >> 64), uint64_t(tx->result >> 32), (uint64_t)tx->result, (uint32_t)tx->o_en);

                Debug_printf("\r\n");
                fflush(stdout);

                myexit(1, tx->result == (in->adda + in->addb), "TODO 3 Failed: Addition logic result of the Verilog module is incorrect when (o_en) is asserted")
            }
        /* TODO END 3 */

        delete in;
        delete tx;
    }
};

class adder_pipe_64bitInDrv
{
private:
    Vadder_pipe_64bit *dut;

public:
    adder_pipe_64bitInDrv(Vadder_pipe_64bit *dut)
    {
        this->dut = dut;
    }

    void drive(adder_pipe_64bitInTx *tx)
    {
        /* TODO BEGIN 4 */
        if (tx != NULL)
        {
            dut->adda = tx->adda;
            dut->addb = tx->addb;
            dut->i_en = tx->i_en;
            dut->rst_n = tx->rst_n;
            delete tx;
        }
        /* TODO END 4 */

        dut->eval();
    }
};

class adder_pipe_64bitInMon
{
private:
    Vadder_pipe_64bit *dut;
    adder_pipe_64bitScb *scb;

public:
    adder_pipe_64bitInMon(Vadder_pipe_64bit *dut, adder_pipe_64bitScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        adder_pipe_64bitInTx *tx = new adder_pipe_64bitInTx();

        /* TODO BEGIN 5 */
        tx->adda = dut->adda;
        tx->addb = dut->addb;
        tx->i_en = dut->i_en;
        tx->rst_n = dut->rst_n;
        /* TODO END 5 */

        scb->writeIn(tx);
    }
};

class adder_pipe_64bitOutMon
{
private:
    Vadder_pipe_64bit *dut;
    adder_pipe_64bitScb *scb;

public:
    adder_pipe_64bitOutMon(Vadder_pipe_64bit *dut, adder_pipe_64bitScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        adder_pipe_64bitOutTx *tx = new adder_pipe_64bitOutTx();

        /* TODO BEGIN 6 */
        tx->o_en = dut->o_en;
        tx->result = (((__uint128_t)dut->result.m_storage[2]) << 64) | (((__uint128_t)dut->result.m_storage[1]) << 32) | dut->result.m_storage[0];
        /* TODO END 6 */

        scb->writeOut(tx);
    }
};

adder_pipe_64bitInTx *rndAluInTx()
{
    adder_pipe_64bitInTx *tx = new adder_pipe_64bitInTx();
    /* TODO BEGIN 7 */
    if (IS_SIM_TIME_IN_RST(sim_time))
        tx->rst_n = 0;
    else if (sim_time > VERIF_START_TIME)
    {
        tx->rst_n = !out_tx_ref.o_en; // reset if last out_tx_ref.o_en is on
        in_tx_ref.i_en = 1;

        if (out_tx_ref.o_en) // random new input data
        {
            in_tx_ref.adda = (((uint64_t)rand()) << 32) | rand();
            in_tx_ref.addb = (((uint64_t)rand()) << 32) | rand();
        }

        tx->i_en = in_tx_ref.i_en;
        tx->adda = in_tx_ref.adda;
        tx->addb = in_tx_ref.addb;
    }
    else
    {
        delete tx;
        return NULL;
    }
    /* TODO END 7 */

    tx_data_gen_time += tx->rst_n;
    return tx;
}

int main(int argc, char **argv)
{
    srand(time(NULL));
    Verilated::commandArgs(argc, argv);
    Vadder_pipe_64bit *dut = new Vadder_pipe_64bit;

    Verilated::traceEverOn(true);
    VerilatedVcdC *m_trace = new VerilatedVcdC;
    dut->trace(m_trace, 5);
    m_trace->open("waveform.vcd");

    adder_pipe_64bitInTx *tx;

    // Here we create the driver, scoreboard, input and output monitor blocks
    adder_pipe_64bitInDrv *drv = new adder_pipe_64bitInDrv(dut);
    adder_pipe_64bitScb *scb = new adder_pipe_64bitScb();
    adder_pipe_64bitInMon *inMon = new adder_pipe_64bitInMon(dut, scb);
    adder_pipe_64bitOutMon *outMon = new adder_pipe_64bitOutMon(dut, scb);

    /* TODO BEGIN 8 */

    // initial data
    in_tx_ref.adda = (((uint64_t)rand()) << 32) | rand();
    in_tx_ref.addb = (((uint64_t)rand()) << 32) | rand();
    in_tx_ref.i_en = 1;
    out_tx_ref.o_en = 0;
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

        // update out_tx_ref o_eb
        out_tx_ref.o_en = dut->o_en;

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
