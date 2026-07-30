#include <verilated.h>
#include <verilated_vcd_c.h>
#include <stdio.h>
#include <vector>
#include <deque>
#include <time.h>
#include <cmath>
#include <iostream>
#include <VRAM__Syms.h>
#include <assert.h>

using namespace std;

VRAM *dut = new VRAM;

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

class RAMInTx
{
public:
    /* TODO BEGIN 1 */
    uint8_t clk,
        rst_n,

        write_en,
        write_addr,
        write_data,

        read_en,
        read_addr;
    /* TODO END 1 */
};

class RAMOutTx
{
public:
    /* TODO BEGIN 2 */
    uint8_t read_data;
    /* TODO END 2 */
};

class RAMInternalTx
{
public:
    /* TODO BEGIN 2 */
    uint8_t a0;
    /* TODO END 2 */
};

RAMInTx in_tx_ref;
RAMOutTx out_tx_ref;
// RAMInternalTx internal_tx_ref;

class RAMScb
{
private:
    std::deque<RAMInTx *> in_q;

public:
    // Input interface monitor port
    void writeIn(RAMInTx *tx)
    {
        // Push the received transaction item into a queue for later
        in_q.push_back(tx);
    }

    // Output interface monitor port
    void writeOut(RAMOutTx *tx)
    {
        // We should never get any data from the output interface
        // before an input gets driven to the input interface
        if (in_q.empty())
        {
            std::cout << "Fatal Error in RAMScb: empty RAMInTx queue" << std::endl;
            exit(1);
        }

        // Grab the transaction item from the front of the input item queue
        RAMInTx *in;
        in = in_q.front();
        in_q.pop_front();

        /* TODO BEGIN 3 */
        if (!in->rst_n)
        {
            if (!(tx->read_data == 0x0))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->read_addr = 0x%x, in->read_en = 0x%x, in->rst_n = 0x%x, in->write_addr = 0x%x, in->write_data = 0x%x, in->write_en = 0x%x", in->read_addr, in->read_en, in->rst_n, in->write_addr, in->write_data, in->write_en);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->read_data = 0x%x", tx->read_data);
                Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: read_data = 0x%x", 0);

                Debug_printf("\r\n");
                fflush(stdout);

                myexit(0, tx->read_data == 0x0, "TODO 3 Failed: Reset logic result of the Verilog module is incorrect")
            }
        }
        else if (in->read_en)
        {
            if (!(tx->read_data == out_tx_ref.read_data))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->read_addr = 0x%x, in->read_en = 0x%x, in->rst_n = 0x%x, in->write_addr = 0x%x, in->write_data = 0x%x, in->write_en = 0x%x", in->read_addr, in->read_en, in->rst_n, in->write_addr, in->write_data, in->write_en);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->read_data = 0x%x", tx->read_data);
                Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: out_tx_ref.read_data = 0x%x", out_tx_ref.read_data);
                Debug_printf("\r\n");
                fflush(stdout);

                myexit(1, tx->read_data == out_tx_ref.read_data, "TODO 3 Failed: Memory logic result of the Verilog module is incorrect")
            }
        }

        /* TODO END 3 */

        delete in;
        delete tx;
    }
};

class RAMInDrv
{
private:
    VRAM *dut;

public:
    RAMInDrv(VRAM *dut)
    {
        this->dut = dut;
    }

    void drive(RAMInTx *tx)
    {
        /* TODO BEGIN 4 */
        if (tx != NULL)
        {

            dut->read_addr = tx->read_addr;
            dut->read_en = tx->read_en;
            dut->write_addr = tx->write_addr;
            dut->write_data = tx->write_data;
            dut->write_en = tx->write_en;

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

class RAMInMon
{
private:
    VRAM *dut;
    RAMScb *scb;

public:
    RAMInMon(VRAM *dut, RAMScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        RAMInTx *tx = new RAMInTx();

        /* TODO BEGIN 5 */
        tx->read_addr = dut->read_addr;
        tx->read_en = dut->read_en;
        tx->write_addr = dut->write_addr;
        tx->write_data = dut->write_data;
        tx->write_en = dut->write_en;
        tx->rst_n = dut->rst_n;
        /* TODO END 5 */

        scb->writeIn(tx);
    }
};

class RAMOutMon
{
private:
    VRAM *dut;
    RAMScb *scb;

public:
    RAMOutMon(VRAM *dut, RAMScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        RAMOutTx *tx = new RAMOutTx();

        /* TODO BEGIN 6 */
        tx->read_data = dut->read_data;
        /* TODO END 6 */

        scb->writeOut(tx);
    }
};

RAMInTx *rndAluInTx()
{
    RAMInTx *tx = new RAMInTx();
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
                in_tx_ref.write_en = 0;
                in_tx_ref.read_en = 0;
                in_tx_ref.read_addr = in_tx_ref.write_addr = 0x7;
                in_tx_ref.write_data = 0;
                break;
            case 1:
                in_tx_ref.read_addr++;
                in_tx_ref.write_addr++;
                in_tx_ref.read_addr &= 0x7;
                in_tx_ref.write_addr &= 0x7;

                in_tx_ref.write_en = 1;
                in_tx_ref.read_en = 0;

                in_tx_ref.write_data = out_tx_ref.read_data = rand() & 0x3f;
                break;
            case 2:
                in_tx_ref.write_en = 0;
                in_tx_ref.read_en = 1;
                break;
            case 3:
                tx_data_gen_time_increase = 0;
                tx_data_gen_time = 1;
                break;
            default:

                break;
            }

        tx->read_addr = in_tx_ref.read_addr;
        tx->read_en = in_tx_ref.read_en;
        tx->rst_n = in_tx_ref.rst_n;
        tx->write_addr = in_tx_ref.write_addr;
        tx->write_data = in_tx_ref.write_data;
        tx->write_en = in_tx_ref.write_en;

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

    RAMInTx *tx;

    // Here we create the driver, scoreboard, input and output monitor blocks
    RAMInDrv *drv = new RAMInDrv(dut);
    RAMScb *scb = new RAMScb();
    RAMInMon *inMon = new RAMInMon(dut, scb);
    RAMOutMon *outMon = new RAMOutMon(dut, scb);

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
