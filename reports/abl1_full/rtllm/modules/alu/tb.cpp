#include <verilated.h>
#include <verilated_vcd_c.h>
#include <stdio.h>
#include <vector>
#include <deque>
#include <time.h>
#include <cmath>
#include <iostream>
#include <Valu__Syms.h>
#include <assert.h>

using namespace std;

Valu *dut = new Valu;

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

enum ALUCode
{
    ADD = 0b100000,
    ADDU = 0b100001,
    SUB = 0b100010,
    SUBU = 0b100011,
    AND = 0b100100,
    OR = 0b100101,
    XOR = 0b100110,
    NOR = 0b100111,
    SLT = 0b101010,
    SLTU = 0b101011,
    SLL = 0b000000,
    SRL = 0b000010,
    SRA = 0b000011,
    SLLV = 0b000100,
    SRLV = 0b000110,
    SRAV = 0b000111,
    LUI = 0b001111,
};

typedef struct
{
    uint64_t latch_state;
    uint64_t after_latch_state;
    uint64_t *selector;
} latch_management;

class aluInTx
{
public:
    /* TODO BEGIN 1 */
    union a_all
    {
        int64_t a_sign;
        uint64_t a;
    } a;
    union b_all
    {
        int64_t b_sign;
        uint64_t b;
    } b;
    uint8_t aluc;
    /* TODO END 1 */
};
struct FlagStruct
{
    uint8_t zero : 1,
        carry : 1,
        negative : 1,
        overflow : 1,
        flag : 1;
};

class aluOutTx
{
public:
    /* TODO BEGIN 2 */
    uint64_t r;
    struct FlagStruct flag;

    /* TODO END 2 */
};

class aluInternalTx
{
public:
    /* TODO BEGIN 2 */
    uint8_t a0;
    /* TODO END 2 */
};

// aluInTx in_tx_ref;
aluOutTx out_tx_ref;
// aluInternalTx internal_tx_ref;

class aluScb
{
private:
    std::deque<aluInTx *> in_q;

public:
    // Input interface monitor port
    void writeIn(aluInTx *tx)
    {
        // Push the received transaction item into a queue for later
        in_q.push_back(tx);
    }

