#include <verilated.h>
#include <verilated_vcd_c.h>
#include <stdio.h>
#include <vector>
#include <deque>
#include <time.h>
#include <cmath>
#include <iostream>
#include <Vtraffic_light__Syms.h>
#include <assert.h>

using namespace std;

Vtraffic_light *dut = new Vtraffic_light;

#define IS_SIM_TIME_IN_RST(sim_time) (sim_time >= 3 && sim_time < 6)
#define MAX_SIM_TIME 400
#define VERIF_START_TIME 7
#define MAX_STAGE 200
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
#define LATCH_MANAGEMENT_LATCH_ASSIGN(lm, x) (lm.latch_state = x)
#define LATCH_MANAGEMENT_LATCH_UPDATE(lm) (lm.latch_state = lm.after_latch_state)
#define LATCH_MANAGEMENT_AFTER_LATCH_ASSIGN(lm, x) (lm.after_latch_state = x)
#define LATCH_MANAGEMENT_IS_RISING_EDGE(lm) (!lm.latch_state && lm.after_latch_state)
#define LATCH_MANAGEMENT_IS_FALLING_EDGE(lm) (lm.latch_state && !lm.after_latch_state)

typedef struct
{
    uint64_t latch_state;
    uint64_t after_latch_state;
    uint64_t *selector;
} latch_management;

latch_management red_latch_management, green_latch_management, yellow_latch_management;

class traffic_lightInTx
{
public:
    /* TODO BEGIN 1 */
    uint8_t rst_n,
        pass_request;
    /* TODO END 1 */
};

class traffic_lightOutTx
{
public:
    /* TODO BEGIN 2 */
    uint8_t clock,
        red,
        yellow, green;
    /* TODO END 2 */
};

class traffic_lightInternalTx
{
public:
    /* TODO BEGIN 2 */
    uint8_t a0;
    /* TODO END 2 */
};

traffic_lightInTx in_tx_ref;
traffic_lightOutTx out_tx_ref;
traffic_lightInternalTx internal_tx_ref;

class traffic_lightScb
{
private:
    std::deque<traffic_lightInTx *> in_q;

public:
    // Input interface monitor port
    void writeIn(traffic_lightInTx *tx)
    {
        // Push the received transaction item into a queue for later
        in_q.push_back(tx);
    }

    // Output interface monitor port
    void writeOut(traffic_lightOutTx *tx)
    {
        // We should never get any data from the output interface
        // before an input gets driven to the input interface
        if (in_q.empty())
        {
            std::cout << "Fatal Error in traffic_lightScb: empty traffic_lightInTx queue" << std::endl;
            exit(1);
        }

        // Grab the transaction item from the front of the input item queue
        traffic_lightInTx *in;
        in = in_q.front();
        in_q.pop_front();

        /* TODO BEGIN 3 */
        if (!in->rst_n && sim_time >= 2)
        {
            if (!(tx->clock == 0xA && tx->green == 0x0 && tx->red == 0x0 && tx->yellow == 0x0))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->pass_request = 0x%x, in->rst_n = 0x%x", in->pass_request, in->rst_n);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->clock = 0x%x, tx->green = 0x%x, tx->red = 0x%x, tx->yellow = 0x%x", tx->clock, tx->green, tx->red, tx->yellow);
                Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: clock = 0x%x, green = 0x%x, red = 0x%x, yellow = 0x%x", 0xA, 0, 0, 0);

                Debug_printf("\r\n");
                fflush(stdout);

                myexit(0, tx->clock == 0x0 && tx->green == 0x0 && tx->red == 0x0 && tx->yellow == 0x0, "TODO 3 Failed: Reset logic result of the Verilog module is incorrect")
            }
        }
        else if (IS_SEQUENTIAL_LOGIC_EVAL(!dut->clk, combinational_logic_update))
        {
            LATCH_MANAGEMENT_LATCH_UPDATE(red_latch_management);
            LATCH_MANAGEMENT_LATCH_UPDATE(green_latch_management);
            LATCH_MANAGEMENT_LATCH_UPDATE(yellow_latch_management);

            LATCH_MANAGEMENT_AFTER_LATCH_ASSIGN(red_latch_management, tx->red);
            LATCH_MANAGEMENT_AFTER_LATCH_ASSIGN(green_latch_management, tx->green);
            LATCH_MANAGEMENT_AFTER_LATCH_ASSIGN(yellow_latch_management, tx->yellow);

            switch (tx_data_gen_time)
            {
            case 3:
                if (!(tx->clock == 0xA && LATCH_MANAGEMENT_IS_RISING_EDGE(red_latch_management)))
                {
                    Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                    Debug_printf("\r\n# TODO 3 INPUT TRACE: in->pass_request = 0x%x, in->rst_n = 0x%x", in->pass_request, in->rst_n);
                    Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->clock = 0x%x, tx->green = 0x%x, tx->red = 0x%x, tx->yellow = 0x%x", tx->clock, tx->green, tx->red, tx->yellow);
                    Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: clock = 0x%x", 0xA);

                    Debug_printf("\r\n");
                    fflush(stdout);

                    myexit(1, tx->clock == 0xA && LATCH_MANAGEMENT_IS_RISING_EDGE(red_latch_management), "TODO 3 Failed: Red Output logic result of the Verilog module is incorrect")
                }
                break;
            case 13:
                if (!(tx->clock == 0x3C && LATCH_MANAGEMENT_IS_FALLING_EDGE(red_latch_management) && LATCH_MANAGEMENT_IS_RISING_EDGE(green_latch_management)))
                {
                    Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                    Debug_printf("\r\n# TODO 3 INPUT TRACE: in->pass_request = 0x%x, in->rst_n = 0x%x", in->pass_request, in->rst_n);
                    Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->clock = 0x%x, tx->green = 0x%x, tx->red = 0x%x, tx->yellow = 0x%x", tx->clock, tx->green, tx->red, tx->yellow);
                    Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: clock = 0x%x", 0x3C);
                    Debug_printf("\r\n");
                    fflush(stdout);

                    myexit(2, tx->clock == 0x3C && LATCH_MANAGEMENT_IS_FALLING_EDGE(red_latch_management) && LATCH_MANAGEMENT_IS_RISING_EDGE(green_latch_management), "TODO 3 Failed: Green Output logic result of the Verilog module is incorrect")
                }
                break;
            case 73:
                if (!(tx->clock == 0x5 && LATCH_MANAGEMENT_IS_FALLING_EDGE(green_latch_management) && LATCH_MANAGEMENT_IS_RISING_EDGE(yellow_latch_management)))
                {
                    Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                    Debug_printf("\r\n# TODO 3 INPUT TRACE: in->pass_request = 0x%x, in->rst_n = 0x%x", in->pass_request, in->rst_n);
                    Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->clock = 0x%x, tx->green = 0x%x, tx->red = 0x%x, tx->yellow = 0x%x", tx->clock, tx->green, tx->red, tx->yellow);
                    Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: clock = 0x%x", 0x5);
                    Debug_printf("\r\n");
                    fflush(stdout);

                    myexit(3, tx->clock == 0x3C && LATCH_MANAGEMENT_IS_FALLING_EDGE(green_latch_management) && LATCH_MANAGEMENT_IS_RISING_EDGE(yellow_latch_management), "TODO 3 Failed: Yellow Output logic result of the Verilog module is incorrect")
                }
                break;
            case 135:
                if (!(tx->clock == 0xA && tx->green))
                {
                    Debug_printf("\r\n# TODO 3 NO Failed at simtime %ld %ld", sim_time, tx_data_gen_time);
                    Debug_printf("\r\n# TODO 3 INPUT TRACE: in->pass_request = 0x%x, in->rst_n = 0x%x", in->pass_request, in->rst_n);
                    Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->clock = 0x%x, tx->green = 0x%x, tx->red = 0x%x, tx->yellow = 0x%x", tx->clock, tx->green, tx->red, tx->yellow);
                    Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: clock = 0x%x", 0xA);
                    Debug_printf("\r\n");
                    fflush(stdout);

                    myexit(4, tx->clock == 0xA && tx->green, "TODO 3 Failed: pass_request logic result of the Verilog module is incorrect")
                }
                break;

            default:
                break;
            }
        }
        /* TODO END 3 */

        delete in;
        delete tx;
    }
};

