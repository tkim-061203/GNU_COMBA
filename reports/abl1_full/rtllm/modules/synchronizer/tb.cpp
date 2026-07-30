#include <verilated.h>
#include <verilated_vcd_c.h>
#include <stdio.h>
#include <vector>
#include <deque>
#include <time.h>
#include <cmath>
#include <iostream>
#include <Vsynchronizer__Syms.h>
#include <assert.h>

using namespace std;

Vsynchronizer *dut = new Vsynchronizer;

#define IS_SIM_TIME_IN_RST(sim_time) (sim_time >= 3 && sim_time < 6)
#define MAX_SIM_TIME 300
#define VERIF_START_TIME 7
#define MAX_STAGE 100
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

class synchronizerInTx
{
public:
    /* TODO BEGIN 1 */
    uint8_t clk_a,
        clk_b,
        arstn,
        brstn,
        data_in,
        data_en;
    /* TODO END 1 */
};

class synchronizerOutTx
{
public:
    /* TODO BEGIN 2 */
    uint8_t dataout;
    /* TODO END 2 */
};

synchronizerInTx in_tx_ref;

class synchronizerScb
{
private:
    std::deque<synchronizerInTx *> in_q;

public:
    // Input interface monitor port
    void writeIn(synchronizerInTx *tx)
    {
        // Push the received transaction item into a queue for later
        in_q.push_back(tx);
    }

    // Output interface monitor port
    void writeOut(synchronizerOutTx *tx)
    {
        // We should never get any data from the output interface
        // before an input gets driven to the input interface
        if (in_q.empty())
        {
            std::cout << "Fatal Error in synchronizerScb: empty synchronizerInTx queue" << std::endl;
            exit(1);
        }

        // Grab the transaction item from the front of the input item queue
        synchronizerInTx *in;
        in = in_q.front();
        in_q.pop_front();

        /* TODO BEGIN 3 */
        // myexit(0, "Delete me first before filling this TODO")
        if (tx_data_gen_time == 1)
        {
            if (!(tx->dataout == 0x0))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->arstn = 0x%x, in->brstn = 0x%x, in->data_en = 0x%x, in->data_in = 0x%x", in->arstn, in->brstn, in->data_en, in->data_in);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->dataout = 0x%x", tx->dataout);
                Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: dataout = 0x%x", 0);

                Debug_printf("\r\n");
                fflush(stdout);

                myexit(0, tx->dataout == 0x0, "TODO 3 Failed: Reset logic result of the Verilog module is incorrect")
            }
        }
        else if (tx_data_gen_time == 10)
        {
            if (!(tx->dataout == in_tx_ref.data_in))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->arstn = 0x%x, in->brstn = 0x%x, in->data_en = 0x%x, in->data_in = 0x%x", in->arstn, in->brstn, in->data_en, in->data_in);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->dataout = 0x%x", tx->dataout);
                Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: dataout = 0x%x", in_tx_ref.data_in);

                Debug_printf("\r\n");
                fflush(stdout);

                myexit(1, tx->dataout == in_tx_ref.data_in, "TODO 3 Failed: Synchronization logic result of the Verilog module is incorrect")
            }
        }
        /* TODO END 3 */

        delete in;
        delete tx;
    }
};

class synchronizerInDrv
{
private:
    Vsynchronizer *dut;

public:
    synchronizerInDrv(Vsynchronizer *dut)
    {
        this->dut = dut;
    }

    void drive(synchronizerInTx *tx)
    {
        /* TODO BEGIN 4 */
        if (tx != NULL)
        {
            dut->arstn = tx->arstn;
            dut->brstn = tx->brstn;
            dut->data_en = tx->data_en;
            dut->data_in = tx->data_in;
            delete tx;
        }
        /* TODO END 4 */

        dut->eval();
    }
};

class synchronizerInMon
{
private:
    Vsynchronizer *dut;
    synchronizerScb *scb;

public:
    synchronizerInMon(Vsynchronizer *dut, synchronizerScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        synchronizerInTx *tx = new synchronizerInTx();

        /* TODO BEGIN 5 */
        tx->arstn = dut->arstn;
        tx->brstn = dut->brstn;
        tx->data_en = dut->data_en;
        tx->data_in = dut->data_in;
        /* TODO END 5 */

        scb->writeIn(tx);
    }
};

class synchronizerOutMon
{
private:
    Vsynchronizer *dut;
    synchronizerScb *scb;

public:
    synchronizerOutMon(Vsynchronizer *dut, synchronizerScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        synchronizerOutTx *tx = new synchronizerOutTx();

        /* TODO BEGIN 6 */
        tx->dataout = dut->dataout;
        /* TODO END 6 */

        scb->writeOut(tx);
    }
};

synchronizerInTx *rndAluInTx()
{
    synchronizerInTx *tx = new synchronizerInTx();
    uint8_t tx_data_gen_time_increase = dut->clk_a;
    /* TODO BEGIN 7 */
    if (IS_SIM_TIME_IN_RST(sim_time))
        in_tx_ref.arstn = in_tx_ref.brstn = 0;
    else if (sim_time >= VERIF_START_TIME)
    {
        switch (tx_data_gen_time)
        {
        case 0:
            in_tx_ref.arstn = in_tx_ref.brstn = 0;
            break;
        case 1:
            in_tx_ref.arstn = in_tx_ref.brstn = 1;
            in_tx_ref.data_en = 0x1;
            in_tx_ref.data_in = rand() & 0xf;
            break;
        case 9:
            tx_data_gen_time_increase = dut->clk_b;
            break;

        case 10:
            in_tx_ref.data_en = 0x0;
            tx_data_gen_time = 0;
            tx_data_gen_time_increase = 0;
            break;

        default:
            break;
        }

        tx_data_gen_time += tx_data_gen_time_increase;
        tx_data_gen_time %= MAX_STAGE;
    }
    else
    {
        delete tx;
        return NULL;
    }

    tx->arstn = in_tx_ref.arstn;
    tx->brstn = in_tx_ref.brstn;
    tx->data_en = in_tx_ref.data_en;
    tx->data_in = in_tx_ref.data_in;
    /* TODO END 7 */

    return tx;
}

int main(int argc, char **argv)
{
    srand(time(NULL));
    Verilated::commandArgs(argc, argv);

    Verilated::traceEverOn(true);
    VerilatedVcdC *m_trace = new VerilatedVcdC;
    dut->trace(m_trace, 5);
    m_trace->open("waveform.vcd");

    synchronizerInTx *tx;

    // Here we create the driver, scoreboard, input and output monitor blocks
    synchronizerInDrv *drv = new synchronizerInDrv(dut);
    synchronizerScb *scb = new synchronizerScb();
    synchronizerInMon *inMon = new synchronizerInMon(dut, scb);
    synchronizerOutMon *outMon = new synchronizerOutMon(dut, scb);

    /* TODO BEGIN 8 */
    while (sim_time < MAX_SIM_TIME)
    {
        dut->clk_a ^= 1;
        dut->clk_b ^= (sim_time && (!(sim_time % 2)));

        // Do all the driving/monitoring on a positive edge
        if ((dut->clk_a == 1 || IS_SIM_TIME_IN_RST(sim_time)) && sim_time)
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
