#include <verilated.h>
#include <verilated_vcd_c.h>
#include <stdio.h>
#include <vector>
#include <deque>
#include <time.h>
#include <cmath>
#include <iostream>
#include <Vaccu__Syms.h>
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

class accuInTx
{
public:
    /* TODO BEGIN 1 */
    uint8_t clk, rst_n, valid_in;
    uint16_t data_in;
    /* TODO END 1 */
};

class accuOutTx
{
public:
    /* TODO BEGIN 2 */
    uint8_t valid_out;
    uint16_t data_out;
    /* TODO END 2 */
};

uint16_t data_in_ref[4];
accuInTx in_tx_ref;
accuOutTx out_tx_ref;

class accuScb
{
private:
    std::deque<accuInTx *> in_q;

public:
    // Input interface monitor port
    void writeIn(accuInTx *tx)
    {
        // Push the received transaction item into a queue for later
        in_q.push_back(tx);
    }

    // Output interface monitor port
    void writeOut(accuOutTx *tx)
    {
        // We should never get any data from the output interface
        // before an input gets driven to the input interface
        if (in_q.empty())
        {
            std::cout << "Fatal Error in accuScb: empty accuInTx queue" << std::endl;
            exit(1);
        }

        // Grab the transaction item from the front of the input item queue
        accuInTx *in;
        in = in_q.front();
        in_q.pop_front();

        /* TODO BEGIN 3 */
        if (!in->rst_n)
        {
            if (!(tx->data_out == 0 && tx->valid_out == 0))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->rst_n = 0x%x, in->data_in = 0x%x, in->valid_in = 0x%x", in->rst_n, in->data_in, in->valid_in);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->data_out = 0x%x, tx->valid_out = 0x%x", tx->data_out, tx->valid_out);

                Debug_printf("\r\n");
                fflush(stdout);

                myexit(0, tx->data_out == 0 && tx->valid_out == 0, "TODO 3 Failed: Reset output logic result of the Verilog module is incorrect")
            }
        }
        else if (tx->valid_out)
        {
            if (!(tx->data_out == (data_in_ref[0] + data_in_ref[1] + data_in_ref[2] + data_in_ref[3])))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->rst_n = 0x%x, in->data_in = 0x%x, in->valid_in = 0x%x", in->rst_n, in->data_in, in->valid_in);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->data_out = 0x%x, tx->valid_out = 0x%x", tx->data_out, tx->valid_out);

                Debug_printf("\r\n");
                fflush(stdout);

                myexit(1, tx->data_out == (data_in_ref[0] + data_in_ref[1] + data_in_ref[2] + data_in_ref[3]), "TODO 3 Failed: Accumulation output logic result of the Verilog module is incorrect when valid_out is on")
            }
        }

        /* TODO END 3 */

        delete in;
        delete tx;
    }
};

class accuInDrv
{
private:
    Vaccu *dut;

public:
    accuInDrv(Vaccu *dut)
    {
        this->dut = dut;
    }

    void drive(accuInTx *tx)
    {
        /* TODO BEGIN 4 */
        if (tx != NULL)
        {
            dut->data_in = (uint8_t)tx->data_in;
            dut->rst_n = tx->rst_n;
            dut->valid_in = tx->valid_in;
            delete tx;
        }
        /* TODO END 4 */
        dut->eval();
    }
};

class accuInMon
{
private:
    Vaccu *dut;
    accuScb *scb;

public:
    accuInMon(Vaccu *dut, accuScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        accuInTx *tx = new accuInTx();

        /* TODO BEGIN 5 */
        tx->data_in = dut->data_in;
        tx->valid_in = dut->valid_in;
        tx->rst_n = dut->rst_n;
        /* TODO END 5 */

        scb->writeIn(tx);
    }
};

class accuOutMon
{
private:
    Vaccu *dut;
    accuScb *scb;

public:
    accuOutMon(Vaccu *dut, accuScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        accuOutTx *tx = new accuOutTx();

        /* TODO BEGIN 6 */
        tx->data_out = dut->data_out;
        tx->valid_out = dut->valid_out;
        /* TODO END 6 */

        scb->writeOut(tx);
    }
};

accuInTx *rndAluInTx()
{
    accuInTx *tx = new accuInTx();
    /* TODO BEGIN 7 */
    if (IS_SIM_TIME_IN_RST(sim_time))
        tx->rst_n = 0;
    else if (sim_time >= VERIF_START_TIME)
    {
        tx->rst_n = !out_tx_ref.valid_out;

        in_tx_ref.valid_in = 1;
        if (!out_tx_ref.valid_out) // load accumulator
            in_tx_ref.data_in = data_in_ref[tx_data_gen_time % 4];
        else // update data_in_ref
        {
            for (int i = 0; i < (sizeof(data_in_ref) / sizeof(data_in_ref[0])); i++)
                data_in_ref[i] = rand() & 0xff;
        }

        tx->data_in = in_tx_ref.data_in;
        tx->valid_in = in_tx_ref.valid_in;
    }
    else
    {
        delete tx;
        return NULL;
    }
    /* TODO END 7 */

    tx_data_gen_time += (sim_time >= VERIF_START_TIME);
    return tx;
}

int main(int argc, char **argv)
{
    srand(time(NULL));
    Verilated::commandArgs(argc, argv);
    Vaccu *dut = new Vaccu;

    Verilated::traceEverOn(true);
    VerilatedVcdC *m_trace = new VerilatedVcdC;
    dut->trace(m_trace, 5);
    m_trace->open("waveform.vcd");

    accuInTx *tx;

    // Here we create the driver, scoreboard, input and output monitor blocks
    accuInDrv *drv = new accuInDrv(dut);
    accuScb *scb = new accuScb();
    accuInMon *inMon = new accuInMon(dut, scb);
    accuOutMon *outMon = new accuOutMon(dut, scb);
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
        out_tx_ref.valid_out = dut->valid_out; // update out_tx_ref
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
