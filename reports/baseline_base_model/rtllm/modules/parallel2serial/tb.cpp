#include <verilated.h>
#include <verilated_vcd_c.h>
#include <stdio.h>
#include <vector>
#include <deque>
#include <time.h>
#include <cmath>
#include <iostream>
#include <Vparallel2serial__Syms.h>
#include <assert.h>

using namespace std;

Vparallel2serial *dut = new Vparallel2serial;

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

#define LATCH_MANAGEMENT_SELECTOR_VAL(lm) (*lm.selector)
#define LATCH_MANAGEMENT_AFTER_LATCH_VAL(lm) (lm.after_latch_state)
#define LATCH_MANAGEMENT_SELECTOR_ASSIGN(lm, x) (*lm.selector = x)
#define LATCH_MANAGEMENT_SELECTOR_INCREASE(lm, x) (*lm.selector += x)
#define LATCH_MANAGEMENT_SELECTOR_OPERATE_IF_IS_AFTER_LATCH(lm, o, x) \
    if (LATCH_MANAGEMENT_IS_SELECTOR_AFTER_LATCH(lm))                 \
    *lm.selector o## = x
#define LATCH_MANAGEMENT_IS_SELECTOR_AFTER_LATCH(lm) (lm.selector == &lm.after_latch_state)
#define LATCH_MANAGEMENT_SELECTOR_TO_LATCH_IF_THRESHOLD(lm, threshold, statement1, statement2, statement3) \
    if (LATCH_MANAGEMENT_SELECTOR_VAL(lm) == threshold)                                                    \
    {                                                                                                      \
        if (LATCH_MANAGEMENT_IS_SELECTOR_AFTER_LATCH(lm))                                                  \
        {                                                                                                  \
            LATCH_MANAGEMENT_SELECTOR_TO_LATCH(lm);                                                        \
            LATCH_MANAGEMENT_LATCH_ASSIGN(lm, lm.after_latch_state);                                       \
            statement1                                                                                     \
        }                                                                                                  \
        else                                                                                               \
        {                                                                                                  \
            LATCH_MANAGEMENT_SELECTOR_TO_AFTER_LATCH(lm);                                                  \
            statement2                                                                                     \
        }                                                                                                  \
    }                                                                                                      \
    else                                                                                                   \
    {                                                                                                      \
        statement3                                                                                         \
    }
#define LATCH_MANAGEMENT_SELECTOR_TO_LATCH(lm) (lm.selector = &lm.latch_state)
#define LATCH_MANAGEMENT_SELECTOR_TO_AFTER_LATCH(lm) (lm.selector = &lm.after_latch_state)
#define LATCH_MANAGEMENT_LATCH_ASSIGN(lm, x) (lm.latch_state = lm.after_latch_state)
typedef struct
{
    uint64_t latch_state;
    uint64_t after_latch_state;
    uint64_t *selector;
} latch_management;

class parallel2serialInTx
{
public:
    /* TODO BEGIN 1 */
    uint8_t rst_n, d;
    /* TODO END 1 */
};

class parallel2serialOutTx
{
public:
    /* TODO BEGIN 2 */
    uint8_t valid_out, dout;
    /* TODO END 2 */
};

parallel2serialInTx in_tx_ref;
parallel2serialOutTx out_tx_ref;

class parallel2serialScb
{
private:
    std::deque<parallel2serialInTx *> in_q;

public:
    // Input interface monitor port
    void writeIn(parallel2serialInTx *tx)
    {
        // Push the received transaction item into a queue for later
        in_q.push_back(tx);
    }

