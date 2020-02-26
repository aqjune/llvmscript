# llvmscript

One-for-all python script for running experiment with LLVM

Recommended environment: Ubuntu

# Prerequisites

- `git`: required for cloning repos
- `cmake3`, `ninja`, `g++`: required for building repos
- `virtualenv2`, `python-dev`: required for initializing LLVM Nightly Tests
- [NOPASSWD for sudo](https://askubuntu.com/questions/147241/execute-sudo-without-password): if you want to use cset/ramdisk/dropcache.
- [cset](https://stackoverflow.com/questions/11111852/how-to-shield-a-cpu-from-the-linux-scheduler-prevent-it-scheduling-threads-onto): if you want to use cset.


# Commands for Initialization

Type `python3 run.py` to see available options.

Clone LLVM:
```
python3 run.py clone --cfg examples/llvm.json
```

Build LLVM:
```
python3 run.py build --cfg examples/llvm.json --type <release/relassert/debug> --core <# of cores to use>
```

Clone & initialize LLVM Nightly Tests and test-suite:
```
python3 run.py testsuite --cfg examples/testsuite.json
```


# Commands for Performance Test

Run test-suite with `cmake`:
```
python3 run.py test --cfg examples/llvm.json --testcfg examples/testsuite.json --runcfg examples/run.json
```

(WIP) Run Test Suite with LLVM Nightly Tests script:
```
python3 run.py lnt --cfg examples/llvm.json --testcfg examples/testsuite.json --runcfg examples/run.json
```

Run SPEC CINT2017rate using test-suite:
```
python3 run.py spec --cfg examples/llvm.json --testcfg examples/testsuite.json --runcfg examples/run.json --speccfg examples/spec.json --testsuite --runonly CINT2017rate
```


# Commands for Analyzing Experimental Results

Compile test-suite with llvm and llvm2, compares assembly outputs, prints the results (one assembly file per one line) to result.txt
```
python3 run.py diff --cfg examples/llvm.json --cfg2 examples/llvm2.json --testcfg examples/testsuite.json --runcfg examples/run-emitasm.json --out result.txt
```

Count the number of IR instructions in a directory and prints it as a json format
```
python3 run.py instcount --cfg examples/llvm.json --dir <test-suite compiled with run-emitbc.json> --out result.json
```
