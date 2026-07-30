#include <verilated.h>
#include <verilated_vcd_c.h>
#include <stdio.h>
#include <vector>
#include <deque>
#include <time.h>
#include <cmath>
#include <iostream>
#include <Vedge_detect__Syms.h>
#include <assert.h>

using namespace std;

Vedge_detect *dut = new Vedge_detect;

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

vluint8_t combinational_logic_update = 1;
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

class edge_detectInTx
{
public:
    /* TODO BEGIN 1 */
    uint8_t rst_n, a;
    /* TODO END 1 */
};

class edge_detectOutTx
{
public:
    /* TODO BEGIN 2 */
    uint8_t rise, down;
    /* TODO END 2 */
};

edge_detectInTx in_tx_ref;
edge_detectOutTx out_tx_ref;

class edge_detectInternalTx
{
public:
    /* TODO BEGIN 2 */
    uint8_t a0;
    /* TODO END 2 */
};

edge_detectInternalTx internal_tx_ref;

class edge_detectScb
{
private:
    std::deque<edge_detectInTx *> in_q;

public:
    // Input interface monitor port
    void writeIn(edge_detectInTx *tx)
    {
        // Push the received transaction item into a queue for later
        in_q.push_back(tx);
    }

    // Output interface monitor port
    void writeOut(edge_detectOutTx *tx)
    {
        // We should never get any data from the output interface
        // before an input gets driven to the input interface
        if (in_q.empty())
        {
            std::cout << "Fatal Error in edge_detectScb: empty edge_detectInTx queue" << std::endl;
            exit(1);
        }

        // Grab the transaction item from the front of the input item queue
        edge_detectInTx *in;
        in = in_q.front();
        in_q.pop_front();

        /* TODO BEGIN 3 */
        if (!in->rst_n)
        {
            if (!(tx->down == 0x0 && tx->rise == 0))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->rst_n = 0x%x, in->a = 0x%x", in->rst_n, in->a);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->down = 0x%x, tx->rise = 0x%x", tx->down, tx->rise);
                Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: down = 0x%x, rise = 0x%x", 0, 0);

                Debug_printf("\r\n");
                fflush(stdout);

                myexit(0, tx->down == 0x0 && tx->rise == 0, "TODO 3 Failed: Reset logic result of the Verilog module is incorrect")
            }
        }
        else if (IS_SEQUENTIAL_LOGIC_EVAL(dut->clk, combinational_logic_update))
        {
            internal_tx_ref.a0 <<= 1;
            internal_tx_ref.a0 |= in->a;
            internal_tx_ref.a0 &= 0x3;

            out_tx_ref.down = (internal_tx_ref.a0 == 0b10);
            out_tx_ref.rise = (internal_tx_ref.a0 == 0b01);

            if (!(out_tx_ref.down == tx->down && out_tx_ref.rise == tx->rise))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->rst_n = 0x%x, in->a = 0x%x", in->rst_n, in->a);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->down = 0x%x, tx->rise = 0x%x", tx->down, tx->rise);
                Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: out_tx_ref.down = 0x%x, out_tx_ref.rise = 0x%x", out_tx_ref.down, out_tx_ref.rise);

                Debug_printf("\r\n");
                fflush(stdout);

                myexit(1, out_tx_ref.down == 0x0 && out_tx_ref.rise == 0, "TODO 3 Failed: Edge-Detection logic result of the Verilog module is incorrect")
            }
        }
        /* TODO END 3 */

        delete in;
        delete tx;
    }
};

class edge_detectInDrv
{
private:
    Vedge_detect *dut;

public:
    edge_detectInDrv(Vedge_detect *dut)
    {
        this->dut = dut;
    }

    void drive(edge_detectInTx *tx)
    {
        /* TODO BEGIN 4 */
        if (tx != NULL)
        {
            dut->a = tx->a;
            dut->eval(); // combinational update

            dut->rst_n = tx->rst_n;
            delete tx;
        }
        /* TODO END 4 */

        dut->clk ^= IS_SEQUENTIAL_LOGIC_UPDATE(combinational_logic_update);
        dut->eval(); // sequential update
    }
};

class edge_detectInMon
{
private:
    Vedge_detect *dut;
    edge_detectScb *scb;

public:
    edge_detectInMon(Vedge_detect *dut, edge_detectScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        edge_detectInTx *tx = new edge_detectInTx();

        /* TODO BEGIN 5 */
        tx->a = dut->a;
        tx->rst_n = dut->rst_n;
        /* TODO END 5 */

        scb->writeIn(tx);
    }
};

class edge_detectOutMon
{
private:
    Vedge_detect *dut;
    edge_detectScb *scb;

public:
    edge_detectOutMon(Vedge_detect *dut, edge_detectScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        edge_detectOutTx *tx = new edge_detectOutTx();

        /* TODO BEGIN 6 */
        tx->down = dut->down;
        tx->rise = dut->rise;
        /* TODO END 6 */

        scb->writeOut(tx);
    }
};

edge_detectInTx *rndAluInTx()
{
    edge_detectInTx *tx = new edge_detectInTx();
    uint8_t tx_data_gen_time_increase = dut->clk;
    /* TODO BEGIN 7 */
    if (IS_SIM_TIME_IN_RST(sim_time))
        tx->rst_n = 0;

    if (sim_time >= VERIF_START_TIME)
    {
        switch (tx_data_gen_time)
        {
        case 0:
            in_tx_ref.rst_n = 1;
            break;

        default:
            if (IS_SEQUENTIAL_LOGIC_EVAL(!dut->clk, combinational_logic_update))
            {
                in_tx_ref.a = rand() & 0x1;
            }
            break;
        }

        tx->a = in_tx_ref.a;
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

    edge_detectInTx *tx;

    // Here we create the driver, scoreboard, input and output monitor blocks
    edge_detectInDrv *drv = new edge_detectInDrv(dut);
    edge_detectScb *scb = new edge_detectScb();
    edge_detectInMon *inMon = new edge_detectInMon(dut, scb);
    edge_detectOutMon *outMon = new edge_detectOutMon(dut, scb);

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

        combinational_logic_update ^= 1;
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
