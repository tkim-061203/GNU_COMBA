#include <verilated.h>
#include <verilated_vcd_c.h>
#include <stdio.h>
#include <vector>
#include <deque>
#include <time.h>
#include <cmath>
#include <iostream>
#include <Vdiv_8bit__Syms.h>
#include <assert.h>

using namespace std;

#define IS_SIM_TIME_IN_RST(sim_time) (sim_time >= 3 && sim_time < 6)
#define MAX_SIM_TIME 300
#define VERIF_START_TIME 7
#define MAX_STAGE 6
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

class div_8bitInTx
{
public:
    /* TODO BEGIN 1 */
    uint8_t clk, rst, sign, opn_valid, res_ready;
    uint16_t dividend, divisor;
    /* TODO END 1 */
};

class div_8bitOutTx
{
public:
    /* TODO BEGIN 2 */
    uint8_t res_valid;
    uint16_t result;
    /* TODO END 2 */
};

div_8bitInTx in_tx_ref;
div_8bitOutTx out_tx_ref;

class div_8bitScb
{
private:
    std::deque<div_8bitInTx *> in_q;

public:
    // Input interface monitor port
    void writeIn(div_8bitInTx *tx)
    {
        // Push the received transaction item into a queue for later
        in_q.push_back(tx);
    }

    // Output interface monitor port
    void writeOut(div_8bitOutTx *tx)
    {
        // We should never get any data from the output interface
        // before an input gets driven to the input interface
        if (in_q.empty())
        {
            std::cout << "Fatal Error in div_8bitScb: empty div_8bitInTx queue" << std::endl;
            exit(1);
        }

        // Grab the transaction item from the front of the input item queue
        div_8bitInTx *in;
        in = in_q.front();
        in_q.pop_front();

        /* TODO BEGIN 3 */
        if (in->rst)
        {
            if (!(tx->res_valid == 0 && tx->result == 0))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->dividend = 0x%x, in->divisor = 0x%x, in->opn_valid = 0x%x, in->res_ready = 0x%x, in->sign = 0x%x", in->dividend, in->divisor, in->opn_valid, in->res_ready, in->sign);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->res_valid = 0x%x, tx->result = 0x%x", tx->res_valid, tx->result);

                Debug_printf("\r\n");
                fflush(stdout);

                myexit(0, tx->res_valid == 0 && tx->result == 0, "TODO 3 Failed: Reset logic result of the Verilog module is incorrect")
            }
        }
        else if (tx_data_gen_time == 3)
        {
            // calculation
            uint8_t quotient, remainer;
            if (in->sign)
            {
                quotient = (int8_t)in->dividend / (int8_t)in->divisor;
                remainer = (int8_t)in->dividend - (int8_t)quotient * (int8_t)in->divisor;
            }
            else
            {
                quotient = in->dividend / in->divisor;
                remainer = in->dividend - quotient * in->divisor;
            }
            uint16_t result = quotient | (remainer << 8);

            if (!(tx->result == result))
            {
                Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                Debug_printf("\r\n# TODO 3 INPUT TRACE: in->dividend = 0x%x, in->divisor = 0x%x, in->opn_valid = 0x%x, in->res_ready = 0x%x, in->sign = 0x%x", in->dividend, in->divisor, in->opn_valid, in->res_ready, in->sign);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->res_valid = 0x%x, tx->result = 0x%x", tx->res_valid, tx->result);
                Debug_printf("\r\n# TODO 3 OUTPUT TRACE: remainder = 0x%x, quotient = 0x%x", remainer, quotient);
                Debug_printf("\r\n");
                fflush(stdout);

                myexit(1, tx->result == result, "TODO 3 Failed: Division logic result of the Verilog module is incorrect when res_valid is on")
            }
        }

        /* TODO END 3 */

        delete in;
        delete tx;
    }
};

