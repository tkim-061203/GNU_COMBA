#include <verilated.h>
#include <verilated_vcd_c.h>
#include <stdio.h>
#include <vector>
#include <deque>
#include <time.h>
#include <cmath>
#include <iostream>
#include <Vfsm__Syms.h>
#include <assert.h>

using namespace std;

Vfsm *dut = new Vfsm;

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

class fsmInTx
{
public:
    /* TODO BEGIN 1 */
    uint8_t IN, CLK, RST;
    /* TODO END 1 */
};

class fsmOutTx
{
public:
    /* TODO BEGIN 2 */
    uint8_t MATCH;
    /* TODO END 2 */
};

class fsmInternalTx
{
public:
    /* TODO BEGIN 2 */
    uint8_t ST_cache;
    /* TODO END 2 */
};

fsmInTx in_tx_ref;
fsmOutTx out_tx_ref;
fsmInternalTx internal_tx_ref;

class fsmScb
{
private:
    std::deque<fsmInTx *> in_q;

public:
    // Input interface monitor port
    void writeIn(fsmInTx *tx)
    {
        // Push the received transaction item into a queue for later
        in_q.push_back(tx);
    }

    // Output interface monitor port
    void writeOut(fsmOutTx *tx)
    {
        // We should never get any data from the output interface
        // before an input gets driven to the input interface
        if (in_q.empty())
        {
            std::cout << "Fatal Error in fsmScb: empty fsmInTx queue" << std::endl;
            exit(1);
        }

        // Grab the transaction item from the front of the input item queue
        fsmInTx *in;
        in = in_q.front();
        in_q.pop_front();

        /* TODO BEGIN 3 */
        if (in->RST)
        {
            internal_tx_ref.ST_cache = 0;
            if (!(tx->MATCH == 0x0))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->IN = 0x%x, in->RST = 0x%x", in->IN, in->RST);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->MATCH = 0x%x", tx->MATCH);
                Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: MATCH = 0x%x", 0);

                Debug_printf("\r\n");
                fflush(stdout);

                myexit(0, tx->MATCH == 0x0, "TODO 3 Failed: Reset logic result of the Verilog module is incorrect")
            }
        }
        else if (IS_SEQUENTIAL_LOGIC_EVAL(dut->CLK, combinational_logic_update))
        {
            internal_tx_ref.ST_cache <<= 1;
            internal_tx_ref.ST_cache |= in->IN;
            internal_tx_ref.ST_cache &= 0xf;
            out_tx_ref.MATCH = ((internal_tx_ref.ST_cache == 0b1001) && in->IN);
            // printf("\r\n# TODO 3 Update ST_cache at simtime %ld, %x, %x", sim_time, internal_tx_ref.ST_cache, out_tx_ref.MATCH);

            if (tx_data_gen_time == 5 || tx_data_gen_time == 9)
            {
                if (!(tx->MATCH == 0x1))
                {
                    Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                    Debug_printf("\r\n# TODO 3 INPUT TRACE: in->IN = 0x%x, in->RST = 0x%x", in->IN, in->RST);
                    Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->MATCH = 0x%x", tx->MATCH);
                    Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: MATCH = 0x%x", 1);

                    Debug_printf("\r\n");
                    fflush(stdout);

                    myexit(1, tx->MATCH == 0x0, "TODO 3 Failed: Logic result of MATCH assertion of the Verilog module is incorrect")
                }
            }
            else
            {
                if (!(tx->MATCH == out_tx_ref.MATCH))
                {
                    Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                    Debug_printf("\r\n# TODO 3 INPUT TRACE: in->IN = 0x%x, in->RST = 0x%x", in->IN, in->RST);
                    Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->MATCH = 0x%x", tx->MATCH);
                    Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: out_tx_ref.MATCH = 0x%x", out_tx_ref.MATCH);

                    Debug_printf("\r\n");
                    fflush(stdout);

                    myexit(2, tx->MATCH == out_tx_ref.MATCH, "TODO 3 Failed: Logic result of MATCH assertion of the Verilog module is incorrect")
                }
            }
        }
        /* TODO END 3 */

        delete in;
        delete tx;
    }
};

