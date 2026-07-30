#include <verilated.h>
#include <verilated_vcd_c.h>
#include <stdio.h>
#include <vector>
#include <deque>
#include <time.h>
#include <cmath>
#include <iostream>
#include <Vwidth_8to16__Syms.h>
#include <assert.h>

using namespace std;

Vwidth_8to16 *dut = new Vwidth_8to16;

#define IS_SIM_TIME_IN_RST(sim_time) (sim_time >= 3 && sim_time < 6)
#define MAX_SIM_TIME 300
#define VERIF_START_TIME 8
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

#define COMBINATIONAL_LOGIC_EVAL_EN 0
vluint8_t combinational_logic_update = COMBINATIONAL_LOGIC_EVAL_EN;
#define IS_SEQUENTIAL_LOGIC_EVAL(clk, combinational) (clk && (!combinational))
#define IS_SEQUENTIAL_LOGIC_UPDATE(combinational) (!combinational)
#define IS_COMBINATIONAL_LOGIC_EVAL(combinational) (combinational)
#define IS_COMBINATIONAL_LOGIC_CONDITION_EVAL(combinational, cond) (combinational && (cond))

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

class width_8to16InTx
{
public:
    /* TODO BEGIN 1 */
    uint8_t rst_n,
        valid_in,
        data_in;
    /* TODO END 1 */
};

class width_8to16OutTx
{
public:
    /* TODO BEGIN 2 */
    uint8_t valid_out;
    uint16_t data_out;
    /* TODO END 2 */
};

class width_8to16InternalTx
{
public:
    /* TODO BEGIN 2 */
    uint8_t flag;
    /* TODO END 2 */
};

width_8to16InTx in_tx_ref;
width_8to16OutTx out_tx_ref;
width_8to16InternalTx internal_tx_ref;

class width_8to16Scb
{
private:
    std::deque<width_8to16InTx *> in_q;

public:
    // Input interface monitor port
    void writeIn(width_8to16InTx *tx)
    {
        // Push the received transaction item into a queue for later
        in_q.push_back(tx);
    }

    // Output interface monitor port
    void writeOut(width_8to16OutTx *tx)
    {
        // We should never get any data from the output interface
        // before an input gets driven to the input interface
        if (in_q.empty())
        {
            std::cout << "Fatal Error in width_8to16Scb: empty width_8to16InTx queue" << std::endl;
            exit(1);
        }

        // Grab the transaction item from the front of the input item queue
        width_8to16InTx *in;
        in = in_q.front();
        in_q.pop_front();

        /* TODO BEGIN 3 */
        if (!in->rst_n)
        {

            out_tx_ref.data_out = out_tx_ref.valid_out = 0;
            if (!(tx->data_out == 0x0 && tx->valid_out == 0x0))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->data_in = 0x%x, in->rst_n = 0x%x, in->valid_in = 0x%x", in->data_in, in->rst_n, in->valid_in);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->data_out = 0x%x, tx->valid_out = 0x%x", tx->data_out, tx->valid_out);
                Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: data_out = 0x%x, valid_out = 0x%x", 0, 0);
                Debug_printf("\r\n");
                fflush(stdout);

                myexit(0, tx->data_out == 0x0 && tx->valid_out == 0x0, "TODO 3 Failed: Reset logic result of the Verilog module is incorrect")
            }
        }
        else if (in->valid_in && IS_SEQUENTIAL_LOGIC_EVAL(dut->clk, combinational_logic_update))
        {
            out_tx_ref.data_out <<= 8;
            out_tx_ref.data_out |= in_tx_ref.data_in;
            out_tx_ref.valid_out = internal_tx_ref.flag;
            internal_tx_ref.flag ^= 1;

            if (out_tx_ref.valid_out)
                if (!(tx->data_out == out_tx_ref.data_out && tx->valid_out == out_tx_ref.valid_out))
                {
                    Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                    Debug_printf("\r\n# TODO 3 INPUT TRACE: in->data_in = 0x%x, in->rst_n = 0x%x, in->valid_in = 0x%x", in->data_in, in->rst_n, in->valid_in);
                    Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->data_out = 0x%x, tx->valid_out = 0x%x", tx->data_out, tx->valid_out);
                    Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: out_tx_ref.data_out = 0x%x, out_tx_ref.valid_out = 0x%x", out_tx_ref.data_out, out_tx_ref.valid_out);
                    Debug_printf("\r\n");
                    fflush(stdout);

                    myexit(1, tx->data_out == 0x0 && tx->valid_out == 0x0, "TODO 3 Failed: Reset logic result of the Verilog module is incorrect")
                }
        }
        /* TODO END 3 */

        delete in;
        delete tx;
    }
};

