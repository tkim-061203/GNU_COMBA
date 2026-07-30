#include <verilated.h>
#include <verilated_vcd_c.h>
#include <stdio.h>
#include <vector>
#include <deque>
#include <time.h>
#include <cmath>
#include <iostream>
#include <Vcalendar__Syms.h>
#include <assert.h>

using namespace std;

Vcalendar *dut = new Vcalendar;

#define IS_SIM_TIME_IN_RST(sim_time) (sim_time >= 3 && sim_time < 6)
#define MAX_SIM_TIME 172810
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

class calendarInTx
{
public:
    /* TODO BEGIN 1 */
    uint8_t CLK, RST;
    /* TODO END 1 */
};

class calendarOutTx
{
public:
    /* TODO BEGIN 2 */
    uint8_t Hours, Mins, Secs;
    /* TODO END 2 */
};

class calendarInternalTx
{
public:
    /* TODO BEGIN 2 */
    uint8_t a0;
    /* TODO END 2 */
};

calendarInTx in_tx_ref;
calendarOutTx out_tx_ref;
// calendarInternalTx internal_tx_ref;

class calendarScb
{
private:
    std::deque<calendarInTx *> in_q;

public:
    // Input interface monitor port
    void writeIn(calendarInTx *tx)
    {
        // Push the received transaction item into a queue for later
        in_q.push_back(tx);
    }

    // Output interface monitor port
    void writeOut(calendarOutTx *tx)
    {
        // We should never get any data from the output interface
        // before an input gets driven to the input interface
        if (in_q.empty())
        {
            std::cout << "Fatal Error in calendarScb: empty calendarInTx queue" << std::endl;
            exit(1);
        }

        // Grab the transaction item from the front of the input item queue
        calendarInTx *in;
        in = in_q.front();
        in_q.pop_front();

        /* TODO BEGIN 3 */
        if (in->RST)
        {
            out_tx_ref.Hours = out_tx_ref.Mins = out_tx_ref.Secs = 0;
            if (!(tx->Hours == 0x0 && tx->Mins == 0x0 && tx->Secs == 0x0))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->RST = 0x%x", in->RST);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->Hours = 0x%x, tx->Mins = 0x%x, tx->Secs = 0x%x", tx->Hours, tx->Mins, tx->Secs);
                Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: out_tx_ref.Hours = 0x%x, out_tx_ref.Mins = 0x%x, out_tx_ref.Secs = 0x%x", out_tx_ref.Hours, out_tx_ref.Mins, out_tx_ref.Secs);
                Debug_printf("\r\n");
                fflush(stdout);

                myexit(0, tx->Hours == 0x0 && tx->Mins == 0x0 && tx->Secs == 0x0, "TODO 3 Failed: Reset logic result of the Verilog module is incorrect")
            }
        }
        else if (IS_SEQUENTIAL_LOGIC_EVAL(dut->CLK, combinational_logic_update) && sim_time > 2)
        {
            out_tx_ref.Secs += 1;
            out_tx_ref.Mins += out_tx_ref.Secs == 60;
            out_tx_ref.Hours += out_tx_ref.Mins == 60;

            out_tx_ref.Secs %= 60;
            out_tx_ref.Mins %= 60;
            out_tx_ref.Hours %= 24;

            if (!(tx->Hours == out_tx_ref.Hours && tx->Mins == out_tx_ref.Mins && tx->Secs == out_tx_ref.Secs))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->RST = 0x%x", in->RST);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->Hours = 0x%x, tx->Mins = 0x%x, tx->Secs = 0x%x", tx->Hours, tx->Mins, tx->Secs);
                Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: out_tx_ref.Hours = 0x%x, out_tx_ref.Mins = 0x%x, out_tx_ref.Secs = 0x%x", out_tx_ref.Hours, out_tx_ref.Mins, out_tx_ref.Secs);
                Debug_printf("\r\n");
                fflush(stdout);

                myexit(1, tx->Hours == out_tx_ref.Hours && tx->Mins == out_tx_ref.Mins && tx->Secs == out_tx_ref.Secs, "TODO 3 Failed: Counter logic result for Hours, Mins, and Secs of the Verilog module is incorrect")
            }
        }
        /* TODO END 3 */

        delete in;
        delete tx;
    }
};

class calendarInDrv
{
private:
    Vcalendar *dut;

public:
    calendarInDrv(Vcalendar *dut)
    {
        this->dut = dut;
    }

    void drive(calendarInTx *tx)
    {
        /* TODO BEGIN 4 */
        if (tx != NULL)
        {
            dut->RST = tx->RST;
            if (COMBINATIONAL_LOGIC_EVAL_EN)
                dut->eval(); // combinational update
            delete tx;
        }
        /* TODO END 4 */

        dut->CLK ^= IS_SEQUENTIAL_LOGIC_UPDATE(combinational_logic_update);
        dut->eval(); // sequential update
    }
};

class calendarInMon
{
private:
    Vcalendar *dut;
    calendarScb *scb;

public:
    calendarInMon(Vcalendar *dut, calendarScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        calendarInTx *tx = new calendarInTx();

        /* TODO BEGIN 5 */
        tx->RST = dut->RST;
        /* TODO END 5 */

        scb->writeIn(tx);
    }
};

class calendarOutMon
{
private:
    Vcalendar *dut;
    calendarScb *scb;

public:
    calendarOutMon(Vcalendar *dut, calendarScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        calendarOutTx *tx = new calendarOutTx();

        /* TODO BEGIN 6 */
        tx->Hours = dut->Hours;
        tx->Mins = dut->Mins;
        tx->Secs = dut->Secs;
        /* TODO END 6 */

        scb->writeOut(tx);
    }
};

calendarInTx *rndAluInTx()
{
    calendarInTx *tx = new calendarInTx();
    /* TODO BEGIN 7 */
    uint8_t tx_data_gen_time_increase = IS_COMBINATIONAL_LOGIC_CONDITION_EVAL(combinational_logic_update, !dut->CLK);
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

    calendarInTx *tx;

    // Here we create the driver, scoreboard, input and output monitor blocks
    calendarInDrv *drv = new calendarInDrv(dut);
    calendarScb *scb = new calendarScb();
    calendarInMon *inMon = new calendarInMon(dut, scb);
    calendarOutMon *outMon = new calendarOutMon(dut, scb);

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

        // if (sim_time > (MAX_SIM_TIME - 20))
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
