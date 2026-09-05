# Bang tong hop cell-count bloat (chi nhom PASS + comparable)

| Benchmark | N | Cell sinh (trung vi) | Cell tham chieu (trung vi) | Trung vi ratio | TB nhan ratio | ratio<=1.0 | ratio>1.5 | ratio>2.0 | Latch phat sinh |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| RTLLM v1.1 | 28 | 17.5 | 24.0 | 0.902 | 0.596 | 24 | 0 | 0 | 0 |
| RTLLM v2.0 | 33 | 11.0 | 17.0 | 0.857 | 0.660 | 28 | 1 | 1 | 0 |
| VerilogEval V2 (e0_t0) | 88 | 5.0 | 4.0 | 1.000 | 1.480 | 48 | 27 | 18 | 2 |
| VerilogEval V2 (e0_t8) | 92 | 5.0 | 4.0 | 1.000 | 1.498 | 48 | 28 | 18 | 2 |
| VerilogEval V2 (e1_t0) | 120 | 6.0 | 5.0 | 1.000 | 1.451 | 66 | 34 | 22 | 2 |
| VerilogEval V2 (e1_t8) | 120 | 6.0 | 5.0 | 1.000 | 1.459 | 65 | 33 | 20 | 3 |

## Cell-type breakdown (% tren tong so cell cua ma sinh ra, nhom comparable)

| Benchmark | FF | Latch | MUX | ADD/SUB | MUL/DIV | XOR | AND/OR | NOT/BUF | COMPARE | MEM | Other |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| RTLLM v1.1 | 9.2% | 0.0% | 24.2% | 8.6% | 0.4% | 0.0% | 20.9% | 24.1% | 5.7% | 0.0% | 7.0% |
| RTLLM v2.0 | 4.5% | 0.0% | 9.4% | 4.2% | 0.3% | 8.8% | 26.2% | 35.3% | 2.6% | 0.5% | 8.1% |
| VerilogEval V2 (e0_t0) | 1.9% | 0.2% | 19.0% | 20.5% | 0.0% | 11.2% | 17.8% | 17.2% | 6.1% | 0.6% | 5.5% |
| VerilogEval V2 (e0_t8) | 0.4% | 0.0% | 40.5% | 44.8% | 0.0% | 1.6% | 2.6% | 2.6% | 6.4% | 0.1% | 1.1% |
| VerilogEval V2 (e1_t0) | 2.0% | 0.1% | 19.5% | 9.6% | 0.0% | 22.9% | 9.7% | 22.1% | 6.8% | 0.3% | 7.1% |
| VerilogEval V2 (e1_t8) | 2.0% | 0.2% | 19.3% | 9.4% | 0.0% | 22.9% | 9.8% | 22.1% | 7.3% | 0.2% | 6.7% |

## Phan bo bucket PyraNet (0-5/6-10/11-15/16+ cell), nhom comparable

| Benchmark | gen 0-5 | gen 6-10 | gen 11-15 | gen 16+ | ref 0-5 | ref 6-10 | ref 11-15 | ref 16+ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| RTLLM v1.1 | 11% | 21% | 11% | 57% | 7% | 7% | 11% | 75% |
| RTLLM v2.0 | 18% | 30% | 9% | 42% | 12% | 21% | 12% | 55% |
| VerilogEval V2 (e0_t0) | 53% | 22% | 5% | 20% | 61% | 27% | 7% | 5% |
| VerilogEval V2 (e0_t8) | 53% | 22% | 4% | 21% | 61% | 27% | 5% | 7% |
| VerilogEval V2 (e1_t0) | 48% | 21% | 7% | 24% | 56% | 27% | 8% | 10% |
| VerilogEval V2 (e1_t8) | 48% | 22% | 6% | 24% | 56% | 28% | 8% | 8% |

*Tham khao: kich thuoc 4 tap train PyraNet (train_index2_*.npy): 0-5=198,241 mau; 6-10=85,033; 11-15=27,394-38,138; 16+=5,225 (lech manh ve mach nho).*

## Chi tiet — RTLLM v2.0

**Module co ratio > 1.5** (mac dinh gom ca > 2.0):
- `adder_pipe_64bit`: 2.590x (>2.0)

