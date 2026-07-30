#include <verilated.h>
#include <verilated_vcd_c.h>
#include <stdio.h>
#include <vector>
#include <deque>
#include <time.h>
#include <cmath>
#include <iostream>
#include <Vfreq_div__Syms.h>
#include <assert.h>

using namespace std;

Vfreq_div *dut = new Vfreq_div;

#define IS_SIM_TIME_IN_RST(sim_time) (sim_time >= 0 && sim_time < 6)
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

uint8_t tb_counters[2];

vluint64_t sim_time = 0;
vluint64_t tx_data_gen_time = 0;

class freq_divInTx
{
public:
    /* TODO BEGIN 1 */
    uint8_t CLK_in, RST;
    /* TODO END 1 */
};

class freq_divOutTx
{
public:
    /* TODO BEGIN 2 */
    uint8_t CLK_50, CLK_10, CLK_1;
    /* TODO END 2 */
};

freq_divOutTx out_tx_ref;

class freq_divScb
{
private:
    std::deque<freq_divInTx *> in_q;

public:
    // Input interface monitor port
    void writeIn(freq_divInTx *tx)
    {
        // Push the received transaction item into a queue for later
        in_q.push_back(tx);
    }

    // Output interface monitor port
    void writeOut(freq_divOutTx *tx)
    {
        // We should never get any data from the output interface
        // before an input gets driven to the input interface
        if (in_q.empty())
        {
            std::cout << "Fatal Error in freq_divScb: empty freq_divInTx queue" << std::endl;
            exit(1);
        }

        // Grab the transaction item from the front of the input item queue
        freq_divInTx *in;
        in = in_q.front();
        in_q.pop_front();

        /* TODO BEGIN 3 */
        if (in->RST == 1)
        {
            tb_counters[1] = tb_counters[0] = 1;
            if (!(tx->CLK_10 == 0 && tx->CLK_1 == 0 && tx->CLK_50 == 0))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->RST = 0x%x", in->RST);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->CLK_10 = 0x%x, tx->CLK_1 = 0x%x, tx->CLK_50 = 0x%x", tx->CLK_10, tx->CLK_1, tx->CLK_50);
                Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: CLK_10 = 0x%x, CLK_1 = 0x%x, CLK_50 = 0x%x", 0, 0, 0);
                Debug_printf("\r\n");
                fflush(stdout);

                myexit(0, tx->CLK_10 == 0 && tx->CLK_1 == 0 && tx->CLK_50 == 0, "TODO 3 Failed: Reset logic result of the Verilog module is incorrect")
            }
        }
        else
        {
            out_tx_ref.CLK_50 ^= 1;

            if (tb_counters[0] == 10)
            {
                out_tx_ref.CLK_10 ^= 1;
                tb_counters[0] = 0;
            }

            tb_counters[0]++;

            if (tb_counters[1] == 100)
            {
                out_tx_ref.CLK_1 ^= 1;
                tb_counters[1] = 0;
            }

            tb_counters[1]++;

            if (!(tx->CLK_10 == out_tx_ref.CLK_10 && tx->CLK_1 == out_tx_ref.CLK_1 && tx->CLK_50 == out_tx_ref.CLK_50))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld %d %d", sim_time, tb_counters[0], tb_counters[1]);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->RST = 0x%x", in->RST);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->CLK_10 = 0x%x, tx->CLK_1 = 0x%x, tx->CLK_50 = 0x%x", tx->CLK_10, tx->CLK_1, tx->CLK_50);
                Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: out_tx_ref.CLK_10 = 0x%x, out_tx_ref.CLK_1 = 0x%x, out_tx_ref.CLK_50 = 0x%x", out_tx_ref.CLK_10, out_tx_ref.CLK_1, out_tx_ref.CLK_50);
                Debug_printf("\r\n");
                fflush(stdout);

                myexit(1, tx->CLK_10 == out_tx_ref.CLK_10 && tx->CLK_1 == out_tx_ref.CLK_1 && tx->CLK_50 == out_tx_ref.CLK_50, "TODO 3 Failed: Clock logic result of the Verilog module is incorrect")
            }
        }

        /* TODO END 3 */

        delete in;
        delete tx;
    }
};

class freq_divInDrv
{
private:
    Vfreq_div *dut;

public:
    freq_divInDrv(Vfreq_div *dut)
    {
        this->dut = dut;
    }

    void drive(freq_divInTx *tx)
    {
        /* TODO BEGIN 4 */
        if (tx != NULL)
        {
            dut->RST = tx->RST;
            delete tx;
        }
        /* TODO END 4 */

        dut->eval();
    }
};

class freq_divInMon
{
private:
    Vfreq_div *dut;
    freq_divScb *scb;

public:
    freq_divInMon(Vfreq_div *dut, freq_divScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        freq_divInTx *tx = new freq_divInTx();

        /* TODO BEGIN 5 */
        tx->RST = dut->RST;
        /* TODO END 5 */

        scb->writeIn(tx);
    }
};

class freq_divOutMon
{
private:
    Vfreq_div *dut;
    freq_divScb *scb;

public:
    freq_divOutMon(Vfreq_div *dut, freq_divScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        freq_divOutTx *tx = new freq_divOutTx();

        /* TODO BEGIN 6 */
        tx->CLK_10 = dut->CLK_10;
        tx->CLK_1 = dut->CLK_1;
        tx->CLK_50 = dut->CLK_50;
        /* TODO END 6 */

        scb->writeOut(tx);
    }
};

freq_divInTx *rndAluInTx()
{
    freq_divInTx *tx = new freq_divInTx();
    /* TODO BEGIN 7 */
    if (IS_SIM_TIME_IN_RST(sim_time))
        tx->RST = 1;

    else if (sim_time >= VERIF_START_TIME)
    {
        tx->RST = 0;
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

    Verilated::traceEverOn(true);
    VerilatedVcdC *m_trace = new VerilatedVcdC;
    dut->trace(m_trace, 5);
    m_trace->open("waveform.vcd");

    freq_divInTx *tx;

    // Here we create the driver, scoreboard, input and output monitor blocks
    freq_divInDrv *drv = new freq_divInDrv(dut);
    freq_divScb *scb = new freq_divScb();
    freq_divInMon *inMon = new freq_divInMon(dut, scb);
    freq_divOutMon *outMon = new freq_divOutMon(dut, scb);

    /* TODO BEGIN 8 */
    while (sim_time < MAX_SIM_TIME)
    {
        dut->CLK_in ^= 1;

        // Do all the driving/monitoring on a positive edge
        if ((dut->CLK_in == 1 || IS_SIM_TIME_IN_RST(sim_time)) && sim_time)
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
