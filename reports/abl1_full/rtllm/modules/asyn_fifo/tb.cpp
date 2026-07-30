#include <verilated.h>
#include <verilated_vcd_c.h>
#include <stdio.h>
#include <vector>
#include <deque>
#include <time.h>
#include <cmath>
#include <iostream>
#include <Vasyn_fifo__Syms.h>
#include <assert.h>

using namespace std;

Vasyn_fifo *dut = new Vasyn_fifo;

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

class asyn_fifoInTx
{
public:
    /* TODO BEGIN 1 */
    uint8_t wclk,
        rclk,
        wrstn,
        rrstn,
        winc,
        rinc,
        wdata;
    /* TODO END 1 */
};

class asyn_fifoOutTx
{
public:
    /* TODO BEGIN 2 */
    uint8_t wfull,
        rempty,
        rdata;
    /* TODO END 2 */
};

class asyn_fifoInternalTx
{
public:
    /* TODO BEGIN 2 */
    uint8_t RAM[16];
    uint8_t addr;
    /* TODO END 2 */
};

asyn_fifoInTx in_tx_ref;
// asyn_fifoOutTx out_tx_ref;
asyn_fifoInternalTx internal_tx_ref;

class asyn_fifoScb
{
private:
    std::deque<asyn_fifoInTx *> in_q;

public:
    // Input interface monitor port
    void writeIn(asyn_fifoInTx *tx)
    {
        // Push the received transaction item into a queue for later
        in_q.push_back(tx);
    }

    // Output interface monitor port
    void writeOut(asyn_fifoOutTx *tx)
    {
        // We should never get any data from the output interface
        // before an input gets driven to the input interface
        if (in_q.empty())
        {
            std::cout << "Fatal Error in asyn_fifoScb: empty asyn_fifoInTx queue" << std::endl;
            exit(1);
        }

        // Grab the transaction item from the front of the input item queue
        asyn_fifoInTx *in;
        in = in_q.front();
        in_q.pop_front();

        /* TODO BEGIN 3 */
        if (!in->wrstn && !in->rrstn)
        {
            if (!(tx->rempty == 0x1 && tx->wfull == 0x0))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->rinc = 0x%x, in->rrstn = 0x%x, in->wdata = 0x%x, in->winc = 0x%x, in->wrstn = 0x%x", in->rinc, in->rrstn, in->wdata, in->winc, in->wrstn);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->rdata = 0x%x, tx->rempty = 0x%x, tx->wfull = 0x%x", tx->rdata, tx->rempty, tx->wfull);
                Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: rempty = 0x%x, wfull = 0x%x", 1, 0);

                Debug_printf("\r\n");
                fflush(stdout);

                myexit(0, tx->rempty == 0x1 && tx->wfull == 0x0, "TODO 3 Failed: Reset logic result of the Verilog module is incorrect")
            }
        }
        else if (IS_SEQUENTIAL_LOGIC_EVAL(dut->wclk, combinational_logic_update))
        {
            if (tx_data_gen_time == 3)
            {
                if (!(tx->rempty == 0x0 && tx->wfull == 0x1))
                {
                    Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                    Debug_printf("\r\n# TODO 3 INPUT TRACE: in->rinc = 0x%x, in->rrstn = 0x%x, in->wdata = 0x%x, in->winc = 0x%x, in->wrstn = 0x%x", in->rinc, in->rrstn, in->wdata, in->winc, in->wrstn);
                    Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->rdata = 0x%x, tx->rempty = 0x%x, tx->wfull = 0x%x", tx->rdata, tx->rempty, tx->wfull);
                    Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: internal_tx_ref.RAM[internal_tx_ref.addr] = 0x%x, internal_tx_ref.addr = 0x%x", internal_tx_ref.RAM[internal_tx_ref.addr], internal_tx_ref.addr);
                    Debug_printf("\r\n");
                    fflush(stdout);

                    myexit(1, tx->rempty == 0x0 && tx->wfull == 0x1, "TODO 3 Failed: wfull logic result of the Verilog module is incorrect")
                }
            }
            else if (tx_data_gen_time == 11 && IS_SEQUENTIAL_LOGIC_EVAL(dut->rclk, combinational_logic_update))
            {
                if (!(tx->rempty == 0x0 && tx->rdata == internal_tx_ref.RAM[internal_tx_ref.addr]))
                {
                    Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                    Debug_printf("\r\n# TODO 3 INPUT TRACE: in->rinc = 0x%x, in->rrstn = 0x%x, in->wdata = 0x%x, in->winc = 0x%x, in->wrstn = 0x%x", in->rinc, in->rrstn, in->wdata, in->winc, in->wrstn);
                    Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->rdata = 0x%x, tx->rempty = 0x%x, tx->wfull = 0x%x", tx->rdata, tx->rempty, tx->wfull);
                    Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: internal_tx_ref.RAM[internal_tx_ref.addr] = 0x%x, internal_tx_ref.addr = 0x%x", internal_tx_ref.RAM[internal_tx_ref.addr], internal_tx_ref.addr);
                    Debug_printf("\r\n");
                    fflush(stdout);

                    myexit(2, tx->rempty == 0x0 && tx->rdata == internal_tx_ref.RAM[internal_tx_ref.addr], "TODO 3 Failed: rdata logic result of the Verilog module is incorrect")
                }
            }
        }
        /* TODO END 3 */

        delete in;
        delete tx;
    }
};