## Chi tiet — VerilogEval V2 (e0_t0)

**Module co ratio > 1.5** (mac dinh gom ca > 2.0):
- `Prob092_gatesv100`: 49.833x (>2.0)
- `Prob101_circuit4`: 28.500x (>2.0)
- `Prob043_vector5`: 17.000x (>2.0)
- `Prob083_mt2015_q4b`: 9.000x (>2.0)
- `Prob054_edgedetect`: 6.500x (>2.0)
- `Prob084_ece241_2013_q12`: 6.500x (>2.0)
- `Prob016_m2014_q4j`: 6.000x (>2.0)
- `Prob064_vector3`: 5.000x (>2.0)
- `Prob071_always_casez`: 4.111x (>2.0)
- `Prob025_reduction`: 4.000x (>2.0)
- `Prob059_wire4`: 4.000x (>2.0)
- `Prob112_always_case2`: 3.667x (>2.0)
- `Prob050_kmap1`: 3.333x (>2.0)
- `Prob027_fadd`: 2.667x (>2.0)
- `Prob072_thermostat`: 2.500x (>2.0)
- `Prob100_fsm3comb`: 2.250x (>2.0)
- `Prob110_fsm2`: 2.125x (>2.0)
- `Prob088_ece241_2014_q5b`: 2.091x (>2.0)
- `Prob009_popcount3`: 2.000x
- `Prob015_vector1`: 2.000x
- `Prob024_hadd`: 2.000x
- `Prob032_vector0`: 2.000x
- `Prob051_gates4`: 2.000x
- `Prob109_fsm1`: 2.000x
- `Prob056_ece241_2013_q7`: 1.667x
- `Prob065_7420`: 1.667x
- `Prob079_fsm3onehot`: 1.600x

**Module phat sinh latch trong code sinh ra:**
- `Prob028_m2014_q4a`
- `Prob083_mt2015_q4b`

## Chi tiet — VerilogEval V2 (e0_t8)

**Module co ratio > 1.5** (mac dinh gom ca > 2.0):
- `Prob092_gatesv100`: 49.833x (>2.0)
- `Prob101_circuit4`: 28.500x (>2.0)
- `Prob043_vector5`: 17.000x (>2.0)
- `Prob045_edgedetect2`: 16.667x (>2.0)
- `Prob083_mt2015_q4b`: 9.000x (>2.0)
- `Prob054_edgedetect`: 6.500x (>2.0)
- `Prob084_ece241_2013_q12`: 6.500x (>2.0)
- `Prob016_m2014_q4j`: 6.000x (>2.0)
- `Prob112_always_case2`: 5.667x (>2.0)
- `Prob064_vector3`: 5.000x (>2.0)
- `Prob071_always_casez`: 4.111x (>2.0)
- `Prob025_reduction`: 4.000x (>2.0)
- `Prob059_wire4`: 4.000x (>2.0)
- `Prob144_conwaylife`: 3.446x (>2.0)
- `Prob050_kmap1`: 3.333x (>2.0)
- `Prob027_fadd`: 2.667x (>2.0)
- `Prob072_thermostat`: 2.500x (>2.0)
- `Prob100_fsm3comb`: 2.250x (>2.0)
- `Prob009_popcount3`: 2.000x
- `Prob015_vector1`: 2.000x
- `Prob024_hadd`: 2.000x
- `Prob032_vector0`: 2.000x
- `Prob051_gates4`: 2.000x
- `Prob088_ece241_2014_q5b`: 2.000x
- `Prob109_fsm1`: 2.000x
- `Prob119_fsm3`: 1.786x
- `Prob065_7420`: 1.667x
- `Prob074_ece241_2014_q4`: 1.667x

**Module phat sinh latch trong code sinh ra:**
- `Prob028_m2014_q4a`
- `Prob083_mt2015_q4b`

## Chi tiet — VerilogEval V2 (e1_t0)