class fsmInDrv
{
private:
    Vfsm *dut;

public:
    fsmInDrv(Vfsm *dut)
    {
        this->dut = dut;
    }

    void drive(fsmInTx *tx)
    {
        /* TODO BEGIN 4 */
        if (tx != NULL)
        {
            dut->IN = tx->IN;
            dut->eval(); // combinational update

            dut->RST = tx->RST;
            delete tx;
        }
        /* TODO END 4 */

        dut->CLK ^= IS_SEQUENTIAL_LOGIC_UPDATE(combinational_logic_update);
        dut->eval(); // sequential update
    }
};

class fsmInMon
{
private:
    Vfsm *dut;
    fsmScb *scb;

public:
    fsmInMon(Vfsm *dut, fsmScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        fsmInTx *tx = new fsmInTx();

        /* TODO BEGIN 5 */
        tx->IN = dut->IN;
        tx->RST = dut->RST;
        /* TODO END 5 */

        scb->writeIn(tx);
    }
};

class fsmOutMon
{
private:
    Vfsm *dut;
    fsmScb *scb;

public:
    fsmOutMon(Vfsm *dut, fsmScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        fsmOutTx *tx = new fsmOutTx();

        /* TODO BEGIN 6 */
        tx->MATCH = dut->MATCH;
        /* TODO END 6 */

        scb->writeOut(tx);
    }
};

fsmInTx *rndAluInTx()
{
    fsmInTx *tx = new fsmInTx();
    // uint8_t tx_data_gen_time_increase = IS_SEQUENTIAL_LOGIC_EVAL(!dut->CLK, combinational_logic_update);
    uint8_t tx_data_gen_time_increase = IS_COMBINATIONAL_LOGIC_CONDITION_EVAL(combinational_logic_update, !dut->CLK);
    /* TODO BEGIN 7 */
    if (IS_SIM_TIME_IN_RST(sim_time))
        tx->RST = 1;
    else if (sim_time >= VERIF_START_TIME)
    {
        // printf("\r\n# Rand at simtime %ld %d %ld %d", sim_time, combinational_logic_update, tx_data_gen_time, tx_data_gen_time_increase);
        in_tx_ref.RST = 0;
        if (tx_data_gen_time_increase)
        {
            switch (tx_data_gen_time)
            {
            case 0:
                in_tx_ref.IN = 0x1;
                break;
            case 1:
                in_tx_ref.IN = 0x1;
                break;
            case 2:
                in_tx_ref.IN = 0x0;
                break;
            case 3:
                in_tx_ref.IN = 0x0;
                break;
            case 4:
                in_tx_ref.IN = 0x1;
                break;
            case 5:
                in_tx_ref.IN = 0x1;
                break;
            case 6:
                in_tx_ref.IN = 0x0;
                break;
            case 7:
                in_tx_ref.IN = 0x0;
                break;
            case 8:
                in_tx_ref.IN = 0x1;
                break;
            default:
                // if (IS_COMBINATIONAL_LOGIC_CONDITION_EVAL(combinational_logic_update, !dut->CLK))
                in_tx_ref.IN = rand() & 0x1;
                break;
            }
        }

        tx->IN = in_tx_ref.IN;
        tx->RST = in_tx_ref.RST;

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

    fsmInTx *tx;

    // Here we create the driver, scoreboard, input and output monitor blocks
    fsmInDrv *drv = new fsmInDrv(dut);
    fsmScb *scb = new fsmScb();
    fsmInMon *inMon = new fsmInMon(dut, scb);
    fsmOutMon *outMon = new fsmOutMon(dut, scb);

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