class div_8bitInDrv
{
private:
    Vdiv_8bit *dut;

public:
    div_8bitInDrv(Vdiv_8bit *dut)
    {
        this->dut = dut;
    }

    void drive(div_8bitInTx *tx)
    {
        /* TODO BEGIN 4 */
        if (tx != NULL)
        {
            dut->dividend = tx->dividend;
            dut->divisor = tx->divisor;
            dut->opn_valid = tx->opn_valid;
            dut->res_ready = tx->res_ready;
            dut->rst = tx->rst;
            dut->sign = tx->sign;
            delete tx;
        }
        /* TODO END 4 */

        dut->eval();
    }
};

class div_8bitInMon
{
private:
    Vdiv_8bit *dut;
    div_8bitScb *scb;

public:
    div_8bitInMon(Vdiv_8bit *dut, div_8bitScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        div_8bitInTx *tx = new div_8bitInTx();

        /* TODO BEGIN 5 */
        tx->dividend = dut->dividend;
        tx->divisor = dut->divisor;
        tx->opn_valid = dut->opn_valid;
        tx->res_ready = dut->res_ready;
        tx->rst = dut->rst;
        tx->sign = dut->sign;
        /* TODO END 5 */

        scb->writeIn(tx);
    }
};

class div_8bitOutMon
{
private:
    Vdiv_8bit *dut;
    div_8bitScb *scb;

public:
    div_8bitOutMon(Vdiv_8bit *dut, div_8bitScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        div_8bitOutTx *tx = new div_8bitOutTx();

        /* TODO BEGIN 6 */
        tx->res_valid = dut->res_valid;
        tx->result = dut->result;
        /* TODO END 6 */

        scb->writeOut(tx);
    }
};

div_8bitInTx *rndAluInTx()
{
    div_8bitInTx *tx = new div_8bitInTx();
    uint8_t tx_data_gen_time_increase = 1;
    /* TODO BEGIN 7 */
    if (IS_SIM_TIME_IN_RST(sim_time))
        tx->rst = 1;
    else if (sim_time >= VERIF_START_TIME)
    {
        switch (tx_data_gen_time)
        {
        case 0:
            in_tx_ref.dividend = rand() & 0xff;
            in_tx_ref.divisor = rand() & 0xff;
            in_tx_ref.sign = rand() & 0x1;
            in_tx_ref.opn_valid = 0x1;
            in_tx_ref.res_ready = 0;
            in_tx_ref.rst = 0;
            break;
        case 1:
            in_tx_ref.opn_valid = 0x0;
            break;
        case 2:
            if (!out_tx_ref.res_valid)
                tx_data_gen_time_increase = 0;
            break;
        case 3:
            in_tx_ref.res_ready = 1;
            break;
        case 4:
            if (out_tx_ref.res_valid)
                tx_data_gen_time_increase = 0;
            break;
        case 5:
            in_tx_ref.rst = 1;
            break;

        default:
            break;
        }

        tx->dividend = in_tx_ref.dividend;
        tx->divisor = in_tx_ref.divisor;
        tx->opn_valid = in_tx_ref.opn_valid;
        tx->res_ready = in_tx_ref.res_ready;
        tx->rst = in_tx_ref.rst;
        tx->sign = in_tx_ref.sign;

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
    Vdiv_8bit *dut = new Vdiv_8bit;

    Verilated::traceEverOn(true);
    VerilatedVcdC *m_trace = new VerilatedVcdC;
    dut->trace(m_trace, 5);
    m_trace->open("waveform.vcd");

    div_8bitInTx *tx;

    // Here we create the driver, scoreboard, input and output monitor blocks
    div_8bitInDrv *drv = new div_8bitInDrv(dut);
    div_8bitScb *scb = new div_8bitScb();
    div_8bitInMon *inMon = new div_8bitInMon(dut, scb);
    div_8bitOutMon *outMon = new div_8bitOutMon(dut, scb);

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
        out_tx_ref.res_valid = dut->res_valid;

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