**Module co ratio > 1.5** (mac dinh gom ca > 2.0):
- `Prob108_rule90`: 170.667x (>2.0)
- `Prob092_gatesv100`: 99.333x (>2.0)
- `Prob043_vector5`: 25.000x (>2.0)
- `Prob103_circuit2`: 19.400x (>2.0)
- `Prob006_vectorr`: 8.000x (>2.0)
- `Prob054_edgedetect`: 6.750x (>2.0)
- `Prob131_mt2015_q4`: 5.000x (>2.0)
- `Prob004_vector2`: 4.000x (>2.0)
- `Prob059_wire4`: 4.000x (>2.0)
- `Prob094_gatesv`: 3.333x (>2.0)
- `Prob109_fsm1`: 3.250x (>2.0)
- `Prob063_review2015_shiftcount`: 3.200x (>2.0)
- `Prob055_conditional`: 3.143x (>2.0)
- `Prob009_popcount3`: 3.000x (>2.0)
- `Prob101_circuit4`: 2.500x (>2.0)
- `Prob136_m2014_q6`: 2.500x (>2.0)
- `Prob045_edgedetect2`: 2.333x (>2.0)
- `Prob100_fsm3comb`: 2.250x (>2.0)
- `Prob084_ece241_2013_q12`: 2.167x (>2.0)
- `Prob107_fsm1s`: 2.125x (>2.0)
- `Prob110_fsm2`: 2.125x (>2.0)
- `Prob111_fsm2s`: 2.125x (>2.0)
- `Prob015_vector1`: 2.000x
- `Prob024_hadd`: 2.000x
- `Prob032_vector0`: 2.000x
- `Prob034_dff8`: 2.000x
- `Prob030_popcount255`: 1.992x
- `Prob088_ece241_2014_q5b`: 1.909x
- `Prob121_2014_q3bfsm`: 1.833x
- `Prob081_7458`: 1.750x
- `Prob127_lemmings1`: 1.700x
- `Prob142_lemmings2`: 1.682x
- `Prob065_7420`: 1.667x
- `Prob112_always_case2`: 1.667x

**Module phat sinh latch trong code sinh ra:**
- `Prob109_fsm1`
- `Prob121_2014_q3bfsm`

## Chi tiet — VerilogEval V2 (e1_t8)

**Module co ratio > 1.5** (mac dinh gom ca > 2.0):
- `Prob108_rule90`: 170.667x (>2.0)
- `Prob092_gatesv100`: 99.333x (>2.0)
- `Prob043_vector5`: 25.000x (>2.0)
- `Prob103_circuit2`: 19.400x (>2.0)
- `Prob006_vectorr`: 8.000x (>2.0)
- `Prob134_2014_q3c`: 7.444x (>2.0)
- `Prob054_edgedetect`: 6.750x (>2.0)
- `Prob131_mt2015_q4`: 5.000x (>2.0)
- `Prob004_vector2`: 4.000x (>2.0)
- `Prob059_wire4`: 4.000x (>2.0)
- `Prob094_gatesv`: 3.333x (>2.0)
- `Prob109_fsm1`: 3.250x (>2.0)
- `Prob055_conditional`: 3.143x (>2.0)
- `Prob009_popcount3`: 3.000x (>2.0)
- `Prob045_edgedetect2`: 2.333x (>2.0)
- `Prob100_fsm3comb`: 2.250x (>2.0)
- `Prob084_ece241_2013_q12`: 2.167x (>2.0)
- `Prob107_fsm1s`: 2.125x (>2.0)
- `Prob110_fsm2`: 2.125x (>2.0)
- `Prob111_fsm2s`: 2.125x (>2.0)
- `Prob015_vector1`: 2.000x
- `Prob024_hadd`: 2.000x
- `Prob032_vector0`: 2.000x
- `Prob034_dff8`: 2.000x
- `Prob083_mt2015_q4b`: 2.000x
- `Prob030_popcount255`: 1.992x
- `Prob088_ece241_2014_q5b`: 1.909x
- `Prob142_lemmings2`: 1.864x
- `Prob121_2014_q3bfsm`: 1.833x
- `Prob081_7458`: 1.750x
- `Prob127_lemmings1`: 1.700x
- `Prob065_7420`: 1.667x
- `Prob112_always_case2`: 1.667x

**Module phat sinh latch trong code sinh ra:**
- `Prob109_fsm1`
- `Prob121_2014_q3bfsm`
- `Prob134_2014_q3c`
