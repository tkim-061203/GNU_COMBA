#include <verilated.h>
#include <verilated_vcd_c.h>
#include <stdio.h>
#include <vector>
#include <deque>
#include <time.h>
#include <cmath>
#include <iostream>
#include <Vsignal_generator__Syms.h>
#include <assert.h>

using namespace std;

Vsignal_generator *dut = new Vsignal_generator;

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

latch_management latch_management_wave = {.selector = &latch_management_wave.after_latch_state};

class signal_generatorInTx
{
public:
    /* TODO BEGIN 1 */
    uint8_t clk,
        rst_n;
    /* TODO END 1 */
};

class signal_generatorOutTx
{
public:
    /* TODO BEGIN 2 */
    uint8_t wave;
    /* TODO END 2 */
};

class signal_generatorInternalTx
{
public:
    /* TODO BEGIN 2 */
    uint8_t state;
    /* TODO END 2 */
};

signal_generatorInternalTx internal_tx_ref;

class signal_generatorScb
{
private:
    std::deque<signal_generatorInTx *> in_q;

public:
    // Input interface monitor port
    void writeIn(signal_generatorInTx *tx)
    {
        // Push the received transaction item into a queue for later
        in_q.push_back(tx);
    }

    // Output interface monitor port
    void writeOut(signal_generatorOutTx *tx)
    {
        // We should never get any data from the output interface
        // before an input gets driven to the input interface
        if (in_q.empty())
        {
            std::cout << "Fatal Error in signal_generatorScb: empty signal_generatorInTx queue" << std::endl;
            exit(1);
        }

        // Grab the transaction item from the front of the input item queue
        signal_generatorInTx *in;
        in = in_q.front();
        in_q.pop_front();

        /* TODO BEGIN 3 */
        if (in->rst_n == 0)
        {
            LATCH_MANAGEMENT_SELECTOR_ASSIGN(latch_management_wave, 1);
            if (!(tx->wave == 0))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->rst_n = 0x%x", in->rst_n);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->wave = 0x%x", tx->wave);
                Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: wave = 0x%x", 0);

                Debug_printf("\r\n");
                fflush(stdout);

                myexit(0, tx->wave == 0, "TODO 3 Failed: Reset logic result of the Verilog module is incorrect")
            }
        }
        else
        {

            if (!(tx->wave == LATCH_MANAGEMENT_SELECTOR_VAL(latch_management_wave)))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->rst_n = 0x%x", in->rst_n);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->wave = 0x%x", tx->wave);
                Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: wave = 0x%lx, %d", LATCH_MANAGEMENT_SELECTOR_VAL(latch_management_wave), LATCH_MANAGEMENT_IS_SELECTOR_AFTER_LATCH(latch_management_wave));
                Debug_printf("\r\n");
                fflush(stdout);

                myexit(1, tx->wave == 0, "TODO 3 Failed: Wave logic result of the Verilog module is incorrect")
            }

            if (internal_tx_ref.state == 0)
            {
                LATCH_MANAGEMENT_SELECTOR_TO_LATCH_IF_THRESHOLD(latch_management_wave, 31, {

                                                                                           },
                                                                {
                                                                    internal_tx_ref.state = 1;
                                                                    LATCH_MANAGEMENT_SELECTOR_OPERATE_IF_IS_AFTER_LATCH(latch_management_wave, -, 1); }, {
                                                                    LATCH_MANAGEMENT_SELECTOR_OPERATE_IF_IS_AFTER_LATCH(latch_management_wave, +, 1); //
                                                                })
            }
            else
            {
                LATCH_MANAGEMENT_SELECTOR_TO_LATCH_IF_THRESHOLD(latch_management_wave, 0, {

                                                                                          },
                                                                {
                                                                    internal_tx_ref.state = 0; //
                                                                    LATCH_MANAGEMENT_SELECTOR_OPERATE_IF_IS_AFTER_LATCH(latch_management_wave, +, 1); }, {
                                                                    LATCH_MANAGEMENT_SELECTOR_OPERATE_IF_IS_AFTER_LATCH(latch_management_wave, -, 1); //
                                                                })
            }
        }

        /* TODO END 3 */

        delete in;
        delete tx;
    }
};

class signal_generatorInDrv
{
private:
    Vsignal_generator *dut;

public:
    signal_generatorInDrv(Vsignal_generator *dut)
    {
        this->dut = dut;
    }

    void drive(signal_generatorInTx *tx)
    {
        /* TODO BEGIN 4 */
        if (tx != NULL)
        {
            dut->rst_n = tx->rst_n;
            delete tx;
        }
        /* TODO END 4 */

        dut->eval();
    }
};

class signal_generatorInMon
{
private:
    Vsignal_generator *dut;
    signal_generatorScb *scb;

public:
    signal_generatorInMon(Vsignal_generator *dut, signal_generatorScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        signal_generatorInTx *tx = new signal_generatorInTx();

        /* TODO BEGIN 5 */
        tx->rst_n = dut->rst_n;
        /* TODO END 5 */

        scb->writeIn(tx);
    }
};

class signal_generatorOutMon
{
private:
    Vsignal_generator *dut;
    signal_generatorScb *scb;

public:
    signal_generatorOutMon(Vsignal_generator *dut, signal_generatorScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        signal_generatorOutTx *tx = new signal_generatorOutTx();

        /* TODO BEGIN 6 */
        tx->wave = dut->wave;
        /* TODO END 6 */

        scb->writeOut(tx);
    }
};

signal_generatorInTx *rndAluInTx()
{
    signal_generatorInTx *tx = new signal_generatorInTx();
    /* TODO BEGIN 7 */
    if (IS_SIM_TIME_IN_RST(sim_time))
    {
        tx->rst_n = 0;
        internal_tx_ref.state = 0;
    }

    else if (sim_time >= VERIF_START_TIME)
    {
        tx->rst_n = 1;
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

    signal_generatorInTx *tx;

    // Here we create the driver, scoreboard, input and output monitor blocks
    signal_generatorInDrv *drv = new signal_generatorInDrv(dut);
    signal_generatorScb *scb = new signal_generatorScb();
    signal_generatorInMon *inMon = new signal_generatorInMon(dut, scb);
    signal_generatorOutMon *outMon = new signal_generatorOutMon(dut, scb);

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