    // Output interface monitor port
    void writeOut(aluOutTx *tx)
    {
        // We should never get any data from the output interface
        // before an input gets driven to the input interface
        if (in_q.empty())
        {
            std::cout << "Fatal Error in aluScb: empty aluInTx queue" << std::endl;
            exit(1);
        }

        // Grab the transaction item from the front of the input item queue
        aluInTx *in;
        in = in_q.front();
        in_q.pop_front();

        /* TODO BEGIN 3 */
        out_tx_ref.flag = {0};
        out_tx_ref.r = 0;
        out_tx_ref.flag.flag = (in->aluc == SLT || in->aluc == SLTU) ? (in->aluc == SLT) ? in->a.a_sign < in->b.b_sign : in->a.a < in->b.b : 0;

        switch (in->aluc)
        {
        case ADD:
            out_tx_ref.r = in->a.a_sign + in->b.b_sign;
            out_tx_ref.flag.carry = (out_tx_ref.r >> 32);
            out_tx_ref.flag.overflow = ((~((in->a.a_sign >> 31) & 0x1) & ~((in->b.b_sign >> 31) & 0x1) & ((out_tx_ref.r >> 31) & 0x1))) | ((((in->a.a_sign >> 31) & 0x1) & ((in->b.b_sign >> 31) & 0x1) & ~((out_tx_ref.r >> 31) & 0x1)));
            break;
        case ADDU:
            out_tx_ref.r = in->a.a + in->b.b;
            out_tx_ref.flag.carry = (out_tx_ref.r >> 32);
            out_tx_ref.flag.overflow = 0;
            break;
        case SUB:
            out_tx_ref.r = in->a.a_sign - in->b.b_sign;
            out_tx_ref.flag.carry = (out_tx_ref.r >> 32);
            out_tx_ref.flag.overflow = ((((in->a.a_sign >> 31) & 0x1) & ~((in->b.b_sign >> 31) & 0x1) & ~((out_tx_ref.r >> 31) & 0x1))) | ((~((in->a.a_sign >> 31) & 0x1) & ~((in->b.b_sign >> 31) & 0x1) & ((out_tx_ref.r >> 31) & 0x1)));
            break;
        case SUBU:
            out_tx_ref.r = in->a.a - in->b.b;
            out_tx_ref.flag.carry = (out_tx_ref.r >> 32);
            out_tx_ref.flag.overflow = 0;
            break;
        case AND:
            out_tx_ref.r = in->a.a & in->b.b;
            break;
        case OR:
            out_tx_ref.r = in->a.a | in->b.b;
            break;
        case XOR:
            out_tx_ref.r = in->a.a ^ in->b.b;
            break;
        case NOR:
            out_tx_ref.r = ~(in->a.a | in->b.b);
            break;
        case SLT:
            out_tx_ref.r = (in->a.a_sign < in->b.b_sign);
            break;
        case SLTU:
            out_tx_ref.r = (in->a.a < in->b.b);
            break;
        case SLL:
            out_tx_ref.r = out_tx_ref.r = ((uint32_t)in->a.a > 31) ? 0 : (uint32_t)in->b.b << (uint32_t)in->a.a;
            break;
        case SRL:
            out_tx_ref.r = ((uint32_t)in->a.a > 31) ? 0 : (uint32_t)in->b.b >> (uint32_t)in->a.a;
            break;
        case SRA:
            out_tx_ref.r = ((uint32_t)in->a.a > 31) ? 0 : (int32_t)in->b.b >> (uint32_t)in->a.a;
            break;
        case SLLV:
            out_tx_ref.r = ((uint32_t)in->b.b << (in->a.a & 0x1f));
            break;
        case SRLV:
            out_tx_ref.r = ((uint32_t)in->b.b >> (in->a.a & 0x1f));
            break;
        case SRAV:
            out_tx_ref.r = ((int32_t)in->b.b_sign >> (in->a.a_sign & 0x1f));
            break;
        case LUI:
            out_tx_ref.r = (in->a.a_sign & 0xffff) << 16;
            break;
        default:
            out_tx_ref.r = 0;
            break;
        }

        out_tx_ref.flag.zero = (out_tx_ref.r & 0xffffffff) == 0;
        out_tx_ref.flag.negative = out_tx_ref.r >> 31;

        if (!(tx->r == (out_tx_ref.r & 0xffffffff) &&
              tx->flag.carry == out_tx_ref.flag.carry &&
              tx->flag.flag == out_tx_ref.flag.flag &&
              tx->flag.negative == out_tx_ref.flag.negative &&
              tx->flag.overflow == out_tx_ref.flag.overflow &&
              tx->flag.zero == out_tx_ref.flag.zero))
        {
            Debug_printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
            Debug_printf("\r\n# TODO 3 INPUT TRACE: in->a.a = 0x%lx, in->b.b = 0x%lx, in->aluc = 0x%x", in->a.a, in->b.b, in->aluc);
            Debug_printf("\r\n# TODO 3 OUTPUT TRACE: tx->flag.carry = 0x%x, tx->flag.flag = 0x%x, tx->flag.negative = 0x%x, tx->flag.overflow = 0x%x, tx->flag.zero = 0x%x, tx->r = 0x%lx", tx->flag.carry, tx->flag.flag, tx->flag.negative, tx->flag.overflow, tx->flag.zero, tx->r);
            Debug_printf("\r\n# TODO 3 REFERENCE OUTPUT TRACE: out_tx_ref.flag.carry = 0x%x, out_tx_ref.flag.flag = 0x%x, out_tx_ref.flag.negative = 0x%x, out_tx_ref.flag.overflow = 0x%x, out_tx_ref.flag.zero = 0x%x, out_tx_ref.r = 0x%x, out_tx_ref.r = 0x%x", out_tx_ref.flag.carry, out_tx_ref.flag.flag, out_tx_ref.flag.negative, out_tx_ref.flag.overflow, out_tx_ref.flag.zero, out_tx_ref.r, (uint32_t)out_tx_ref.r);
            Debug_printf("\r\n");
            fflush(stdout);

            myexit(0, tx->r == (out_tx_ref.r & 0xffffffff) && tx->flag.carry == out_tx_ref.flag.carry && tx->flag.flag == out_tx_ref.flag.flag && tx->flag.negative == out_tx_ref.flag.negative && tx->flag.overflow == out_tx_ref.flag.overflow && tx->flag.zero == out_tx_ref.flag.zero,
                   "TODO 3 Failed: Operation logic result of the Verilog module is incorrect")
        }
        /* TODO END 3 */

        delete in;
        delete tx;
    }
};

class aluInDrv
{
private:
    Valu *dut;

public:
    aluInDrv(Valu *dut)
    {
        this->dut = dut;
    }

    void drive(aluInTx *tx)
    {
        /* TODO BEGIN 4 */
        if (tx != NULL)
        {
            dut->a = tx->a.a;
            dut->aluc = tx->aluc;
            dut->b = tx->b.b;
            if (COMBINATIONAL_LOGIC_EVAL_EN)
                dut->eval(); // combinational update
            delete tx;
        }
        /* TODO END 4 */

        dut->eval(); // sequential update
    }
};

class aluInMon
{
private:
    Valu *dut;
    aluScb *scb;

public:
    aluInMon(Valu *dut, aluScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        aluInTx *tx = new aluInTx();

        /* TODO BEGIN 5 */
        tx->a.a = dut->a;
        tx->aluc = dut->aluc;
        tx->b.b = dut->b;
        /* TODO END 5 */

        scb->writeIn(tx);
    }
};

class aluOutMon
{
private:
    Valu *dut;
    aluScb *scb;

public:
    aluOutMon(Valu *dut, aluScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        aluOutTx *tx = new aluOutTx();

        /* TODO BEGIN 6 */
        tx->flag.carry = dut->carry;
        tx->flag.flag = dut->flag;
        tx->flag.negative = dut->negative;
        tx->flag.overflow = dut->overflow;
        tx->flag.zero = dut->zero;
        tx->r = dut->r;
        /* TODO END 6 */

        scb->writeOut(tx);
    }
};

aluInTx *rndAluInTx()
{
    aluInTx *tx = new aluInTx();
    /* TODO BEGIN 7 */
    tx->a.a = rand();
    tx->aluc = rand() & 0x3f;
    tx->b.b = rand();
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

    aluInTx *tx;

    // Here we create the driver, scoreboard, input and output monitor blocks
    aluInDrv *drv = new aluInDrv(dut);
    aluScb *scb = new aluScb();
    aluInMon *inMon = new aluInMon(dut, scb);
    aluOutMon *outMon = new aluOutMon(dut, scb);

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