    // Output interface monitor port
    void writeOut(parallel2serialOutTx *tx)
    {
        // We should never get any data from the output interface
        // before an input gets driven to the input interface
        if (in_q.empty())
        {
            std::cout << "Fatal Error in parallel2serialScb: empty parallel2serialInTx queue" << std::endl;
            exit(1);
        }

        // Grab the transaction item from the front of the input item queue
        parallel2serialInTx *in;
        in = in_q.front();
        in_q.pop_front();

        /* TODO BEGIN 3 */
        if (!in->rst_n)
        {
            if (!(tx->dout == 0 && tx->valid_out == 0))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->rst_n = 0x%x", in->rst_n);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->dout = 0x%x, tx->valid_out = 0x%x", tx->dout, tx->valid_out);
                Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: dout = 0x%x, valid_out = 0x%x", 0, 0);

                Debug_printf("\r\n");
                fflush(stdout);

                myexit(0, tx->dout == 0 && tx->valid_out == 0, "TODO 3 Failed: Reset logic result of the Verilog module is incorrect")
            }
        }
        else if (tx_data_gen_time >= 4) // valid out is on
        {
            uint8_t offset = tx_data_gen_time - 4;
            uint8_t d_shift = in_tx_ref.d;
            d_shift <<= offset;
            d_shift &= 0xf;
            d_shift >>= 3;

            out_tx_ref.dout = d_shift;

            if (tx_data_gen_time == 4)
                if (!(tx->valid_out == 1))
                {
                    Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                    Debug_printf("\r\n# TODO 3 INPUT TRACE: in->rst_n = 0x%x", in->rst_n);
                    Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->dout = 0x%x, tx->valid_out = 0x%x", tx->dout, tx->valid_out);
                    Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: valid_out = 0x%x", 1);

                    Debug_printf("\r\n");
                    fflush(stdout);

                    myexit(1, tx->valid_out == 1, "TODO 3 Failed: Valid-out logic result of the Verilog module is incorrect")
                }
            if (!(tx->dout == out_tx_ref.dout))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->rst_n = 0x%x", in->rst_n);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->dout = 0x%x, tx->valid_out = 0x%x", tx->dout, tx->valid_out);
                Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: out_tx_ref.dout = 0x%x, tx->valid_out = 0x%x", out_tx_ref.dout, tx->valid_out);

                Debug_printf("\r\n");
                fflush(stdout);

                myexit(2, tx->dout == out_tx_ref.dout, "TODO 3 Failed: Parallel logic result of the Verilog module is incorrect")
            }
        }

        /* TODO END 3 */

        delete in;
        delete tx;
    }
};

class parallel2serialInDrv
{
private:
    Vparallel2serial *dut;

public:
    parallel2serialInDrv(Vparallel2serial *dut)
    {
        this->dut = dut;
    }

    void drive(parallel2serialInTx *tx)
    {
        /* TODO BEGIN 4 */
        if (tx != NULL)
        {
            dut->d = tx->d;
            dut->rst_n = tx->rst_n;
            delete tx;
        }
        /* TODO END 4 */

        dut->eval();
    }
};

class parallel2serialInMon
{
private:
    Vparallel2serial *dut;
    parallel2serialScb *scb;

public:
    parallel2serialInMon(Vparallel2serial *dut, parallel2serialScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        parallel2serialInTx *tx = new parallel2serialInTx();

        /* TODO BEGIN 5 */
        tx->d = dut->d;
        tx->rst_n = dut->rst_n;
        /* TODO END 5 */

        scb->writeIn(tx);
    }
};

class parallel2serialOutMon
{
private:
    Vparallel2serial *dut;
    parallel2serialScb *scb;

public:
    parallel2serialOutMon(Vparallel2serial *dut, parallel2serialScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        parallel2serialOutTx *tx = new parallel2serialOutTx();

        /* TODO BEGIN 6 */
        tx->dout = dut->dout;
        tx->valid_out = dut->valid_out;
        /* TODO END 6 */

        scb->writeOut(tx);
    }
};

parallel2serialInTx *rndAluInTx()
{
    parallel2serialInTx *tx = new parallel2serialInTx();
    uint8_t tx_data_gen_time_increase = dut->clk;
    /* TODO BEGIN 7 */
    if (IS_SIM_TIME_IN_RST(sim_time))
        tx->rst_n = 0;

    else if (sim_time >= VERIF_START_TIME)
    {
        in_tx_ref.rst_n = 1;
        switch (tx_data_gen_time)
        {
        case 0:
            in_tx_ref.d = rand() & 0xf;
            break;
        case 7:
            in_tx_ref.rst_n = 0;
            tx_data_gen_time = tx_data_gen_time_increase = 0;

            break;
        default:
            break;
        }

        tx->d = in_tx_ref.d;
        tx->rst_n = in_tx_ref.rst_n;

        tx_data_gen_time += tx_data_gen_time_increase;
        tx_data_gen_time %= MAX_STAGE;
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

    parallel2serialInTx *tx;

    // Here we create the driver, scoreboard, input and output monitor blocks
    parallel2serialInDrv *drv = new parallel2serialInDrv(dut);
    parallel2serialScb *scb = new parallel2serialScb();
    parallel2serialInMon *inMon = new parallel2serialInMon(dut, scb);
    parallel2serialOutMon *outMon = new parallel2serialOutMon(dut, scb);

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
