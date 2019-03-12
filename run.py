#!/usr/bin/python3
import os
import argparse
import sys
import json
import uuid
from subprocess import Popen


# Check whether given config is valid
def checkLLVMConfigForClone(js):
  # Destination of src should exist
  assert ("src" in js)
  # Should have cloninig repo info
  assert ("repo" in js)
  # LLVM repo should exist
  assert ("llvm" in js["repo"])
  # For each repo, url should exist
  for i in js["repo"]:
    assert ("url" in js["repo"][i])

def checkLLVMConfigForBuild(js, buildopt):
  # Destination of src should exist
  assert ("src" in js)
  # Should have build options
  assert ("builds" in js)
  found = False
  for i in js["builds"]:
    if i["type"] == buildopt:
      assert ("path" in i)
      assert ("sharedlib" in i)
      found = True
  assert(found)

def checkLNTConfigForClone(js):
  # Destination of lnt/test-suite/virtualenv should exist
  assert ("lnt-dir" in js)
  assert ("test-suite-dir" in js)
  assert ("virtualenv-dir" in js)
  # Should have cloninig repo info
  assert ("repo" in js)
  # LLVM repo should exist
  assert ("lnt" in js["repo"])
  assert ("test-suite" in js["repo"])
  for i in js["repo"]:
    assert ("url" in js["repo"][i])


# Starts git clone.
# branch can be None.
# depth can be None or -1 (meaning that it is infinite)
def startGitClone(repo, dest, branch, depth):
  try:
    os.makedirs(dest)
    cmds = ["git", "clone", repo, dest]
    if branch != None:
      cmds = cmds + ["--branch", branch]
    if depth != None and depth != -1:
      cmds = cmds + ["--depth", str(depth)]

    p = Popen(cmds)
    assert(p != None)
    return p
  except OSError as e:
    print ("Cannot create directory '{0}'.".format(dest))
    exit(1)



