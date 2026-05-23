import subprocess
import os

work_dir = "/home/nntkim/GNU_COMBA/VE_testbench/langgraph/.build_sample_e1_t0/samples/Prob013_m2014_q4e/work_01"
binary_out = "TopModule.vvp"

r2 = subprocess.run(
    ["vvp", binary_out], cwd=work_dir,
    capture_output=True, text=True, timeout=120,
)
print("Returncode:", r2.returncode)
print("Stdout:", repr(r2.stdout))
print("Stderr:", repr(r2.stderr))
