#include <verilated.h>
#include <verilated_vcd_c.h>
#include <stdio.h>
#include <vector>
#include <deque>
#include <time.h>
#include <cmath>
#include <iostream>
#include <Vpulse_detect__Syms.h>
#include <assert.h>

using namespace std;

Vpulse_detect *dut = new Vpulse_detect;

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

class pulse_detectInTx
{
public:
    /* TODO BEGIN 1 */
    uint8_t rst_n,
        data_in;
    /* TODO END 1 */
};

class pulse_detectOutTx
{
public:
    /* TODO BEGIN 2 */
    uint8_t data_out;
    /* TODO END 2 */
};

pulse_detectInTx in_tx_ref;
pulse_detectOutTx out_tx_ref;

class pulse_detectScb
{
private:
    std::deque<pulse_detectInTx *> in_q;

public:
    // Input interface monitor port
    void writeIn(pulse_detectInTx *tx)
    {
        // Push the received transaction item into a queue for later
        in_q.push_back(tx);
    }

    // Output interface monitor port
    void writeOut(pulse_detectOutTx *tx)
    {
        // We should never get any data from the output interface
        // before an input gets driven to the input interface
        if (in_q.empty())
        {
            std::cout << "Fatal Error in pulse_detectScb: empty pulse_detectInTx queue" << std::endl;
            exit(1);
        }

        // Grab the transaction item from the front of the input item queue
        pulse_detectInTx *in;
        in = in_q.front();
        in_q.pop_front();

        /* TODO BEGIN 3 */
        if (IS_COMBINATIONAL_LOGIC_CONDITION_EVAL(combinational_logic_update, tx->data_out))
        {
            // printf("\r\n# TODO 3 check at simtime %ld, 0x%x", sim_time, out_tx_ref.data_out);
            if (!(out_tx_ref.data_out == 0x1))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->rst_n = 0x%x", in->rst_n);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->data_out = 0x%x", tx->data_out);
                Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: out_tx_ref.data_out = 0x%x", out_tx_ref.data_out);
                Debug_printf("\r\n");
                fflush(stdout);

                myexit(0, out_tx_ref.data_out == 0x1, "TODO 3 Failed: Pulse detection logic result of the Verilog module is incorrect")
            }
            out_tx_ref.data_out <<= 1;
        }
        else if (!in->rst_n)
        {
            out_tx_ref.data_out = 0;
            if (!(tx->data_out == 0))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->rst_n = 0x%x", in->rst_n);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->data_out = 0x%x", tx->data_out);
                Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: data_out = 0x%x", 0);

                Debug_printf("\r\n");
                fflush(stdout);

                myexit(1, tx->data_out == 0, "TODO 3 Failed: Reset logic result of the Verilog module is incorrect")
            }
        }
        else if (IS_SEQUENTIAL_LOGIC_EVAL(dut->clk, combinational_logic_update))
        {
            out_tx_ref.data_out <<= 1;
            out_tx_ref.data_out |= in->data_in;
            out_tx_ref.data_out &= 0x3;
            // printf("\r\n# TODO 3 Update at simtime %ld, 0x%x", sim_time, out_tx_ref.data_out);
        }

        /* TODO END 3 */

        delete in;
        delete tx;
    }
};

class pulse_detectInDrv
{
private:
    Vpulse_detect *dut;

public:
    pulse_detectInDrv(Vpulse_detect *dut)
    {
        this->dut = dut;
    }

    void drive(pulse_detectInTx *tx)
    {
        /* TODO BEGIN 4 */
        if (tx != NULL)
        {
            dut->data_in = tx->data_in;
            dut->eval(); // combinational update

            dut->rst_n = tx->rst_n; // sequential update
            delete tx;
        }
        /* TODO END 4 */

        dut->clk ^= IS_SEQUENTIAL_LOGIC_UPDATE(combinational_logic_update);
        dut->eval(); // sequential update
    }
};

class pulse_detectInMon
{
private:
    Vpulse_detect *dut;
    pulse_detectScb *scb;

public:
    pulse_detectInMon(Vpulse_detect *dut, pulse_detectScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        pulse_detectInTx *tx = new pulse_detectInTx();

        /* TODO BEGIN 5 */
        tx->data_in = dut->data_in;
        tx->rst_n = dut->rst_n;
        /* TODO END 5 */

        scb->writeIn(tx);
    }
};

class pulse_detectOutMon
{
private:
    Vpulse_detect *dut;
    pulse_detectScb *scb;

public:
    pulse_detectOutMon(Vpulse_detect *dut, pulse_detectScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        pulse_detectOutTx *tx = new pulse_detectOutTx();

        /* TODO BEGIN 6 */
        tx->data_out = dut->data_out;
        /* TODO END 6 */

        scb->writeOut(tx);
    }
};

pulse_detectInTx *rndAluInTx()
{
    pulse_detectInTx *tx = new pulse_detectInTx();
    uint8_t tx_data_gen_time_increase = dut->clk;
    /* TODO BEGIN 7 */
    if (IS_SIM_TIME_IN_RST(sim_time))
        tx->rst_n = 0;

    else if (sim_time >= VERIF_START_TIME)
    {
        switch (tx_data_gen_time)
        {
        case 0:
            in_tx_ref.rst_n = 1;
            break;
        default:
            if (IS_COMBINATIONAL_LOGIC_CONDITION_EVAL(combinational_logic_update, !dut->clk))
                in_tx_ref.data_in = rand() & 0x1;
            break;
        }

        tx->data_in = in_tx_ref.data_in;
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

    pulse_detectInTx *tx;

    // Here we create the driver, scoreboard, input and output monitor blocks
    pulse_detectInDrv *drv = new pulse_detectInDrv(dut);
    pulse_detectScb *scb = new pulse_detectScb();
    pulse_detectInMon *inMon = new pulse_detectInMon(dut, scb);
    pulse_detectOutMon *outMon = new pulse_detectOutMon(dut, scb);

    /* TODO BEGIN 8 */
    while (sim_time < MAX_SIM_TIME)
    {

        // dut->clk ^= (!combinational_logic_update);

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
