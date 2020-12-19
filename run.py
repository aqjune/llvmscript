#!/usr/bin/python3
import argparse
import csv
import datetime
import glob
import json
import multiprocessing
import os
import random
import re
import shutil
import smtplib
import socket
import stat
import string
import subprocess
import sys
import uuid
from subprocess import Popen


errmsg = lambda attrname, filename: "Attribute %s does not exist%s" % \
    (attrname, " in file %s" % filename if filename else "")

# Check whether given config is valid
def checkLLVMConfigForClone(js, filename=None):
  assert ("src" in js), errmsg("src", filename)
  assert ("repo" in js), errmsg("repo", filename)
  assert ("branch" in js), errmsg("branch", filename)

def checkLLVMConfigForBuild(js, buildopt,
                            filename=None):
  assert ("src" in js), errmsg("src", filename)
  assert ("builds" in js), errmsg("builds", filename)
  assert (buildopt in js["builds"]), errmsg("builds/%s" % buildopt, filename)
  assert ("path" in js["builds"][buildopt]), errmsg("builds/%s/path" % buildopt, filename)
  assert ("projects" in js["builds"][buildopt]), errmsg("builds/%s/projects" % buildopt, filename)

def checkLNTConfigForClone(js, filename=None):
  assert ("lnt-dir" in js), errmsg("lnt-dir", filename)
  assert ("test-suite-dir" in js), errmsg("test-suite-dir", filename)
  assert ("virtualenv-dir" in js), errmsg("virtualenv-dir", filename)
  for i in ["lnt", "test-suite"]:
    assert (i in js), errmsg(i, filename)
    assert ("url" in js[i]), errmsg("%s/url" % i, filename)

def checkRunConfig(js, filename=None):
  assert ("buildopt" in js), errmsg("buildopt", filename)
  assert (js["buildopt"] in ["debug", "release", "relassert"]), \
      "Unknown build option: %s%s" % \
        (js["buildopt"], " in file %s" % filename if filename else "")



def newParser(cmd, desc=None, llvm=False, llvm2=False, testsuite=False, run=False,
              spec=False, sendmail=False, optionals=[]):
  if desc == None:
    desc = 'Arguments for %s command' % cmd
  parser = argparse.ArgumentParser(description = desc)

  multi_cfg = False
  if len(list(filter((lambda x: x), [llvm, testsuite, run, spec]))) > 1:
    multi_cfg = True

  if llvm:
    parser.add_argument('--cfg', help='config path for LLVM (json file)',
        action='store', required="llvm" not in optionals)

  if llvm2:
    assert(llvm)
    parser.add_argument('--cfg2', help='config path for LLVM (json file)',
        action='store', required="llvm2" not in optionals)

  if testsuite:
    parser.add_argument('--' + ("test" if multi_cfg else "") + 'cfg',
        help='config path for test-suite (json file)', action='store',
        required="testsuite" not in optionals)

  if run:
    parser.add_argument('--' + ("run" if multi_cfg else "") + 'cfg',
        help='config path for run (json file)', action='store',
        required="run" not in optionals)

  if spec:
    parser.add_argument('--' + ("spec" if multi_cfg else "") + "cfg",
        help='config path for SPEC (json file)', action='store',
        required="spec" not in optionals)

  if sendmail:
    parser.add_argument("--mailcfg", help="Mail notification config",
        action="store", required="sendmail" not in optionals)

  return parser


def hasAndEquals(d, key, val):
  return key in d and d[key] == val


# Starts git clone.
# branch can be None.
# depth can be None or -1 (meaning that it is infinite)
def startGitClone(repo, dest, branch, depth):
  try:
    print("repo: " + repo)
    print("dest: " + dest)
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

# Send a mail.
def sendMail(mailcfg, title, contents):
  efrom = mailcfg["from"]
  frompasswd = mailcfg["frompasswd"]
  eto = mailcfg["to"]
  machinename = socket.gethostname()
  title = "[llvmscript, %s] %s" % (machinename, title)

  email_text = """\
From: %s
To: %s
Subject: %s

%s
""" % (efrom, eto, title, contents)

  try:
    server = smtplib.SMTP('smtp.gmail.com:587')
    server.ehlo()
    server.starttls()
    server.login(efrom, frompasswd)

    server.sendmail(efrom, eto, email_text)
    server.close()
  except Exception as e:
    print(e)

def runAsSudo(cmd):
  if isinstance(cmd, str):
    p = Popen(["sudo", "-S", "sh", "-c", cmd])
    p.wait()
  else:
    p = Popen(["sudo", "-S"] + cmd)
    p.wait()
  return p.returncode

def dropCache():
  runAsSudo("echo 1 > /proc/sys/vm/drop_caches")
  runAsSudo("echo 2 > /proc/sys/vm/drop_caches")
  runAsSudo("echo 3 > /proc/sys/vm/drop_caches")

def initCSet():
  print("Unsupported feature: use_cset")
  exit(1)
  #runAsSudo("cset shield --reset")
  #runAsSudo("cset shield -c 0 -k on")

def setScalingGovernor():
  for p in glob.glob("/sys/devices/system/cpu/cpu*/cpufreq/"):
    f = p + "scaling_governor"
    runAsSudo("echo performance > %s" % f)

def checkPerf():
  p = Popen(["perf", "stat", "echo", "hi"])
  p.wait()
  if p.returncode != 0:
    print("Cannot run perf!")
    exit(1)

def asmHasDiff(asmpath1, asmpath2):
  prune = lambda s: (s if s.find("#") == -1 else s[s.find("#"):]).strip()

  asm1 = open(asmpath1, "r").readlines()
  asm2 = open(asmpath2, "r").readlines()

  hasdiff = False
  if len(asm1) != len(asm2):
    hasdiff = True
  else:
    for i in range(0, len(asm1)):
      a1 = prune(asm1[i])
      a2 = prune(asm2[i])

      if a1 == a2:
        continue
      elif a1.startswith(".ident") and a2.startswith(".ident"):
        pattern = '.ident\s*\"clang version [0-9]+.[0-9].[0-9] \(((git\@github.com)|(https:\/\/github.com))[a-zA-Z0-9\)\( :/.-]*'
        if re.match(pattern, a1) or re.match(pattern, a2):
          continue
        else:
          hasdiff = True
          break
      else:
        hasdiff = True
        break
  return hasdiff

def llHasDiff(llpath1, llpath2):
  ll1 = open(llpath1, "r").readlines()
  ll2 = open(llpath2, "r").readlines()

  hasdiff = False
  if len(ll1) != len(ll2):
    hasdiff = True
  else:
    for i in range(1, len(ll1)):
      a = ll1[i].strip()
      b = ll2[i].strip()
      if a != b:
        # !1 = !{!"clang version 11.0.0 (git@github.com:aqjune/llvm-project-nonnull.git 13db7490fa67e22605dec4ab824121230b0fd928)"}
        pat = '\![0-9]+\s*=\s*\!\{\!\"clang version [0-9]+.[0-9].[0-9] \(((git\@github.com)|(https:\/\/github.com))[a-zA-Z0-9\)\( :/.-]*\"\}'
        if re.match(pat, a) or re.match(pat, b):
          continue
        hasdiff = True
        break
  return hasdiff


