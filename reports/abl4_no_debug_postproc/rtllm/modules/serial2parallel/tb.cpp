#include <verilated.h>
#include <verilated_vcd_c.h>
#include <stdio.h>
#include <vector>
#include <deque>
#include <time.h>
#include <cmath>
#include <iostream>
#include <Vserial2parallel__Syms.h>
#include <assert.h>

using namespace std;

Vserial2parallel *dut = new Vserial2parallel;

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

class serial2parallelInTx
{
public:
    /* TODO BEGIN 1 */
    uint8_t rst_n,
        din_serial,
        din_valid;
    /* TODO END 1 */
};

class serial2parallelOutTx
{
public:
    /* TODO BEGIN 2 */
    uint8_t dout_parallel,
        dout_valid;
    /* TODO END 2 */
};

serial2parallelOutTx out_tx_ref;

class serial2parallelScb
{
private:
    std::deque<serial2parallelInTx *> in_q;

public:
    // Input interface monitor port
    void writeIn(serial2parallelInTx *tx)
    {
        // Push the received transaction item into a queue for later
        in_q.push_back(tx);
    }

    // Output interface monitor port
    void writeOut(serial2parallelOutTx *tx)
    {
        // We should never get any data from the output interface
        // before an input gets driven to the input interface
        if (in_q.empty())
        {
            std::cout << "Fatal Error in serial2parallelScb: empty serial2parallelInTx queue" << std::endl;
            exit(1);
        }

        // Grab the transaction item from the front of the input item queue
        serial2parallelInTx *in;
        in = in_q.front();
        in_q.pop_front();

        /* TODO BEGIN 3 */
        if (!in->rst_n)
        {
            if (!(tx->dout_parallel == 0 && tx->dout_valid == 0))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->rst_n = 0x%x", in->rst_n);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->dout_parallel = 0x%x, tx->dout_valid = 0x%x", tx->dout_parallel, tx->dout_valid);
                Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: dout_parallel = 0x%x, dout_valid = 0x%x", 0, 0);
                Debug_printf("\r\n");
                fflush(stdout);

                myexit(0, tx->dout_parallel == 0 && tx->dout_valid == 0, "TODO 3 Failed: Reset logic result of the Verilog module is incorrect")
            }
        }
        else if (tx->dout_valid)
        {

            if (!(tx->dout_parallel == out_tx_ref.dout_parallel))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->rst_n = 0x%x", in->rst_n);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->dout_parallel = 0x%x, tx->dout_valid = 0x%x", tx->dout_parallel, tx->dout_valid);
                Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: out_tx_ref.dout_parallel = 0x%x, tx->dout_valid = 0x%x", out_tx_ref.dout_parallel, tx->dout_valid);
                Debug_printf("\r\n");
                fflush(stdout);

                myexit(1, tx->dout_parallel == out_tx_ref.dout_parallel, "TODO 3 Failed: Parallel logic result of the Verilog module is incorrect")
            }
        }
        else if (in->din_valid)
        {
            out_tx_ref.dout_parallel <<= 1;
            out_tx_ref.dout_parallel |= in->din_serial;
        }
        /* TODO END 3 */

        delete in;
        delete tx;
    }
};

class serial2parallelInDrv
{
private:
    Vserial2parallel *dut;

public:
    serial2parallelInDrv(Vserial2parallel *dut)
    {
        this->dut = dut;
    }

    void drive(serial2parallelInTx *tx)
    {
        /* TODO BEGIN 4 */
        if (tx != NULL)
        {
            dut->din_serial = tx->din_serial;
            dut->din_valid = tx->din_valid;
            dut->rst_n = tx->rst_n;

            delete tx;
        }
        /* TODO END 4 */

        dut->eval();
    }
};

class serial2parallelInMon
{
private:
    Vserial2parallel *dut;
    serial2parallelScb *scb;

public:
    serial2parallelInMon(Vserial2parallel *dut, serial2parallelScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        serial2parallelInTx *tx = new serial2parallelInTx();

        /* TODO BEGIN 5 */
        tx->din_serial = dut->din_serial;
        tx->din_valid = dut->din_valid;
        tx->rst_n = dut->rst_n;
        /* TODO END 5 */

        scb->writeIn(tx);
    }
};

class serial2parallelOutMon
{
private:
    Vserial2parallel *dut;
    serial2parallelScb *scb;

public:
    serial2parallelOutMon(Vserial2parallel *dut, serial2parallelScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        serial2parallelOutTx *tx = new serial2parallelOutTx();

        /* TODO BEGIN 6 */
        tx->dout_parallel = dut->dout_parallel;
        tx->dout_valid = dut->dout_valid;
        /* TODO END 6 */

        scb->writeOut(tx);
    }
};

serial2parallelInTx *rndAluInTx()
{
    serial2parallelInTx *tx = new serial2parallelInTx();
    uint8_t tx_data_gen_time_increase = dut->clk;
    /* TODO BEGIN 7 */

    if (IS_SIM_TIME_IN_RST(sim_time))
    {
        tx->rst_n = 0;
        out_tx_ref.dout_parallel = 0;
    }
    else if (sim_time >= VERIF_START_TIME)
    {
        switch (tx_data_gen_time)
        {
        case 9:
            tx->rst_n = 0;
            tx->din_valid = 0;
            out_tx_ref.dout_parallel = 0;

            tx_data_gen_time = 0;
            tx_data_gen_time_increase = 0;
            break;
        default:
            tx->rst_n = 1;
            tx->din_serial = rand() & 0x1;
            tx->din_valid = 1;
            break;
        }

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

    serial2parallelInTx *tx;

    // Here we create the driver, scoreboard, input and output monitor blocks
    serial2parallelInDrv *drv = new serial2parallelInDrv(dut);
    serial2parallelScb *scb = new serial2parallelScb();
    serial2parallelInMon *inMon = new serial2parallelInMon(dut, scb);
    serial2parallelOutMon *outMon = new serial2parallelOutMon(dut, scb);

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
