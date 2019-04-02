# llvmscript

One-for-all python script for running experiment with LLVM

WIP; don't use this.

Preferred environment: Linux

# Prerequisites

- `git`: required to clone repos
- `virtualenv2`: required when initializing LLVM Nightly Tests
- cset: required if `use_cset` is enabled. [NOPASSWD for sudo](https://askubuntu.com/questions/147241/execute-sudo-without-password) should be set as well


# Commands

Type `python3 run.py` to see available options.


`python3 run.py clone --cfg examples/llvm.json`

- Clones LLVM (as well as Clang and other projects, if mentioned in the config file)


`python3 run.py build --cfg examples/llvm.json --build <release/relassert/debug> --core <# of cores to use>`

- Builds LLVM (as well as Clang and other projects)


`python3 run.py testsuite --cfg examples/testsuite.json`

- Clones & initializes LLVM Nightly Tests


`python3 run.py test --cfg examples/llvm.json --testcfg examples/testsuite.json --runcfg examples/run.json`

- Runs Test Suite with `cmake` command


`python3 run.py lnt --cfg examples/llvm.json --testcfg examples/testsuite.json --runcfg examples/run.json`

- Runs Test Suite with LLVM Nightly Tests script


`python3 run.py spec --cfg examples/llvm.json --testcfg examples/testsuite.json --runcfg examples/run.json --speccfg examples/spec.json --testsuite --runonly CINT2017rate`

- Runs SPEC CINT2017rate using tools contained in Test Suite
