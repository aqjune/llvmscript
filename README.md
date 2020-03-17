# llvmscript

One-for-all python script for running experiment with LLVM

Recommended environment: Ubuntu

## Prerequisites

- `python3`: required for running this script
- `git`: required for cloning repos
- `cmake3`, `ninja`, `g++`: required for building repos

```
# Ubuntu:
apt update
apt install git cmake ninja-build g++
```

#### To run benchmarks (LNT, test-suite):

- `python3-pip`, `virtualenv2`, `python-dev`: required for initializing LNT
- `yacc`, `tclsh`: required for running LNT
- `perf`: if you want to use perf (`use_perf`)
- [cset](https://stackoverflow.com/questions/11111852/how-to-shield-a-cpu-from-the-linux-scheduler-prevent-it-scheduling-threads-onto): if you want to use cset (`use_cset`; currently not supported)
- [NOPASSWD for sudo](https://askubuntu.com/questions/147241/execute-sudo-without-password): if you want to use cset/ramdisk/dropcache.

```
# Ubuntu:
apt-get install bison tclsh python3 python3-pip cpuset linux-tools-common \
                linux-tools-generic
pip3 install --upgrade pip3
pip3 install virtualenv
```


## Commands for Initialization

Type `python3 run.py` to see available options.

Clone LLVM:
```
python3 run.py clone --cfg examples/llvm.json
```

Build LLVM:
```
python3 run.py build --cfg examples/llvm.json --type <release/relassert/debug> --core <# of cores to use>
```


## Commands for Performance Test

Clone & initialize LLVM Nightly Tests and test-suite:
```
python3 run.py initlnt --cfg examples/testsuite.json
```

Run test-suite with `cmake`:
```
python3 run.py testsuite --cfg examples/llvm.json --testcfg examples/testsuite.json --runcfg examples/run.json
```

Run test-suite with LLVM Nightly Tests script:
```
python3 run.py lnt --cfg examples/llvm.json --testcfg examples/testsuite.json --runcfg examples/run.json
```

Run SPEC CINT2017rate:
```
python3 run.py spec --cfg examples/llvm.json --testcfg examples/testsuite.json --runcfg examples/run-spec.json --speccfg examples/spec.json --testsuite --runonly CINT2017rate
# CINT2017rate, CFP2017rate, CINT2017speed, CFP2017speed
```

Compare the results:
```
# testsuite-result-1/ : contains result1.json, .. resultN.json for the first LLVM
# testsuite-result-2/ : contains json files for the second LLVM
python3 run.py compare --dir1 testsuite-result-1/ --dir2 testsuite-result-2/ --out table.csv --comparecfg examples/compare.json
```

## Commands for Analyzing Experimental Results

Compile test-suite with llvm and llvm2, compares assembly outputs, prints the results (one assembly file per one line) to result.txt
```
python3 run.py diff --cfg examples/llvm.json --cfg2 examples/llvm2.json --testcfg examples/testsuite.json --runcfg examples/run-emitasm.json --out diff.txt
```

Filter the result from `run.py testsuite` or `run.py spec` so it only contains tests that are different in assembly
```
python3 run.py filter --json results1.json --diff diff.txt --out results1.filtered.json
```

Count the number of IR instructions in a directory and prints it as a json format
```
python3 run.py instcount --cfg examples/llvm.json --dir <test-suite compiled with run-emitbc.json> --out result.json
```