class asyn_fifoInDrv
{
private:
    Vasyn_fifo *dut;

public:
    asyn_fifoInDrv(Vasyn_fifo *dut)
    {
        this->dut = dut;
    }

    void drive(asyn_fifoInTx *tx)
    {
        /* TODO BEGIN 4 */
        if (tx != NULL)
        {
            dut->rinc = tx->rinc;
            dut->wdata = tx->wdata;
            dut->winc = tx->winc;
            if (COMBINATIONAL_LOGIC_EVAL_EN)
                dut->eval(); // combinational update
            dut->wrstn = tx->wrstn;
            dut->rrstn = tx->rrstn;
            delete tx;
        }
        /* TODO END 4 */

        dut->wclk ^= IS_SEQUENTIAL_LOGIC_UPDATE(combinational_logic_update);

        if (IS_SEQUENTIAL_LOGIC_EVAL(dut->wclk, combinational_logic_update))
            dut->rclk ^= 1;

        dut->eval(); // sequential update
    }
};

class asyn_fifoInMon
{
private:
    Vasyn_fifo *dut;
    asyn_fifoScb *scb;

public:
    asyn_fifoInMon(Vasyn_fifo *dut, asyn_fifoScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        asyn_fifoInTx *tx = new asyn_fifoInTx();

        /* TODO BEGIN 5 */
        tx->rinc = dut->rinc;
        tx->rrstn = dut->rrstn;
        tx->wdata = dut->wdata;
        tx->winc = dut->winc;
        tx->wrstn = dut->wrstn;
        /* TODO END 5 */

        scb->writeIn(tx);
    }
};

class asyn_fifoOutMon
{
private:
    Vasyn_fifo *dut;
    asyn_fifoScb *scb;

public:
    asyn_fifoOutMon(Vasyn_fifo *dut, asyn_fifoScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        asyn_fifoOutTx *tx = new asyn_fifoOutTx();

        /* TODO BEGIN 6 */
        tx->rdata = dut->rdata;
        tx->rempty = dut->rempty;
        tx->wfull = dut->wfull;
        /* TODO END 6 */

        scb->writeOut(tx);
    }
};

asyn_fifoInTx *rndAluInTx()
{
    asyn_fifoInTx *tx = new asyn_fifoInTx();
    /* TODO BEGIN 7 */
    uint8_t tx_data_gen_time_increase = IS_SEQUENTIAL_LOGIC_EVAL(!dut->wclk, combinational_logic_update);
    if (IS_SIM_TIME_IN_RST(sim_time))
    {
        tx->rrstn = tx->wrstn = 0;
    }

    else if (sim_time >= VERIF_START_TIME)
    {
        // printf("\r\nsim_time = %ld, tx_data_gen_time = %ld, tx_data_gen_time_increase = %d", sim_time, tx_data_gen_time, tx_data_gen_time_increase);
        if (tx_data_gen_time_increase)
            switch (tx_data_gen_time)
            {
            case 0:
                in_tx_ref.rrstn = in_tx_ref.wrstn = 1;
                in_tx_ref.winc = in_tx_ref.rinc = 0;
            case 1:
                in_tx_ref.winc = 1;
                in_tx_ref.wdata = internal_tx_ref.RAM[internal_tx_ref.addr++] = rand() & 0xff;
                internal_tx_ref.addr &= internal_tx_ref.addr & 0xf;

                tx_data_gen_time = 1;
                tx_data_gen_time_increase = (internal_tx_ref.addr == 0);
                break;
            case 2:
                in_tx_ref.winc = 0;
                break;
            case 10:
                in_tx_ref.rinc = 1;
                break;
            case 11:
                if (IS_SEQUENTIAL_LOGIC_EVAL(!dut->rclk, combinational_logic_update))
                {
                    internal_tx_ref.addr++;
                    internal_tx_ref.addr &= internal_tx_ref.addr & 0xf;
                    tx_data_gen_time_increase = (internal_tx_ref.addr == 0);
                }
                else
                {
                    tx_data_gen_time_increase = 0;
                }
                tx_data_gen_time = 11;

                break;
            case 12:
                in_tx_ref.rinc = 0;
                break;
            case 20:
                in_tx_ref.rrstn = in_tx_ref.wrstn = 0;
                tx_data_gen_time = 0;
                tx_data_gen_time_increase = 0;
            default:
                break;
            }

        tx->rinc = in_tx_ref.rinc;
        tx->rrstn = in_tx_ref.rrstn;
        tx->wdata = in_tx_ref.wdata;
        tx->winc = in_tx_ref.winc;
        tx->wrstn = in_tx_ref.wrstn;

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

    asyn_fifoInTx *tx;

    // Here we create the driver, scoreboard, input and output monitor blocks
    asyn_fifoInDrv *drv = new asyn_fifoInDrv(dut);
    asyn_fifoScb *scb = new asyn_fifoScb();
    asyn_fifoInMon *inMon = new asyn_fifoInMon(dut, scb);
    asyn_fifoOutMon *outMon = new asyn_fifoOutMon(dut, scb);

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