class traffic_lightInDrv
{
private:
    Vtraffic_light *dut;

public:
    traffic_lightInDrv(Vtraffic_light *dut)
    {
        this->dut = dut;
    }

    void drive(traffic_lightInTx *tx)
    {
        /* TODO BEGIN 4 */
        if (tx != NULL)
        {
            dut->pass_request = tx->pass_request;
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

class traffic_lightInMon
{
private:
    Vtraffic_light *dut;
    traffic_lightScb *scb;

public:
    traffic_lightInMon(Vtraffic_light *dut, traffic_lightScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        traffic_lightInTx *tx = new traffic_lightInTx();

        /* TODO BEGIN 5 */
        tx->pass_request = dut->pass_request;
        tx->rst_n = dut->rst_n;
        /* TODO END 5 */

        scb->writeIn(tx);
    }
};

class traffic_lightOutMon
{
private:
    Vtraffic_light *dut;
    traffic_lightScb *scb;

public:
    traffic_lightOutMon(Vtraffic_light *dut, traffic_lightScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        traffic_lightOutTx *tx = new traffic_lightOutTx();

        /* TODO BEGIN 6 */
        tx->clock = dut->clock;
        tx->green = dut->green;
        tx->red = dut->red;
        tx->yellow = dut->yellow;
        /* TODO END 6 */

        scb->writeOut(tx);
    }
};

traffic_lightInTx *rndAluInTx()
{
    traffic_lightInTx *tx = new traffic_lightInTx();
    /* TODO BEGIN 7 */
    uint8_t tx_data_gen_time_increase = IS_SEQUENTIAL_LOGIC_EVAL(!dut->clk, combinational_logic_update);

    if (IS_SIM_TIME_IN_RST(sim_time))
        tx->rst_n = 0;

    else if (sim_time >= VERIF_START_TIME)
    {
        if (tx_data_gen_time_increase)
        {
            switch (tx_data_gen_time)
            {
            case 0:
                in_tx_ref.rst_n = 1;
                in_tx_ref.pass_request = 0;
                break;
            case 134:
                in_tx_ref.pass_request = 1;
                break;
            case 135:
                in_tx_ref.rst_n = 0;
                tx_data_gen_time = tx_data_gen_time_increase = 0;
                break;

            default:

                break;
            }
        }
        tx->pass_request = in_tx_ref.pass_request;
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

    traffic_lightInTx *tx;

    // Here we create the driver, scoreboard, input and output monitor blocks
    traffic_lightInDrv *drv = new traffic_lightInDrv(dut);
    traffic_lightScb *scb = new traffic_lightScb();
    traffic_lightInMon *inMon = new traffic_lightInMon(dut, scb);
    traffic_lightOutMon *outMon = new traffic_lightOutMon(dut, scb);

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