class width_8to16InDrv
{
private:
    Vwidth_8to16 *dut;

public:
    width_8to16InDrv(Vwidth_8to16 *dut)
    {
        this->dut = dut;
    }

    void drive(width_8to16InTx *tx)
    {
        /* TODO BEGIN 4 */
        if (tx != NULL)
        {
            dut->data_in = tx->data_in;
            dut->valid_in = tx->valid_in;
            if (COMBINATIONAL_LOGIC_EVAL_EN)
                dut->eval(); // combinational update
            dut->rst_n = tx->rst_n;
            delete tx;
        }
        /* TODO END 4 */

        dut->clk ^= IS_SEQUENTIAL_LOGIC_UPDATE(combinational_logic_update);
        dut->eval(); // sequential update
    }
};

class width_8to16InMon
{
private:
    Vwidth_8to16 *dut;
    width_8to16Scb *scb;

public:
    width_8to16InMon(Vwidth_8to16 *dut, width_8to16Scb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        width_8to16InTx *tx = new width_8to16InTx();

        /* TODO BEGIN 5 */
        tx->data_in = dut->data_in;
        tx->rst_n = dut->rst_n;
        tx->valid_in = dut->valid_in;
        /* TODO END 5 */

        scb->writeIn(tx);
    }
};

class width_8to16OutMon
{
private:
    Vwidth_8to16 *dut;
    width_8to16Scb *scb;

public:
    width_8to16OutMon(Vwidth_8to16 *dut, width_8to16Scb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        width_8to16OutTx *tx = new width_8to16OutTx();

        /* TODO BEGIN 6 */
        tx->data_out = dut->data_out;
        tx->valid_out = dut->valid_out;
        /* TODO END 6 */

        scb->writeOut(tx);
    }
};

width_8to16InTx *rndAluInTx()
{
    width_8to16InTx *tx = new width_8to16InTx();
    /* TODO BEGIN 7 */
    uint8_t tx_data_gen_time_increase = IS_SEQUENTIAL_LOGIC_EVAL(!dut->clk, combinational_logic_update);
    if (IS_SIM_TIME_IN_RST(sim_time))
        tx->rst_n = 0;
    else if (sim_time >= VERIF_START_TIME)
    {
        if (tx_data_gen_time_increase)
            switch (tx_data_gen_time)
            {
            case 0:
                in_tx_ref.rst_n = 1;
            default:

                in_tx_ref.data_in = rand() & 0xff;
                in_tx_ref.valid_in = rand() & 0x1;
                break;
            }

        tx->data_in = in_tx_ref.data_in;
        tx->rst_n = in_tx_ref.rst_n;
        tx->valid_in = in_tx_ref.valid_in;

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

    width_8to16InTx *tx;

    // Here we create the driver, scoreboard, input and output monitor blocks
    width_8to16InDrv *drv = new width_8to16InDrv(dut);
    width_8to16Scb *scb = new width_8to16Scb();
    width_8to16InMon *inMon = new width_8to16InMon(dut, scb);
    width_8to16OutMon *outMon = new width_8to16OutMon(dut, scb);

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

        combinational_logic_update ^= COMBINATIONAL_LOGIC_EVAL_EN;
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