def readJsonResults(path, key):
  res = dict()
  for fs in os.listdir(path):
    if not fs.endswith(".json"):
      continue
    js = json.load(open(os.path.join(path, fs)))

    if "tests" in js:
      # test-suite was run with cmake
      for t in js["tests"]:
        if key not in t["metrics"]:
          continue
        n = t["name"]
        v = t["metrics"][key]

        if n not in res:
          res[n] = [v]
        else:
          res[n].append(v)
    else:
      for t in js["Tests"]:
        # test-suite was run with lnt script
        assert "Name" in t
        assert "Data" in t
        if key == "size":
          assert False, "Unsupported key"

        n = t["Name"]
        if not n.endswith(".exec"):
          continue
        n = n[:-len(".exec")]
        assert len(t["Data"]) == 1
        if n not in res:
          res[n] = [t["Data"][0]]
        else:
          res[n].append(t["Data"][0])
  return res


def readRunningTimes(path):
  return readJsonResults(path, "exec_time")

def readObjSizes(path):
  return readJsonResults(path, "size")


# Main object.
class LLVMScript(object):

  def __init__(self):
    parser = argparse.ArgumentParser(
      usage = '''python3 run.py <command> [<args>]

Commands:
  clone     Clone LLVM
  build     Build LLVM
  initlnt   Clone & initialize test-suite and lnt
  test      Run LIT tests
  testsuite Run test-suite using cmake
  lnt       Run test-suite using lnt
  spec      Run SPEC benchmark
  diff      Compile test-suite with different clangs and compare assembly files
  compare   Compare performance results of test-suite
  instcount Get statistics of the number of LLVM assembly instructions
  filter    Filter test-suite result with assembly diff
  check     Check wellformedness of config files
  mailtest  Test the mail account

Type 'python3 run.py <command> help' to get details
''')

    parser.add_argument('command', help='')
    args = parser.parse_args(sys.argv[1:2])
    if not hasattr(self, args.command):
      print ("Unrecognized command")
      parser.print_help()
      exit(1)
    getattr(self, args.command)()



  ############################################################
  #                       clone llvm
  ############################################################
  def clone(self):
    parser = newParser("clone", desc="Clones LLVM from Git", llvm=True,
                       sendmail=True, optionals=["sendmail"])
    parser.add_argument('--depth', help='commit depth to clone (-1 means inf)',
                        nargs='?', const=-1, type=int)
    args = parser.parse_args(sys.argv[2:])

    cfgpath = args.cfg
    f = open(cfgpath)
    cfg = json.load(f)
    checkLLVMConfigForClone(cfg)

    abssrc = os.path.abspath(cfg["src"])

    def _callGitClone (cfg):
      repo = cfg["repo"]
      branch = cfg["branch"]
      dest = abssrc
      depth = None

      if args.depth:
        depth = args.depth

      if os.path.isdir(dest):
        cmds = ["git", "remote", "get-url", "origin"]
        p = Popen(cmds, cwd=dest, stdout=subprocess.PIPE)
        out, err = p.communicate()
        out = out.decode("utf-8").strip()
        if out != repo:
          print("Directory %s already exists and it has unknown remote: %s" %
                (dest, out))
          exit(1)

        cmds = ["git", "branch", "--no-color"]
        p = Popen(cmds, cwd=dest, stdout=subprocess.PIPE)
        out, err = p.communicate()
        lines = [s.strip() for s in out.decode("utf-8").strip().split("\n")]
        curbranch = None
        for b in lines:
          if b.startswith("* "):
            curbranch = b[len(" *"):]
        if curbranch != branch:
          print("Directory %s already exists and it has unknown branch: %s" %
                (dest, curbranch))
          exit(1)

        # Fetch the branch
        Popen(["git", "fetch", "origin"], cwd=dest,
              stdout=subprocess.PIPE, stderr=subprocess.PIPE).wait()
        return Popen(["git", "reset", "--hard", "origin/%s" % branch], cwd=dest)

      return startGitClone(repo, dest, branch, depth)

    p = _callGitClone(cfg)
    p.wait()

    if args.mailcfg:
      cfg = json.load(open(args.mailcfg, "r"))
      sendMail(cfg, "clone", str(args))



  ############################################################
  #                      build llvm
  ############################################################
  def build(self):
    parser = newParser("build", desc="Builds LLVM from a cloned repo",
                       llvm=True, sendmail=True, optionals=["sendmail"])
    parser.add_argument('--type', help='release/relassert/debug', action='store', required=True)
    parser.add_argument('--core', help='# of cores to use', nargs='?', const=1, type=int)
    parser.add_argument('--target', help='targets, separated by comma (ex: opt,clang,llvm-as)',
                        action='store')
    args = parser.parse_args(sys.argv[2:])

    cfgpath = args.cfg
    f = open(cfgpath)
    cfg = json.load(f)

    if args.type != "release" and args.type != "relassert" and args.type != "debug":
      print ("Unknown build option: {}; should be release / relassert / debug.".format(args.type))
      exit(1)

    checkLLVMConfigForBuild(cfg, args.type)

    options = cfg["builds"][args.type]
    prevpath = os.getcwd()

    abspath = os.path.abspath(options["path"])
    if not os.path.exists(abspath):
      try:
        os.makedirs(abspath)
      except OSError as e:
        print ("Cannot create directory '{0}'.".format(options["path"]))
        exit(1)

    cmd = ["cmake", "-GNinja", os.path.join(os.path.abspath(cfg["src"]), "llvm")]
    os.chdir(abspath)

    if args.type == "release":
      cmd.append("-DCMAKE_BUILD_TYPE=Release")
    elif args.type == "relassert":
      cmd = cmd + ["-DCMAKE_BUILD_TYPE=Release", "-DLLVM_ENABLE_ASSERTIONS=On"]
    elif args.type == "debug":
      cmd.append("-DCMAKE_BUILD_TYPE=Debug")

    if hasAndEquals(options, "sharedlib", True):
      cmd.append("-DBUILD_SHARED_LIBS=1")

    if hasAndEquals(options, "rtti", True):
      cmd.append("-DLLVM_ENABLE_RTTI=ON")

    if hasAndEquals(options, "eh", True):
      cmd.append("-DLLVM_ENABLE_EH=ON")

    if hasAndEquals(options, "bindings", True):
      cmd.append("-DLLVM_ENABLE_BINDINGS=ON")
    else:
      cmd.append("-DLLVM_ENABLE_BINDINGS=OFF")

    if hasAndEquals(options, "z3", True):
      cmd.append("-DLLVM_ENABLE_Z3_SOLVER=ON")
    else:
      cmd.append("-DLLVM_ENABLE_Z3_SOLVER=OFF")

    projs = cfg["builds"][args.type]["projects"].split(";")
    if hasAndEquals(options, "use-lld", True):
      assert("lld" in projs), "lld should be listed at projects"
      cmd.append("-DCLANG_DEFAULT_LINKER=lld")

    cmd.append("-DLLVM_ENABLE_PROJECTS=%s" % ";".join(projs))
    if "clang-tools-extra" in projs:
      cmd.append("-DLLVM_TOOL_CLANG_TOOLS_EXTRA_BUILD=On")
      #cmd.append("-DCLANGD_BUILD_XPC=Off") # clangd 8.0 does not compile

    p = Popen(cmd)
    p.wait()

    # Now build
    buildarg = []
    corecnt = multiprocessing.cpu_count()

    if args.target:
      buildarg = args.target.split(',')

    if args.core:
      corecnt = args.core

    cmd = ["ninja", "-j%d" % corecnt] + buildarg

    p = Popen(cmd)
    p.wait()

    if args.mailcfg:
      os.chdir(prevpath)
      cfg = json.load(open(args.mailcfg, "r"))
      sendMail(cfg, "build", str(args))



  ############################################################
  #              clone test-suite and lnt
  ############################################################
  def initlnt(self):
    parser = newParser("initlnt", desc="Clone & initialize LLVM Nightly Tests and test-suite",
                       testsuite=True, sendmail=True, optionals=["sendmail"])
    args = parser.parse_args(sys.argv[2:])

    cfgpath = args.cfg
    f = open(cfgpath)
    cfg = json.load(f)
    checkLNTConfigForClone(cfg);

    def _callGitClone(cfg, name):
      repo = cfg[name]["url"]
      dest = cfg[name + "-dir"]
      branch = None

      if "branch" in cfg[name]:
        branch = cfg[name]["branch"]

      return startGitClone(repo, dest, branch, None)

    pipes = []
    pipes.append(_callGitClone(cfg, "lnt"))
    pipes.append(_callGitClone(cfg, "test-suite"))
    for p in pipes:
      p.wait()

    # Now, create virtualenv.
    venv_dir = cfg["virtualenv-dir"]
    p = Popen(["virtualenv", "-p", "python3", venv_dir])
    p.wait()

    # Install LNT at virtualenv.
    p = Popen([venv_dir + "/bin/pip", "install", "six==1.10.0"])
    p.wait()
    p = Popen([venv_dir + "/bin/pip", "install", "typing"])
    p.wait()
    p = Popen([venv_dir + "/bin/pip", "install", "pandas"])
    p.wait()
    # Uses "install" option - the difference between "install" and "develop" is that
    # using "develop" allows the changes in the LNT sources to be immediately
    # propagated to the installed directory.
    p = Popen([venv_dir + "/bin/python", cfg["lnt-dir"] + "/setup.py", "install"])
    p.wait()

    if args.mailcfg:
      cfg = json.load(open(args.mailcfg, "r"))
      sendMail(cfg, "testsuite", str(args))


  ############################################################
  #                Run LLVM's LIT tests
  ############################################################
  def test(self):
    parser = newParser("test", desc="Run LIT tests", llvm=True)
    parser.add_argument('--type', help='release/relassert/debug', action='store', required=True)
    parser.add_argument('--core', help='# of cores to use', nargs='?', const=1, type=int)
    args = parser.parse_args(sys.argv[2:])
    assert(False), "Not supported"


  ############################################################
  #                Build test-suite using cmake
  ############################################################

  # Get a path of directory to build test-suite
  def _getTestSuiteBuildPath(self, cfg, testcfg, runcfg, path_suffix=None):
    orgpath = testcfg["test-suite-dir"]
    if "ramdisk" in runcfg:
      orgpath = os.path.join(runcfg["ramdisk"], "test-suite")

    while orgpath[-1] == '/':
      orgpath = orgpath[:-1]

    if path_suffix == None:
      path_suffix = ""

    name = cfg["name"] if "name" in cfg else cfg["branch"]

    if hasAndEquals(runcfg, "emitasm", True):
      testpath = "%s-%s-%s-asm%s" % (orgpath, name, runcfg["buildopt"],
                                     path_suffix)
      assert("emitbc" not in runcfg)

    elif "emitbc" in runcfg:
      testpath = "%s-%s-%s-bc%s%s" % (orgpath, name, runcfg["buildopt"],
                                      runcfg["emitbc"], path_suffix)
      assert(not hasAndEquals(runcfg, "emitasm", True))

    else:
      strnow = datetime.datetime.now().strftime("%m_%d_%H_%M_%S")
      testpath = "%s-%s-%s-%s%s" % (orgpath, name, runcfg["buildopt"],
                                    strnow, path_suffix)

    assert (not os.path.exists(testpath)), \
           "Directory already exists: %s" % testpath
    return testpath

  def _initCCScript(self, clang, clangpp, noopt, emitllvm):
    mydir = os.path.dirname(__file__)
    f = open(os.path.join(mydir, "cc.sh"), "r")
    contents = "".join(list(f.readlines()))
    f.close()

    def _update(ccc, clang):
      ccc = ccc.replace("[[CLANG]]", clang)
      if emitllvm:
        if noopt:
          ccc = ccc.replace("[[PARAM]]", "-c -emit-llvm -Xclang -disable-llvm-optzns")
        else:
          ccc = ccc.replace("[[PARAM]]", "-c -emit-llvm")
        ccc = ccc.replace("[[EXT]]", "bc")
      else:
        if noopt:
          ccc = ccc.replace("[[PARAM]]", "-S -c -Xclang -disable-llvm-optzns")
        else:
          ccc = ccc.replace("[[PARAM]]", "-S -c")
        ccc = ccc.replace("[[EXT]]", "s")
      return ccc

    hexcode = "".join([random.choice(string.ascii_letters) for n in range(8)])

    ccpath = "/tmp/cc-%s.sh" % hexcode
    ccc = _update(contents, clang)
    f = open(ccpath, "w")
    f.write(ccc)
    f.close()
    os.chmod(ccpath, 0o777)

    cxxpath = "/tmp/cxx-%s.sh" % hexcode
    ccc = _update(contents, clangpp)
    f = open(cxxpath, "w")
    f.write(ccc)
    f.close()
    os.chmod(cxxpath, 0o777)

    return (ccpath, cxxpath)

  # Build test-suite by running cmake and make
  def _buildTestSuiteUsingCMake(self, testpath, cfg, testcfg, runcfg, speccfg=None,
                                runonly=None):
    assert(not os.path.exists(testpath))

    llvmdir = cfg["builds"][runcfg["buildopt"]]["path"]
    clang = "%s/bin/clang" % llvmdir
    clangpp = clang + "++"
    llsize = "%s/bin/llvm-size" % llvmdir

    # Use cc.sh
    if "emitbc" in runcfg:
      (clang, clangpp) = self._initCCScript(clang, clangpp,
          (True if runcfg["emitbc"] == "beforeopt" else False), True)
    elif hasAndEquals(runcfg, "emitasm", True):
      (clang, clangpp) = self._initCCScript(clang, clangpp, False, False)

    if "libcxx" in cfg["repo"]:
      # Set LD_LIBRARY_PATH
      os.putenv("LD_LIBRARY_PATH", "%s/lib" % llvmdir)

    cmakecache = "ReleaseNoLTO.cmake"
    if hasAndEquals(runcfg, "lto", True):
      cmakecache = "ReleaseLTO.cmake"

    os.makedirs(testpath)
    cmakeopt = ["cmake", "-DCMAKE_C_COMPILER=%s" % clang,
                         "-DCMAKE_CXX_COMPILER=%s" % clangpp,
                         "-DTEST_SUITE_LLVM_SIZE=%s" % llsize,
                         "-C%s/cmake/caches/%s" % (testcfg["test-suite-dir"], cmakecache)]
    if speccfg != None:
      cmakeopt.append("-DTEST_SUITE_SPEC2017_ROOT=%s" % speccfg["installed-dir"])

    cflags = ""
    cxxflags = ""

    if "libcxx" in cfg["repo"]:
      cxxflags = cxxflags + " -stdlib=libc++"

    if "cflags" in runcfg:
      cflags = " ".join(runcfg["cflags"])

    if "cxxflags" in runcfg:
      cxxflags = " ".join(runcfg["cxxflags"])

    if hasAndEquals(runcfg, "use_new_pass_manager", True):
      cflags = cflags + " -fexperimental-new-pass-manager"
      cxxflags = cxxflags + " -fexperimental-new-pass-manager"

    if len(cflags) > 0:
      cmakeopt = cmakeopt + ["-DCMAKE_C_FLAGS=%s" % cflags]
    if len(cxxflags) > 0:
      cmakeopt = cmakeopt + ["-DCMAKE_CXX_FLAGS=%s" % cxxflags]

    if runonly:
      subdir = runonly
      if runonly.find("/") != -1:
        subdir = runonly[0:runonly.find("/")]
      assert (subdir in ["Bitcode", "External", "MicroBenchmarks",
              "MultiSource", "SingleSource", "CTMark"]), \
              "Unknown directory (or file): %s" % runonly
      cmakeopt = cmakeopt + ["-DTEST_SUITE_SUBDIRS=%s" % subdir]

    if runcfg["benchmark"] != False:
      cmakeopt = cmakeopt + ["-DTEST_SUITE_BENCHMARKING_ONLY=On"]
      if hasAndEquals(runcfg, "use_cset", True):
        # Note: This doesn't work; the output contains a message from cset,
        # which causes tests to fail;
        #  cset: --> last message, executed args into cpuset "/user", new pid is: 16852
        #cmd = "sudo cset shield --user=%s --exec --" % runcfg["cset_username"]
        #cmakeopt = cmakeopt + ["-DTEST_SUITE_RUN_UNDER=%s" % cmd]

        # RunSafely.sh should be properly modified in advance
        #rsf = open(os.path.join(testcfg["test-suite-dir"], "RunSafely.sh"), "r")
        #lines = [l.strip() for l in rsf.readlines()]
        #if lines[197] == "$TIMEIT $TIMEITFLAGS $COMMAND":
        #  print("To enable use_cset, please update line 197 at %s/RunSafely.sh with following:" % testpath)
        #  print("\tsudo cset shield --user=sflab --exec $TIMEIT -- $TIMEITFLAGS $COMMAND")
        #  exit(1)
        #rsf.close()
        print("TODO: Unsupported feature: use_cset")
        exit(1)
      else:
        cmakeopt = cmakeopt + ["-DTEST_SUITE_RUN_UNDER=taskset -c 1"]

      if hasAndEquals(runcfg, "use_perf", True):
        checkPerf()
        cmakeopt = cmakeopt + ["-DTEST_SUITE_USE_PERF=ON"]

      if runcfg["benchmark"] == "compiletime":
        cmakeopt = cmakeopt + ["-DTEST_SUITE_COLLECT_COMPILE_TIME=ON",
                               "-DTEST_SUITE_RUN_BENCHMARKS=0"]

      elif hasAndEquals(runcfg, "compileonly", True):
        assert False, "compileonly is set!"

    elif hasAndEquals(runcfg, "compileonly", True):
      cmakeopt = cmakeopt + ["-DTEST_SUITE_RUN_BENCHMARKS=0"]

    cmakeopt.append(testcfg["test-suite-dir"])

    # Run cmake.
    p = Popen(cmakeopt, cwd=testpath)
    p.wait()

    makedir = testpath
    makeopt = ["make"]
    corecnt = runcfg["build-threads"] if "build-threads" in runcfg else 1
    makeopt.append("-j%d" % corecnt)

    if runonly:
      if runonly.startswith("SingleSource"):
        # To be conservative, remove the last path
        makedir = makedir + "/" + os.path.dirname(runonly)
      else:
        makedir = makedir + "/" + runonly

    print("Running make at %s" % makedir)
    # Run make.
    p = Popen(makeopt, cwd=makedir)
    p.wait()

  # Runs llvm-lit.
  def _runLit(self, testpath, llvmdir, runonly, corecnt, noExecute=False):
    resjson_num = 1
    # The name of results.json
    while os.path.exists("%s/results%d.json" % (testpath, resjson_num)):
      resjson_num = resjson_num + 1

    args = ["%s/bin/llvm-lit" % llvmdir,
            "-s", # succinct
            "-j", str(corecnt), "--no-progress-bar",
            "-o", "results%d.json" % resjson_num]
    if noExecute:
      args.append("--no-execute")

    if runonly:
      args.append(os.path.join(testpath, runonly))
    else:
      args.append(testpath)

    print("Running lit: %s" % " ".join(args))
    print("\tat: %s" % testpath)
    p = Popen(args, cwd=testpath)
    p.wait()

  # Run Test Suite using CMake
  def _runTestSuiteUsingCMake(self, cfg, testcfg, runcfg, runonly,
                              speccfg=None, path_suffix=None):
    if hasAndEquals(runcfg, "dropcache", True):
      dropCache()
    if hasAndEquals(runcfg, "disable_aslr", True):
      runAsSudo("echo 0 > /proc/sys/kernel/randomize_va_space")
    if hasAndEquals(runcfg, "set_scaling_governor", True):
      setScalingGovernor()


    if "ramdisk" in runcfg:
      for f in glob.glob(runcfg["ramdisk"]):
        if f == runcfg["ramdisk"]:
          continue
        runAsSudo(["rm", "-rf", "f"])

      runAsSudo(["umount", "-f", runcfg["ramdisk"]])
      runAsSudo(["mkdir", "-p", runcfg["ramdisk"]])
      retcode = runAsSudo(["mount", "-t", "tmpfs", "-o", "size=2048M",
                           "tmpfs", runcfg["ramdisk"]])
      assert(retcode == 0), "Cannot mount ramdisk: %s" % runcfg["ramdisk"]

    testpath = self._getTestSuiteBuildPath(cfg, testcfg, runcfg, path_suffix)
    print("++ Path: %s" % testpath)

    if hasAndEquals(runcfg, "use_cset", True):
      initCSet();

    self._buildTestSuiteUsingCMake(testpath, cfg, testcfg, runcfg, speccfg=speccfg,
                                   runonly=runonly)

    # Of iterations to run
    if hasAndEquals(runcfg, "emitasm", True) or "emitbc" in runcfg:
      # No need to run llvm-lit
      itrcnt = 0
    else:
      itrcnt = runcfg["iteration"] if "iteration" in runcfg else 1

    llvmdir = cfg["builds"][runcfg["buildopt"]]["path"]
    corecnt = runcfg["threads"] if "threads" in runcfg else 1
    if runcfg["benchmark"] == True:
      if "threads" in runcfg and runcfg["threads"] != 1:
        print("Warning: benchmark is set, but --threads is not 1!")

    elif runcfg["benchmark"] == "compiletime":
      if "build-threads" in runcfg and runcfg["build-threads"] != 1:
        print("Warning: benchmarking compile-time, but --build-threads is not 1!")

    for itr in range(0, itrcnt):
      runonly = runonly if runonly else "."
      if hasAndEquals(runcfg, "dropcache", True):
        dropCache()
      self._runLit(testpath, llvmdir, runonly, corecnt)


  ##
  # Run Test Suite using CMake
  ##
  def testsuite(self):
    parser = newParser("test", desc="""
Run test-suite using cmake command.
This runs programs that are not written in C/C++ as well.
""",
                       llvm=True, testsuite=True, run=True,
                       sendmail=True, optionals=["sendmail"])
    parser.add_argument('--runonly',
        help='Run a specified test only (e.g. SingleSource/Benchmarks/Shootout)',
        action='store', required=False)
    args = parser.parse_args(sys.argv[2:])

    cfg = json.load(open(args.cfg))
    testcfg = json.load(open(args.testcfg))
    runcfg = json.load(open(args.runcfg))
    runonly = args.runonly if args.runonly else None

    checkRunConfig(runcfg, args.runcfg)

    self._runTestSuiteUsingCMake(cfg, testcfg, runcfg, runonly)

    if args.mailcfg:
      cfg = json.load(open(args.mailcfg, "r"))
      sendMail(cfg, "test", str(args))


  # Get the list of tests by running `llvm-lit --show-tests`
  def _getTestList(self, testpath, llvmdir):
    cmds = ["%s/bin/llvm-lit" % llvmdir, "--show-tests", testpath]
    print(cmds)
    p = Popen(cmds, cwd=testpath, stdout=subprocess.PIPE)
    out, err = p.communicate()
    out = out.decode("utf-8")
    outs = list(filter((lambda x: len(x) > 0),
                [s.strip() for s in out.split("\n")]))

    assert(outs[0] == "-- Available Tests --")
    outs = outs[1:]
    for i in range(0, len(outs)):
      prefix = "test-suite :: "
      assert(outs[i].startswith(prefix)), "Should start with '%s': %s" % (prefix, outs[i])
      outs[i] = outs[i][len(prefix):]
    return outs



  ############################################################
  #    Diff assembly outputs after running test-suite
  #    with two LLVMs
  ############################################################

  def diff(self):
    parser = newParser("diff", desc="""
Diffs assembly outputs after running test-suite with two different LLVMs.
Infos about LLVMs should be given with --cfg and --cfg2.
The list of different assembly files is printed at the file specified by --out.
""",
        llvm=True, llvm2=True, testsuite=True, run=True,
        spec=True, sendmail=True, optionals=["sendmail", "testsuite", "spec"])
    parser.add_argument('--prebuilt', action="store",
        help='Use pre-built test-suites to generate diff (format: dir1,dir2)')
    parser.add_argument('--out', help='Output file path', required=True,
                        action='store')
    parser.add_argument('--runonly', action="store",
        help='Only run this benchmark')
    args = parser.parse_args(sys.argv[2:])

    cfg1 = json.load(open(args.cfg))
    cfg2 = json.load(open(args.cfg2))
    runcfg = json.load(open(args.runcfg))
    outf = open(args.out, "w")
    emitasm = hasAndEquals(runcfg, "emitasm", True)

    if args.prebuilt:
      paths = args.prebuilt.split(',')
      testpath1 = paths[0]
      testpath2 = paths[1]
    else:
      if hasAndEquals(runcfg, "use_cset", True):
        print("use_cset is not allowed for diff")
        exit(1)
        #initCSet();

      # Build test-suite from scratch.
      assert(args.testcfg), "To build test-suite, --testcfg is needed"
      testcfg = json.load(open(args.testcfg))
      speccfg = json.load(open(args.speccfg)) if args.speccfg else None

      assert(hasAndEquals(runcfg, "emitasm", True) or "emitbc" in runcfg)

      testpath1 = self._getTestSuiteBuildPath(cfg1, testcfg, runcfg)
      testpath2 = self._getTestSuiteBuildPath(cfg2, testcfg, runcfg)

      runonly = None
      if args.runonly:
        runonly = args.runonly
        if runonly.startswith("CINT2017rate") or runonly.startswith("CFP2017rate") or \
           runonly.startswith("CINT2017speed") or runonly.startswith("CFP2017speed"):
          if speccfg == None:
            print("runonly is %s, but --speccfg is not given!" % runonly)
            exit(1)
          runonly = "External/SPEC/" + runonly

      self._buildTestSuiteUsingCMake(testpath1, cfg1, testcfg, runcfg, speccfg, runonly)
      self._buildTestSuiteUsingCMake(testpath2, cfg2, testcfg, runcfg, speccfg, runonly)

    corecnt = multiprocessing.cpu_count()
    if args.runcfg:
      corecnt = runcfg["threads"] if "threads" in runcfg else 1

    llvmdir1 = cfg1["builds"][runcfg["buildopt"]]["path"]
    llvmdir2 = cfg2["builds"][runcfg["buildopt"]]["path"]
    # This is needed to get test list
    self._runLit(testpath1, llvmdir1, None, corecnt, noExecute=True)
    self._runLit(testpath2, llvmdir2, None, corecnt, noExecute=True)

    tests = self._getTestList(testpath2, llvmdir2)
    tests.sort()

    # Diff all .s files
    print(testpath1)
    print(testpath2)
    ext = '.s' if emitasm else '.bc'
    result1 = [os.path.join(os.path.relpath(dp, testpath1), f)
               for dp, dn, filenames in os.walk(testpath1)
               for f in filenames if os.path.splitext(f)[-1] == ext]
    result2 = [os.path.join(os.path.relpath(dp, testpath2), f)
               for dp, dn, filenames in os.walk(testpath2)
               for f in filenames if os.path.splitext(f)[-1] == ext]
    # The list of files should be same
    assert(set(result1) == set(result2))
    print("Total %d %s pairs found" % (len(result1), ext))
    # TODO: relate 'tests' variable with results

    cnt = 0
    for asmf in result1:
      cnt = cnt + 1
      asmpath1 = "%s/%s" % (testpath1, asmf)
      asmpath2 = "%s/%s" % (testpath2, asmf)
      if emitasm:
        hasdiff = asmHasDiff(asmpath1, asmpath2)
      else:
        tmp1 = "/tmp/%d.l.ll" % cnt
        tmp2 = "/tmp/%d.r.ll" % cnt
        p = Popen(["%s/bin/llvm-dis" % llvmdir1, asmpath1, "-o", tmp1])
        p.wait()
        p = Popen(["%s/bin/llvm-dis" % llvmdir2, asmpath2, "-o", tmp2])
        p.wait()
        hasdiff = llHasDiff(tmp1, tmp2)
      outf.write("%s %s\n" % (asmf, "YESDIFF" if hasdiff else "NODIFF"))
      if cnt % 100 == 0:
        print("--%d--" % cnt)

    if args.mailcfg:
      cfg = json.load(open(args.mailcfg, "r"))
      sendMail(cfg, "diff", str(args))


  def compare(self):
    parser = newParser("compare", desc="""
Compares performance results of test-suite results.
Two directories containing results (resultN.json) should be specified with
--dir1 and --dir2.
The output is printed in csv format to the file specified by --out.
To give additional parameters for pruning out highly fluctuated results or
short tests, use --comparecfg.
""")
    parser.add_argument('--dir1', required=True, action="store", help='Result dir 1')
    parser.add_argument('--dir2', required=True, action="store", help='Result dir 2')
    parser.add_argument('--comparecfg', action="store", required=True,
                        help="Configurations for fine-grained filtering control")
    parser.add_argument('--out', help='Output file path', required=True,
                        action='store')
    # We're not using test-suite/utils/compare.py because it does not have
    # options for fine-grained control of filtering results.
    args = parser.parse_args(sys.argv[2:])

    mintime = 0.0
    tolerance = 1
    comparecfg = json.load(open(args.comparecfg))

    assert("collect" in comparecfg)

    if comparecfg["collect"] == "exectime":
      if "minimum-runtime-sec" in comparecfg:
        mintime = comparecfg["minimum-runtime-sec"]
      if "tolerance" in comparecfg:
        tolerance = comparecfg["tolerance"]
      res1 = readRunningTimes(args.dir1)
      res2 = readRunningTimes(args.dir2)

      assert(set(res1.keys()) == set(res2.keys())), \
             "The list of tests does not match."

      def _median(runs):
        l = len(runs)
        return runs[int(l / 2)] if l % 2 == 1 else \
              (runs[int(l / 2)] + runs[int((l+1) / 2)]) / 2

      def _filter(runs, med):
        if med == 0.0:
          return True
        return (runs[0] >= mintime) and \
               (max(med - runs[0], runs[-1] - med) / med < tolerance)

      aggregated_result = []
      trials = None
      for k in res1.keys():
        runs1 = res1[k]
        runs2 = res2[k]
        assert(len(runs1) == len(runs2))
        if trials == None:
          trials = len(runs1)
        runs1.sort()
        runs2.sort()
        med1 = _median(runs1)
        med2 = _median(runs2)

        if not _filter(runs1, med1) or not _filter(runs2, med2):
          continue

        speedup = 0.0 if med2 == 0.0 else ((med1 - med2) / med2 * 100)
        aggregated_result.append([k] + runs1 + [med1] + runs2 + [med2] + [speedup])

      aggregated_result.sort(key=lambda k: k[-1])
      fhand = open(args.out, 'w')
      w = csv.writer(fhand)
      w.writerow(["Name"] + ["Itr%d" % x for x in range(1, trials+1)] +
                 ["Median (sec.)"] + ["Itr%d" % x for x in range(1, trials+1)] +
                 ["Median (sec.)", "Speedup(%)"])
      for row in aggregated_result:
        w.writerow(row)
      fhand.close()

    elif comparecfg["collect"] == "objsize":
      res1 = readObjSizes(args.dir1)
      res2 = readObjSizes(args.dir2)

      assert(set(res1.keys()) == set(res2.keys())), \
             "The list of tests does not match."

      aggregated_result = []
      for k in res1.keys():
        runs1 = res1[k]
        runs2 = res2[k]
        for r in runs1:
          assert(r == runs1[0])
        for r in runs2:
          assert(r == runs2[0])

        r1 = runs1[0]
        r2 = runs2[0]
        increase = (r1 / r2 - 1.0) * 100.0
        aggregated_result.append([k, runs1[0], runs2[0], increase])

      aggregated_result.sort(key=lambda k: k[-1])
      fhand = open(args.out, 'w')
      w = csv.writer(fhand)
      w.writerow(["Name", "size", "size", "increase(%)"])
      for row in aggregated_result:
        w.writerow(row)
      fhand.close()


  ############################################################
  #                Running SPEC benchmarks
  ############################################################
  def spec(self):
    parser = newParser("spec", desc="""
Runs SPEC CPU benchmark.
The path of SPEC CPU should be given with --speccfg.
""",
                       llvm=True, testsuite=True, run=True, spec=True,
                       sendmail=True, optionals=["testsuite", "sendmail"])
    parser.add_argument('--testsuite', action="store_true",
        help='Use test-suite to run SPEC')
    parser.add_argument('--runonly', action="store",
        help='Only run this benchmark (CINT2017rate/CFP2017rate/CINT2017speed/CFP2017speed)')
    args = parser.parse_args(sys.argv[2:])

    if args.testsuite:
      if not args.testcfg:
        print("--testcfg should be given to run SPEC with test-suite!")
        exit(1)

      cfg = json.load(open(args.cfg))
      testcfg = json.load(open(args.testcfg))
      runcfg = json.load(open(args.runcfg))
      speccfg = json.load(open(args.speccfg))

      checkRunConfig(runcfg, args.runcfg)

      runonly = "External/SPEC"
      if args.runonly:
        runonly = runonly + "/" + args.runonly

      suffix = "_SPEC2017"
      if args.runonly:
        suffix = "_" + args.runonly.replace("/", "_")
      self._runTestSuiteUsingCMake(cfg, testcfg, runcfg, runonly,
                                   speccfg=speccfg, path_suffix=suffix)

      if args.mailcfg:
        cfg = json.load(open(args.mailcfg, "r"))
        sendMail(cfg, "spec", str(args))

    else:
      assert False, "Not implemented"



  ############################################################
  #           Running test-suite using LNT script
  ############################################################
  def lnt(self):
    parser = newParser("lnt", desc="Runs test-suite using LNT script.",
                       llvm=True, testsuite=True, run=True,
                       sendmail=True, optionals=["sendmail"])
    args = parser.parse_args(sys.argv[2:])

    cfg = json.load(open(args.cfg))
    testcfg = json.load(open(args.testcfg))
    runcfg = json.load(open(args.runcfg))

    checkRunConfig(runcfg, args.runcfg)

    buildopt = runcfg["buildopt"]
    clangdir = cfg["builds"][buildopt]["path"]

    cmds = [testcfg["virtualenv-dir"] + "/bin/lnt",
            "runtest",
            "nt",
            "--sandbox", testcfg["virtualenv-dir"],
            "--cc", clangdir + "/bin/clang",
            "--cxx", clangdir + "/bin/clang++",
            "--test-suite", testcfg["test-suite-dir"]]

    if runcfg["benchmark"] == True:
      if "threads" in runcfg and runcfg["threads"] != 1:
        print("Warning: benchmark is set, but --threads is not 1!")
      cmds = cmds + ["--benchmarking-only", "--use-perf", "time",
                     "--make-param", "\"RUNUNDER=taskset -c 1\""]

      if "iteration" in runcfg:
        cmds = cmds + ["--multisample", str(runcfg["iteration"])]
    elif runcfg["benchmark"] == "compiletime":
      assert(False), "Measuring compile-time is not supported in LNT"

    if "threads" in runcfg:
      cmds = cmds + ["--threads", str(runcfg["threads"])]
    if "build-threads" in runcfg:
      cmds = cmds + ["--build-threads", str(runcfg["build-threads"])]

    cflags = ""
    if hasAndEquals(runcfg, "lto", True):
      cflags = cflags + " -flto"

    if "cflags" in runcfg:
      cflags = " ".join(runcfg["cflags"])

    if "cxxflags" in runcfg:
      if "cflags" in runcfg and runcfg["cflags"] != runcfg["cxxflags"]:
        print("Warning: cxxflags is not used when running test-suite with lnt "
              "script")

    if hasAndEquals(runcfg, "use_new_pass_manager", True):
      cflags = cflags + " -fexperimental-new-pass-manager"

    cmds = cmds + ["--cflag=" + cflags]

    print(cmds)

    p = Popen(cmds)
    p.wait()

    if args.mailcfg:
      cfg = json.load(open(args.mailcfg, "r"))
      sendMail(cfg, "lnt", str(args))



  ############################################################
  #                  Count instructions
  ############################################################

  def _instcount_sum(self, json, jsonres):
    assert(("instrs" in json) and ("instrs" in jsonres))
    assert(("constexprs" in json) and ("constexprs" in jsonres))
    assert(("intrinsics" in json) and ("intrinsics" in jsonres))

    for k in ["instrs", "constexprs", "intrinsics"]:
      for k2 in json[k]:
        n = 0
        if k2 in jsonres[k]:
          n = jsonres[k][k2]
        jsonres[k][k2] = n + json[k][k2]

  def instcount(self):
    parser = newParser("instcount", llvm=True)
    parser.add_argument('--dir', help='A directory that contains *.bc files', action='store', required=True)
    parser.add_argument('--out', help='Output (as a json file)', action='store', required=True)
    args = parser.parse_args(sys.argv[2:])

    if not os.path.exists(args.dir):
      print("Cannot find %s" % args.dir)
      exit(1)

    outdir = os.path.dirname(args.out)
    if outdir != "" and not os.path.exists(outdir):
      print("Cannot find %s" % os.path.dirname(outdir))
      exit(1)

    cfg = json.load(open(args.cfg))
    llvmdir = None
    lcfg = None

    for k in cfg["builds"]:
      p = cfg["builds"][k]["path"]
      pcfg = os.path.join(p, "bin", "llvm-config")
      if os.path.exists(pcfg):
        llvmdir = p
        lcfg = pcfg
        break

    if not lcfg:
      print("Cannot find llvm-config")
      exit(1)

    mydir = os.path.dirname(__file__)

    # Let's compile instcounter.cpp
    p = Popen([lcfg, "--cxxflags", "--ldflags", "--libs", "--system-libs"], stdout=subprocess.PIPE)
    out, err = p.communicate()
    cxxflags = out.decode("utf-8").split()

    instcounter = "/tmp/instcounter"
    p = Popen([os.path.join(llvmdir, "bin", "clang++"), "-std=c++11",
               os.path.join(mydir, "instcounter.cpp")] + cxxflags +
              ["-o", instcounter])
    p.wait()
    if not os.path.exists(instcounter):
      print("%s not generated!" % instcounter)
      exit(1)

    # Now, let's traverse and accumulate the result!
    bcpaths = [os.path.join(dp, f)
               for dp, dn, filenames in os.walk(args.dir)
               for f in filenames if os.path.splitext(f)[-1] == '.bc']

    #results = dict()
    total = {"instrs":{}, "constexprs":{}, "intrinsics":{} }
    for bcpath in bcpaths:
      print(bcpath)
      p = Popen([instcounter, bcpath], stdout=subprocess.PIPE)
      out, err = p.communicate()
      t = out.decode("utf-8")
      j = json.loads(t)
      #results[bcpath] = j
      self._instcount_sum(j, total)

    total["path"] = args.dir
    total["instrs"]["total"] = sum([total["instrs"][k] for k in total["instrs"]])
    total["constexprs"]["total"] = sum([total["constexprs"][k] for k in total["constexprs"]])
    total["intrinsics"]["total"] = sum([total["intrinsics"][k] for k in total["intrinsics"]])
    s = json.dumps(total, indent=2)
    open(args.out, "w").write(s)



  ############################################################
  #  Filter test-suite result (json) with assembly diff list
  ############################################################
  def filter(self):
    parser = argparse.ArgumentParser(description = 'Arguments for filter command')
    parser.add_argument('--json', action="store",
        help='The result of test-suite run', required=True)
    parser.add_argument('--diff', action="store",
        help='Assembly diff file', required=True)
    parser.add_argument('--out', help='Output file path', required=True,
                        action='store')
    args = parser.parse_args(sys.argv[2:])

    difflines = open(args.diff, "r").readlines()
    diffs = []
    for l in difflines:
      ll = l.split()
      filename, hasdiff = ll[0], ll[1]
      hasdiff = hasdiff.strip()

      if filename.endswith(".c.o.s"):
        filename = filename[:-len(".c.o.s")]
      elif filename.endswith(".cpp.o.s"):
        filename = filename[:-len(".cpp.o.s")]
      elif filename.endswith(".bc.o.s"):
        filename = filename[:-len(".bc.o.s")]
      elif filename.endswith(".cc.o.s"):
        filename = filename[:-len(".cc.o.s")]
      elif filename.endswith(".cxx.o.s"):
        filename = filename[:-len(".cxx.o.s")]
      else:
        assert False, filename

      assert(hasdiff == "YESDIFF" or hasdiff == "NODIFF")

      diffs.append((filename, True if hasdiff == "YESDIFF" else False))

    data = json.load(open(args.json, "r"))
    results = data["tests"]
    newresults = []

    for i in range(0, len(results)):
      rawname = results[i]["name"]

      assert(rawname.startswith("test-suite :: "))
      rawname = rawname[len("test-suite :: "):]
      if not rawname.startswith("MicroBenchmarks"):
        assert rawname.endswith(".test"), rawname
      name = rawname[:rawname.rfind(".test")]

      if name.startswith("SingleSource"):
        # SingleSource/AA/TEST => SingleSource/AA/CMakeFiles/TEST.dir/test.extension
        idx = name.rfind("/")
        testname = name[name.rfind("/") + 1:]
        newname = name[:idx] + "/CMakeFiles/" + testname + ".dir/" + testname
        diffs_filtered = [x for x in diffs if x[0] == newname]

        if diffs_filtered == []:
          # Remove the filename and retry
          newname = newname[:newname.rfind("/")]
          diffs_filtered = [x for x in diffs if x[0].startswith(newname)]

        assert(len(diffs_filtered) == 1)

      else:
        # MultiSource/AA/TEST => MultiSource/AA/CMakeFiles/TEST.dir/*
        idx = name.rfind("/")
        testname = name[name.rfind("/") + 1:]
        newname = name[:idx] + "/CMakeFiles/" + testname + ".dir/"
        #print(newname)
        diffs_filtered = [x for x in diffs if x[0].startswith(newname)]
        assert(len(diffs_filtered) > 0)

      #print(diffs_filtered)

      hasdiff = False
      for itm in diffs_filtered:
        hasdiff = hasdiff or itm[1]
      if hasdiff:
        print("-- %s: HAS DIFF!" % rawname)
        newresults.append(results[i])

    data["tests"] = newresults
    json.dump(data, open(args.out, "w"), indent=2)



  ############################################################
  #                   check config files
  ############################################################
  def check(self):
    parser = newParser("check", desc="Checks the validity of configurations.",
                       llvm=True, testsuite=True, run=True, spec=True,
        sendmail=True,
        optionals=["llvm", "testsuite", "run", "spec", "sendmail"])
    args = parser.parse_args(sys.argv[2:])
    hasFatal = False
    hasWarning = False

    def _errmsg(is_fatal, msg, submsg=None):
      print("[%s] %s" % ("Fatal" if is_fatal else "Warning", msg))
      if submsg:
        print("\t%s" % submsg)

    def _checkAttr(flag, attrname, filename, is_fatal, msg=None):
      nonlocal hasFatal
      nonlocal hasWarning
      if flag:
        return
      if is_fatal:
        hasFatal = True
      else:
        hasWarning = True
      _errmsg(is_fatal, "Attribute %s does not exist in %s" % (attrname, filename),
              submsg=msg)

    if args.cfg:
      fname = args.cfg
      cfg = json.load(open(fname))

      _checkAttr("src" in cfg, "src", fname, True)
      _checkAttr("repo" in cfg, "repo", fname, True)
      _checkAttr("builds" in cfg, "builds", fname, True)

      for build in cfg["builds"]:
        _checkAttr("path" in cfg["builds"][build], "builds/%s/path" % build, fname, True)
        # sharedlib is not mandatory

    if args.testcfg:
      fname = args.testcfg
      testcfg = json.load(open(fname))

      _checkAttr("lnt-dir" in testcfg, "lnt-dir", fname, False,
                 msg="lnt-dir is needed to run test-suite with lnt")
      _checkAttr("test-suite-dir" in testcfg, "test-suite", fname, True)
      _checkAttr("virtualenv-dir" in testcfg, "virtualenv-dir", fname, False,
                 msg="virtualenv-dir is needed to run test-suite with lnt")

      for prj in ["test-suite", "lnt"]:
        _checkAttr(prj in testcfg, prj, fname, True)
        _checkAttr("url" in testcfg[prj], "%s/url" % prj, fname, True)
        _checkAttr("branch" in testcfg[prj], "%s/branch" % prj, fname, True)

    if args.runcfg:
      fname = args.runcfg
      runcfg = json.load(open(args.runcfg))

      _checkAttr("buildopt" in runcfg, "buildopt", fname, True)
      _checkAttr("benchmark" in runcfg, "benchmark", fname, True)

      if hasAndEquals(runcfg, "use_cset", True):
        _errmsg(True, "use_cset is not supported.")
        #_checkAttr("cset_username" in runcfg, "cset_username", fname, True,
        #           msg="If use_cset = true, cset_username should be specified.")

      if hasAndEquals(runcfg, "benchmark", True) and hasAndEquals(runcfg, "emitasm", True):
        _errmsg(True, "emitasm and benchmark cannot be both true.")
      if hasAndEquals(runcfg, "benchmark", True) and "emitbc" in runcfg:
        _errmsg(True, "emitbc and benchmark cannot be both true.")
      if hasAndEquals(runcfg, "emitasm", True)   and "emitbc" in runcfg:
        _errmsg(True, "emitasm and emitbc cannot be both true.")
      if "emitbc" in runcfg:
        if not (runcfg["emitbc"] == "beforeopt" or runcfg["emitbc"] == "afteropt"):
          _errmsg(True, "emitbc should be either \"beforeopt\" or \"afteropt\"")

    if args.speccfg:
      fname = args.speccfg
      speccfg = json.load(open(args.speccfg))

      _checkAttr("installed-dir" in speccfg, "installed-dir", fname, True)

    if args.mailcfg:
      fname = args.mailcfg
      smcfg = json.load(open(fname))

      _checkAttr("from" in smcfg, "from", fname, True)
      _checkAttr("frompasswd" in smcfg, "frompasswd", fname, True)
      _checkAttr("to" in smcfg, "to", fname, True)

    if hasFatal:
      exit(2)
    elif hasWarning:
      exit(1)
    else:
      exit(0)



  ############################################################
  #                       Test mail
  ############################################################
  def mailtest(self):
    parser = newParser("mailtest", sendmail=True, optionals=[])
    args = parser.parse_args(sys.argv[2:])
    cfg = json.load(open(args.mailcfg, "r"))
    sendMail(cfg, "test from llvmscript", "contents")



if __name__ == '__main__':
  LLVMScript()

