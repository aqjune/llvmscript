# llvmscript

One-for-all python script for running LLVM experiment.

Recommended environment: Ubuntu

## Clone & Build LLVM

### 1. Prerequisites

- `python3`, `python3-distutils`: required for running this script
- `git`: required for cloning repos
- `cmake3`, `ninja`, `g++`: required for building repos
- `zlib1g-dev`, `libtinfo-dev`, `libxml2-dev`: linker requires it sometimes

```
# Ubuntu:
apt update
apt install git cmake ninja-build g++ python3-distutils zlib1g-dev libtinfo-dev libxml2-dev

# macOS on apple silicon chips (M1, ...):
brew install git cmake ninja gcc python3 zlib libxml2
xcode-select --install
export LIBRARY_PATH="$LIBRARY_PATH:/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/usr/lib"
```

### 2. Clone & Build

Type `python3 run.py` to see available options.

**Clone LLVM**
```
# Please edit "src" attribute at examples/llvm.json to specify where to clone LLVM project
python3 run.py clone --cfg examples/llvm.json
```

**Build LLVM**
```
# release: fast build, has no debug info
# debug: slow build, large binaries; can debug clang with gdb/lldb
# relassert: fast build, enables assertion checks
# NOTE: if it aborts due to insufficient memory space, please re-try with
#       smaller number of cores (it will restart compiling from the last status)
python3 run.py build --cfg examples/llvm.json --type <release/relassert/debug> --core <# of cores to use>
```

This will create binaries at the `path/bin` where `path` is the attribute at `llvm.json`.

Please check whether the binaries work well, e.g. by running `bin/opt` and `bin/clang`.

#### Trouble-shootings

- If `run.py build` prints `Target clang_rt.builtins_x86_64_osx does not exist`, remove `compiler-rt` from `llvm.json` and retry the command.

- If you are using Mac and the built `clang` cannot find C standard header files such as `stdio.h`, please specify `-isysroot <SDK dir>` when using it (e.g. `clang -isysroot  /Library/Developer/CommandLineTools/SDKs/MacOSX.sdk a.c` or `-isysroot /Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX10.15.sdk`).


## Performance Evaluation

### 1. Prerequisites

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

# Manjaro:
pacman -Sy tcl python-pip
```

To use perf, check whether the value of `/proc/sys/kernel/perf_event_paranoid` is 0 or -1.
If it is higher than 0, update `/etc/sysctl.conf` by adding `kernel.perf_event_paranoid=-1`.

### 2. Clone & Run TestSuite

**Clone & Initialize LLVM Nightly Tests and TestSuite**
```
python3 run.py initlnt --cfg examples/testsuite.json
```

**Run TestSuite**
```
python3 run.py testsuite --cfg examples/llvm.json --testcfg examples/testsuite.json --runcfg examples/run.json
```

If you see `fatal error: 'sys/sysctl.h'`, please follow the solution described at https://bugs.llvm.org/show_bug.cgi?id=48568 .

**Run TestSuite with LLVM Nightly Tests script**
```
python3 run.py lnt --cfg examples/llvm.json --testcfg examples/testsuite.json --runcfg examples/run.json
```

**Run SPEC CINT2017rate**
```
python3 run.py spec --cfg examples/llvm.json --testcfg examples/testsuite.json --runcfg examples/run-spec.json --speccfg examples/spec.json --testsuite --runonly CINT2017rate
# CINT2017rate, CFP2017rate, CINT2017speed, CFP2017speed ; one dir only
```

**Compare the results**
```
# testsuite-result-1/ : contains result1.json, .. resultN.json for the first LLVM
# testsuite-result-2/ : contains json files for the second LLVM
python3 run.py compare --dir1 testsuite-result-1/ --dir2 testsuite-result-2/ --out table.csv --comparecfg examples/compare.json
```

A handy tool: `diffutil.py asm <dir1> <dir2> --out difflist.txt`

### 3. Commands for Analyzing Experimental Results

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