# Main object.
class LLVMScript(object):

  def __init__(self):
    parser = argparse.ArgumentParser(
      usage = '''python3 run.py <command> [<args>]

Commands:
  clone     Clone LLVM into local
  build     Build LLVM
  testsuite Clone & initialize test-suite and lnt
  run       Run test-suite (using cmake)

Type 'python3 run.py <command> help' to get details
''')

    parser.add_argument('command', help='clone/build/lntclone/spec2017')
    args = parser.parse_args(sys.argv[1:2])
    if not hasattr(self, args.command):
      print ("Unrecognized command")
      parser.print_help()
      exit(1)
    getattr(self, args.command)()


  def _getBuildOption(self, cfg, build):
    options = None
    for i in cfg["builds"]:
      if i["type"] == build:
        options = i
        break

    assert(options != None)
    return options


  def clone(self):
    parser = argparse.ArgumentParser(
        description = 'Arguments for clone command')
    parser.add_argument('--cfg', help='config path for LLVM (json file)', action='store',
        required=True)
    parser.add_argument('--depth', help='commit depth to clone (-1 means inf)', nargs='?', const=-1, type=int)
    args = parser.parse_args(sys.argv[2:])

    cfgpath = args.cfg
    f = open(cfgpath)
    cfg = json.load(f)
    checkLLVMConfigForClone(cfg)

    def _callGitClone (cfg, name):
      repo = cfg["repo"][name]["url"]
      dest = cfg["src"] + "/" + name
      branch = None
      depth = None

      if "branch" in cfg["repo"][name]:
        branch = cfg["repo"][name]["branch"]

      if args.depth:
        depth = args.depth

      return startGitClone(repo, dest, branch, depth)

    pipes = []
    pipes.append(_callGitClone(cfg, "llvm"))
    pipes.append(_callGitClone(cfg, "clang"))
    if "compiler-rt" in cfg["repo"]:
      pipes.append(_callGitClone(cfg, "compiler-rt"))
    for p in pipes:
      p.wait()


  def build(self):
    parser = argparse.ArgumentParser(
        description = 'Arguments for build command')
    parser.add_argument('--cfg', help='config path for LLVM (json file)', action='store',
        required=True)
    parser.add_argument('--build', help='release/relassert/debug', action='store', required=True)
    parser.add_argument('--core', help='# of cores to use', nargs='?', const=1, type=int)
    parser.add_argument('--target', help='targets, separated by comma (ex: opt,clang,llvm-as)',
                        action='store')
    args = parser.parse_args(sys.argv[2:])

    cfgpath = args.cfg
    f = open(cfgpath)
    cfg = json.load(f)
    
    if args.build != "release" and args.build != "relassert" and args.build != "debug":
      print ("Unknown build option: {}; should be release / relassert / debug.".format(args.build))
      exit(1)

    checkLLVMConfigForBuild(cfg, args.build)

    options = self._getBuildOption(cfg, args.build)

    if not os.path.exists(options["path"]):
      try:
        os.makedirs(options["path"])
      except OSError as e:
        print ("Cannot create directory '{0}'.".format(options["path"]))
        exit(1)

    os.chdir(options["path"])

    cmd = ["cmake", cfg["src"] + "/llvm"]
    if args.build == "release":
      cmd.append("-DCMAKE_BUILD_TYPE=Release")
    elif args.build == "relassert":
      cmd = cmd + ["-DCMAKE_BUILD_TYPE=Release", "-DLLVM_ENABLE_ASSERTIONS=On"]
    elif args.build == "debug":
      cmd.append("-DCMAKE_BUILD_TYPE=Debug")

    if options["sharedlib"]:
      cmd.append("-DBUILD_SHARED_LIBS=1")

    externals = []
    if "clang" in cfg["repo"]:
      externals = externals + ["clang"]
    if "compiler-rt" in cfg["repo"]:
      externals = externals + ["compiler-rt"]
    if len(external) != 0:
      cmd.append("-DLLVM_ENABLE_PROJECTS=\"%s\"" % ";".join(externals))

    p = Popen(cmd)
    p.wait()

    # Now build
    cmd = ["cmake", "--build", "."]
    addedArg = False
    
    if args.target:
      cmd = cmd + ["--"] + args.target.split(',')
      addedArg = True

    if args.core:
      cmd = cmd + ([] if addedArg else ["--"]) + ["-j{}".format(str(args.core))]
      addedArg = True

    p = Popen(cmd)
    p.wait()


  def lntclone(self):
    parser = argparse.ArgumentParser(
        description = 'Arguments for build command')
    parser.add_argument('--cfg',
        help='config path for LLVM Nightly Tests (json file)',
        action='store',
        required=True)
    args = parser.parse_args(sys.argv[2:])

    cfgpath = args.cfg
    f = open(cfgpath)
    cfg = json.load(f)
    checkLNTConfigForClone(cfg);

    def _callGitClone(cfg, name):
      repo = cfg["repo"][name]["url"]
      dest = cfg[name + "-dir"]
      branch = None

      if "branch" in cfg["repo"][name]:
        branch = cfg["repo"][name]["branch"]

      return startGitClone(repo, dest, branch, None)

    pipes = []
    pipes.append(_callGitClone(cfg, "lnt"))
    pipes.append(_callGitClone(cfg, "test-suite"))
    for p in pipes:
      p.wait()

    # Now, create virtualenv.
    venv_dir = cfg["virtualenv-dir"]
    p = Popen(["virtualenv2", venv_dir])
    p.wait()

    # Install LNT at virtualenv.
    p = Popen([venv_dir + "/bin/pip", "install", "six==1.10.0"])
    p.wait()
    p = Popen([venv_dir + "/bin/pip", "install", "typing"])
    p.wait()
    # Uses "install" option - the difference between "install" and "develop" is that
    # using "develop" allows the changes in the LNT sources to be immediately
    # propagated to the installed directory.
    p = Popen([venv_dir + "/bin/python", cfg["lnt-dir"] + "/setup.py", "install"])
    p.wait()


  def lnt(self):
    parser = argparse.ArgumentParser(
        description = 'Arguments for lnt command')
    parser.add_argument('--cfg', help='config path for LLVM (json file)', action='store',
        required=True)
    parser.add_argument('--lntcfg', help='config path for LNT (json file)', action='store',
        required=True)
    parser.add_argument('--runcfg', help='config path for LNT run (json file)', action='store',
        required=True)
    args = parser.parse_args(sys.argv[2:])

    cfg = json.load(open(args.cfg))
    lntcfg = json.load(open(args.lntcfg))
    runcfg = json.load(open(args.runcfg))

    buildopt = runcfg["buildopt"]
    assert(buildopt == "relassert" or buildopt == "release" or buildopt == "debug")
    clangdir = self._getBuildOption(cfg, buildopt)["path"]

    cmds = [lntcfg["virtualenv-dir"] + "/bin/lnt",
            "runtest",
            "nt",
            "--sandbox", lntcfg["virtualenv-dir"],
            "--cc", clangdir + "/bin/clang",
            "--cxx", clangdir + "/bin/clang++",
            "--test-suite", lntcfg["test-suite-dir"]]

    if runcfg["benchmark"] == True:
      if runcfg["threads"] != 1:
        print("Warning: benchmark is set, but --threads is not 1!")
      cmds = cmds + ["--benchmarking-only", "--use-perf", "time",
                     "--make-param", "\"RUNUNDER=taskset -c 1\""]
      cmds = cmds + ["--multisample", "5"]
    cmds = cmds + ["--threads", str(runcfg["threads"])]
    cmds = cmds + ["--build-threads", str(runcfg["build-threads"])]

    print(cmds)

    p = Popen(cmds)
    p.wait()

if __name__ == '__main__':
  LLVMScript()

# LLVM_EXTERNAL_{CLANG,LLD,POLLY}_SOURCE_DIR:PATH

