#!/usr/bin/python3
import argparse
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


# Check whether given config is valid
def checkLLVMConfigForClone(js, filename=None):
  errmsg = lambda attrname: "Attribute %s does not exist%" % \
      (attrname, " in file %s" % filename if filename else "")
  # Destination of src should exist
  assert ("src" in js), errmsg("src")
  # Should have cloninig repo info
  assert ("repo" in js), errmsg("repo")
  # LLVM repo should exist
  assert ("llvm" in js["repo"]), errmsg("repo/llvm")
  # For each repo, url should exist
  for i in js["repo"]:
    assert ("url" in js["repo"][i]), errmsg("repo/%s/url" % i)

def checkLLVMConfigForBuild(js, buildopt,
                            filename=None):
  errmsg = lambda attrname: "Attribute %s does not exist%" % \
      (attrname, " in file %s" % filename if filename else "")
  # Destination of src should exist
  assert ("src" in js), errmsg("src")
  # Should have build options
  assert ("builds" in js), errmsg("builds")
  assert (buildopt in js["builds"]), errmsg("builds/%s" % buildopt)
  assert ("path" in js["builds"][buildopt]), errmsg("builds/%s/path" % buildopt)

def checkLNTConfigForClone(js, filename=None):
  errmsg = lambda attrname: "Attribute %s does not exist%" % \
      (attrname, " in file %s" % filename if filename else "")
  # Destination of lnt/test-suite/virtualenv should exist
  assert ("lnt-dir" in js), errmsg("lnt-dir")
  assert ("test-suite-dir" in js), errmsg("test-suite-dir")
  assert ("virtualenv-dir" in js), errmsg("virtualenv-dir")
  # Should have cloninig repo info
  assert ("repo" in js), errmsg("repo")
  # LLVM repo should exist
  assert ("lnt" in js["repo"]), errmsg("repo/lnt")
  assert ("test-suite" in js["repo"]), errmsg("repo/test-suite")
  for i in js["repo"]:
    assert ("url" in js["repo"][i]), errmsg("repo/%s/url" % i)


def newParser(cmd, llvm=False, llvm2=False, testsuite=False, run=False,
              spec=False, sendmail=False, optionals=[]):
  parser = argparse.ArgumentParser(
      description = 'Arguments for %s command' % cmd)

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



# Main object.
class LLVMScript(object):

  def __init__(self):
    parser = argparse.ArgumentParser(
      usage = '''python3 run.py <command> [<args>]

Commands:
  clone     Clone LLVM into local
  build     Build LLVM
  testsuite Clone & initialize test-suite and lnt
  test      Run test-suite using cmake
  lnt       Run test-suite using lnt
  spec      Run SPEC benchmark
  instcount Get statistics of the number of LLVM assembly instructions
  diff      Compile test-suite with two compilers and compare assembly files
  filter    Filter test-suite result with assembly diff
  check     Check wellformedness of config files

Type 'python3 run.py <command> help' to get details
''')

    parser.add_argument('command', help='clone/build/lntclone/spec2017')
    args = parser.parse_args(sys.argv[1:2])
    if not hasattr(self, args.command):
      print ("Unrecognized command")
      parser.print_help()
      exit(1)
    getattr(self, args.command)()



  def clone(self):
    parser = newParser("clone", llvm=True, sendmail=True, optionals=["sendmail"])
    parser.add_argument('--depth', help='commit depth to clone (-1 means inf)', nargs='?', const=-1, type=int)
    args = parser.parse_args(sys.argv[2:])

    cfgpath = args.cfg
    f = open(cfgpath)
    cfg = json.load(f)
    checkLLVMConfigForClone(cfg)

    abssrc = os.path.abspath(cfg["src"])
    if not os.path.exists(abssrc):
      os.mkdir(abssrc)
    elif not os.path.isdir(abssrc):
      print("%s is not a directory." % abssrc)
      exit(1)

    def _callGitClone (cfg, name):
      repo = cfg["repo"][name]["url"]
      dest = os.path.join(abssrc, name)
      branch = None
      depth = None

      if "branch" in cfg["repo"][name]:
        branch = cfg["repo"][name]["branch"]

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

    pipes = []
    pipes.append(_callGitClone(cfg, "llvm"))
    pipes.append(_callGitClone(cfg, "clang"))
    if "compiler-rt" in cfg["repo"]:
      pipes.append(_callGitClone(cfg, "compiler-rt"))
    if "libcxx" in cfg["repo"]:
      pipes.append(_callGitClone(cfg, "libcxx"))
    if "libcxxabi" in cfg["repo"]:
      pipes.append(_callGitClone(cfg, "libcxxabi"))
    if "clang-tools-extra" in cfg["repo"]:
      pipes.append(_callGitClone(cfg, "clang-tools-extra"))
    for p in pipes:
      p.wait()

    if args.mailcfg:
      cfg = json.load(open(args.mailcfg, "r"))
      sendMail(cfg, "clone", str(args))


  def build(self):
    parser = newParser("build", llvm=True, sendmail=True, optionals=["sendmail"])
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

    options = cfg["builds"][args.build]

    abspath = os.path.abspath(options["path"])
    if not os.path.exists(abspath):
      try:
        os.makedirs(abspath)
      except OSError as e:
        print ("Cannot create directory '{0}'.".format(options["path"]))
        exit(1)

    cmd = ["cmake", os.path.join(os.path.abspath(cfg["src"]), "llvm")]
    os.chdir(abspath)

    if args.build == "release":
      cmd.append("-DCMAKE_BUILD_TYPE=Release")
    elif args.build == "relassert":
      cmd = cmd + ["-DCMAKE_BUILD_TYPE=Release", "-DLLVM_ENABLE_ASSERTIONS=On"]
    elif args.build == "debug":
      cmd.append("-DCMAKE_BUILD_TYPE=Debug")

    if hasAndEquals(options, "sharedlib", True):
      cmd.append("-DBUILD_SHARED_LIBS=1")

    externals = []
    if "clang" in cfg["repo"]:
      externals = externals + ["clang"]
    if "compiler-rt" in cfg["repo"]:
      externals = externals + ["compiler-rt"]
    if "libcxx" in cfg["repo"]:
      externals = externals + ["libcxx"]
    if "libcxxabi" in cfg["repo"]:
      externals = externals + ["libcxxabi"]
    if "clang-tools-extra" in cfg["repo"]:
      externals = externals + ["clang-tools-extra"]

    if len(externals) != 0:
      cmd.append("-DLLVM_ENABLE_PROJECTS=%s" % ";".join(externals))
    if "clang-tools-extra" in cfg["repo"]:
      cmd.append("-DLLVM_TOOL_CLANG_TOOLS_EXTRA_BUILD=On")
      #cmd.append("-DCLANGD_BUILD_XPC=Off") # clangd 8.0 does not compile

    p = Popen(cmd)
    p.wait()

    # Now build
    cmd = ["cmake", "--build", "."]
    buildarg = []
    corecnt = multiprocessing.cpu_count()

    if args.target:
      buildarg = args.target.split(',')

    if args.core:
      corecnt = args.core

    buildarg = buildarg + ["-j%d" % corecnt]
    cmd = cmd + ["--"] + buildarg

    p = Popen(cmd)
    p.wait()

    if args.mailcfg:
      cfg = json.load(open(args.mailcfg, "r"))
      sendMail(cfg, "build", str(args))



  ############################################################
  #              cloning test-suite and lnt
  ############################################################
  def testsuite(self):
    parser = newParser("testsuite", testsuite=True, sendmail=True, optionals=["sendmail"])
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
    p = Popen(["virtualenv", "-p", "python2", venv_dir])
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
  #            Building test-suite using cmake
  ############################################################

  # Get a path of directory to build test-suite
  def _getTestSuiteBuildPath(self, cfg, testcfg, runcfg, path_suffix=None):
    orgpath = testcfg["test-suite-dir"]
    if "ramdisk" in runcfg:
      orgpath = os.path.join(runcfg["ramdisk"], "test-suite")

    while orgpath[-1] == '/':
      orgpath = orgdir[:-1]

    if path_suffix == None:
      path_suffix = ""

    if hasAndEquals(runcfg, "emitasm", True):
      testpath = "%s-%s-%s-%s-asm%s" % (orgpath,
                                  cfg["repo"]["llvm"]["branch"],
                                  cfg["repo"]["clang"]["branch"],
                                  runcfg["buildopt"], path_suffix)
      assert("emitbc" not in runcfg)
      num = 1
      while os.path.exists(os.path.join(orgpath, testpath)):
        num = num + 1
        testpath = "%s-%s-%s-%s-asm%d%s" % (orgpath,
                                    cfg["repo"]["llvm"]["branch"],
                                    cfg["repo"]["clang"]["branch"],
                                    runcfg["buildopt"], num, path_suffix)

    elif "emitbc" in runcfg:
      testpath = "%s-%s-%s-%s-bc%s%s" % (orgpath,
                                  cfg["repo"]["llvm"]["branch"],
                                  cfg["repo"]["clang"]["branch"],
                                  runcfg["buildopt"], runcfg["emitbc"],
                                  path_suffix)
      assert(not hasAndEquals(runcfg, "emitasm", True))
      num = 1
      while os.path.exists(os.path.join(orgpath, testpath)):
        num = num + 1
        testpath = "%s-%s-%s-%s-bc%s%d%s" % (orgpath,
                                    cfg["repo"]["llvm"]["branch"],
                                    cfg["repo"]["clang"]["branch"],
                                    runcfg["buildopt"], runcfg["emitbc"],
                                    num, path_suffix)

    else:
      strnow = datetime.datetime.now().strftime("%m_%d_%H_%M_%S")
      testpath = "%s-%s-%s-%s-%s%s" % (orgpath,
                                    cfg["repo"]["llvm"]["branch"],
                                    cfg["repo"]["clang"]["branch"],
                                    runcfg["buildopt"], strnow,
                                    path_suffix)

    return testpath

  # Initialize cset
  def _initCSet(self):
    p = Popen(["sudo", "cset", "shield", "--reset"])
    p.wait()
    p = Popen(["sudo", "cset", "shield", "-c", "0"])
    p.wait()

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

    os.makedirs(testpath)
    cmakeopt = ["cmake", "-DCMAKE_C_COMPILER=%s" % clang,
                         "-DCMAKE_CXX_COMPILER=%s" % clangpp,
                         "-DTEST_SUITE_LLVM_SIZE=%s" % llsize,
                         "-C%s/cmake/caches/O3.cmake" % testcfg["test-suite-dir"]]
    if speccfg != None:
      cmakeopt.append("-DTEST_SUITE_SPEC2017_ROOT=%s" % speccfg["installed-dir"])

    cflags = ""
    cxxflags = ""

    if "libcxx" in cfg["repo"]:
      cxxflags = cxxflags + " -stdlib=libc++"

    if len(cflags) > 0:
      cmakeopt = cmakeopt + ["-DCMAKE_C_FLAGS=%s" % cflags]
    if len(cxxflags) > 0:
      cmakeopt = cmakeopt + ["-DCMAKE_CXX_FLAGS=%s" % cxxflags]

    if runonly:
      subdir = runonly
      if runonly.find("/") != -1:
        subdir = runonly[0:runonly.find("/")]
      assert (subdir in ["Bitcode", "External", "MicroBenchmarks",
              "MultiSource", "SingleSource"]), \
              "Unknown directory (or file): %s" % runonly
      cmakeopt = cmakeopt + ["-DTEST_SUITE_SUBDIRS=%s" % subdir]

    if runcfg["benchmark"]:
      cmakeopt = cmakeopt + ["-DTEST_SUITE_BENCHMARKING_ONLY=On"]
      if runcfg["use_cset"]:
        # RunSafely.sh should be properly modified in advance
        rsf = open(os.path.join(testcfg["test-suite-dir"], "RunSafely.sh"), "r")
        lines = [l.strip() for l in rsf.readlines()]
        if lines[196] == "$TIMEIT $TIMEITFLAGS $COMMAND":
          print("To enable use_cset, please update line 197 at %s/RunSafely.sh with following:" % testpath)
          print("\tsudo cset shield --user=sflab --exec $TIMEIT -- $TIMEITFLAGS $COMMAND")
          exit(1)
        rsf.close()
      else:
        cmakeopt = cmakeopt + ["-DTEST_SUITE_RUN_UNDER=taskset -c 1"]
    cmakeopt.append(testcfg["test-suite-dir"])

    # Run cmake.
    p = Popen(cmakeopt, cwd=testpath)
    p.wait()

    makedir = testpath
    makeopt = ["make"]
    if runcfg["benchmark"] == False:
      corecnt = runcfg["build-threads"] if "build-threads" in runcfg else 1
      makeopt.append("-j%d" % corecnt)

    if runonly:
      if runonly.startswith("SingleSource"):
        # To be conservative, remove the last path
        makedir = makedir + "/" + os.path.dirname(runonly)
      else:
        makedir = makedir + "/" + runonly

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
      args.append(runonly)
    else:
      args.append(".")

    p = Popen(args, cwd=testpath)
    p.wait()

  # Run Test Suite using CMake
  def _runTestSuiteUsingCMake(self, cfg, testcfg, runcfg, runonly,
                              speccfg=None, path_suffix=None):
    if hasAndEquals(runcfg, "dropcache", True):
      Popen(["sudo", "-S", "sh", "-c", "echo 1 > /proc/sys/vm/drop_caches"]).wait()
      Popen(["sudo", "-S", "sh", "-c", "echo 2 > /proc/sys/vm/drop_caches"]).wait()
      Popen(["sudo", "-S", "sh", "-c", "echo 3 > /proc/sys/vm/drop_caches"]).wait()

    if "ramdisk" in runcfg:
      for f in glob.glob(runcfg["ramdisk"]):
        if f == runcfg["ramdisk"]:
          continue
        Popen(["sudo", "-S", "rm", "-rf", f]).wait()

      p = Popen(["sudo", "-S", "umount", "-f", runcfg["ramdisk"]])
      p.wait()

      Popen(["sudo", "-S", "mkdir", "-p", runcfg["ramdisk"]]).wait()
      cmd = ["sudo", "-S", "mount", "-t", "tmpfs", "-o", "size=2048M",
             "tmpfs", runcfg["ramdisk"]]
      p = Popen(cmd)
      p.wait()
      assert(p.returncode == 0)

    testpath = self._getTestSuiteBuildPath(cfg, testcfg, runcfg, path_suffix)
    print("++ Path: %s" % testpath)

    if hasAndEquals(runcfg, "use_cset", True):
      self._initCSet();

    if not hasAndEquals(runcfg, "nobuild", True):
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

    for itr in range(0, itrcnt):
      runonly = runonly if runonly else "."
      if hasAndEquals(runcfg, "dropcache", True):
        Popen(["sudo", "-S", "sh", "-c", "echo 1 > /proc/sys/vm/drop_caches"]).wait()
        Popen(["sudo", "-S", "sh", "-c", "echo 2 > /proc/sys/vm/drop_caches"]).wait()
        Popen(["sudo", "-S", "sh", "-c", "echo 3 > /proc/sys/vm/drop_caches"]).wait()
      self._runLit(testpath, llvmdir, runonly, corecnt)


  ##
  # Run Test Suite using CMake
  ##
  def test(self):
    parser = newParser("test", llvm=True, testsuite=True, run=True,
        sendmail=True, optionals=["sendmail"])
    parser.add_argument('--runonly',
        help='Run a specified test only (e.g. SingleSource/Benchmarks/Shootout)',
        action='store', required=False)
    args = parser.parse_args(sys.argv[2:])

    cfg = json.load(open(args.cfg))
    testcfg = json.load(open(args.testcfg))
    runcfg = json.load(open(args.runcfg))
    runonly = args.runonly if args.runonly else None

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
    parser = newParser("diff", llvm=True, llvm2=True, testsuite=True, run=True,
        sendmail=True, optionals=["sendmail", "testsuite"])
    parser.add_argument('--diff', action="store",
        help='Use pre-built test-suites to generate diff (format: dir1,dir2)')
    parser.add_argument('--out', help='Output file path', required=True,
                        action='store')
    args = parser.parse_args(sys.argv[2:])

    cfg1 = json.load(open(args.cfg))
    cfg2 = json.load(open(args.cfg2))
    runcfg = json.load(open(args.runcfg))

    if args.diff:
      paths = args.diff.split(',')
      testpath1 = paths[0]
      testpath2 = paths[1]
    else:
      # Build test-suite from scratch.
      assert(args.testcfg)
      testcfg = json.load(open(args.testcfg))

      assert(hasAndEquals(runcfg, "emitasm", True))

      testpath1 = self._getTestSuiteBuildPath(cfg1, testcfg, runcfg)
      testpath2 = self._getTestSuiteBuildPath(cfg2, testcfg, runcfg)

      if hasAndEquals(runcfg, "use_cset", True):
        self._initCSet();

      self._buildTestSuiteUsingCMake(testpath1, cfg1, testcfg, runcfg)
      self._buildTestSuiteUsingCMake(testpath2, cfg2, testcfg, runcfg)

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
    result1 = [os.path.join(os.path.relpath(dp, testpath1), f)
               for dp, dn, filenames in os.walk(testpath1)
               for f in filenames if os.path.splitext(f)[-1] == '.s']
    result2 = [os.path.join(os.path.relpath(dp, testpath2), f)
               for dp, dn, filenames in os.walk(testpath2)
               for f in filenames if os.path.splitext(f)[-1] == '.s']
    # The list of files should be same
    assert(set(result1) == set(result2))
    # TODO: relate 'tests' variable with results

    outf = open(args.out, "w")

    prune = lambda s: (s if s.find("#") == -1 else s[s.find("#"):]).strip()

    for asmf in result1:
      asm1 = open("%s/%s" % (testpath1, asmf), "r").readlines()
      asm2 = open("%s/%s" % (testpath2, asmf), "r").readlines()

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
            pattern = '.ident\s*\"clang version [0-9].[0-9].[0-9] \(((git\@github.com)|(https:\/\/github.com))[a-zA-Z0-9\)\( :/.-]*'
            if re.match(pattern, a1) or re.match(pattern, a2):
              continue
            else:
              hasdiff = True
              break
          else:
            hasdiff = True
            break

      outf.write("%s %s\n" % (asmf, "YESDIFF" if hasdiff else "NODIFF"))

    if args.mailcfg:
      cfg = json.load(open(args.mailcfg, "r"))
      sendMail(cfg, "diff", str(args))



  ############################################################
  #                Running SPEC benchmarks
  ############################################################
  def spec(self):
    parser = newParser("spec", llvm=True, testsuite=True, run=True, spec=True,
                       sendmail=True, optionals=["testsuite", "sendmail"])
    parser.add_argument('--testsuite', action="store_true",
        help='Use test-suite to run SPEC')
    parser.add_argument('--runonly', action="store",
        choices=["CINT2017rate", "CFP2017rate", "CINT2017speed", "CFP2017speed"],
        help='Only run this benchmark')
    args = parser.parse_args(sys.argv[2:])

    if args.testsuite:
      if not args.testcfg:
        print("--testcfg should be given to run SPEC with test-suite!")
        exit(1)

      cfg = json.load(open(args.cfg))
      testcfg = json.load(open(args.testcfg))
      runcfg = json.load(open(args.runcfg))
      speccfg = json.load(open(args.speccfg))
      runonly = "External/SPEC"
      if args.runonly:
        runonly = runonly + "/" + args.runonly

      suffix = "_SPEC2017"
      if args.runonly:
        suffix = "_" + args.runonly
      self._runTestSuiteUsingCMake(cfg, testcfg, runcfg, runonly,
                                   speccfg=speccfg, path_suffix=suffix)

    else:
      assert False, "Not implemented"

    if args.mailcfg:
      cfg = json.load(open(args.mailcfg, "r"))
      sendMail(cfg, "spec", str(args))



  ############################################################
  #           Building test-suite using LNT script
  ############################################################
  def lnt(self):
    parser = newParser("lnt", llvm=True, testsuite=True, run=True,
        sendmail=True, optionals=["sendmail"])
    args = parser.parse_args(sys.argv[2:])

    cfg = json.load(open(args.cfg))
    testcfg = json.load(open(args.testcfg))
    runcfg = json.load(open(args.runcfg))

    buildopt = runcfg["buildopt"]
    assert(buildopt == "relassert" or buildopt == "release" or buildopt == "debug")
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
        cmds = cmds + ["--multisample", runcfg["iteration"]]

    if "threads" in runcfg:
      cmds = cmds + ["--threads", str(runcfg["threads"])]
    if "build-threads" in runcfg:
      cmds = cmds + ["--build-threads", str(runcfg["build-threads"])]

    print(cmds)

    p = Popen(cmds)
    p.wait()

    if args.mailcfg:
      cfg = json.load(open(args.mailcfg, "r"))
      sendMail(cfg, "lnt", str(args))



  ############################################################
  #           Building test-suite using LNT script
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
    parser = newParser("test", llvm=True, testsuite=True, run=True, spec=True,
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
      _checkAttr("llvm" in cfg["repo"], "repo/llvm", fname, True)
      _checkAttr("clang" in cfg["repo"], "repo/clang", fname, False,
                 msg="clang is needed to run test-suite")
      _checkAttr("compiler-rt" in cfg["repo"], "repo/compiler-rt", fname, False,
                 msg="compiler-rt is needed to run test-suite with cmake")
      _checkAttr("libcxx" in cfg["repo"], "repo/libcxx", fname, False,
                 msg="using libcxx is recommended for consistent environment setting")
      _checkAttr("libcxxabi" in cfg["repo"], "repo/libcxxabi", fname, False,
                 msg="using libcxxabi is recommended for consistent environment setting")

      for prj in cfg["repo"]:
        _checkAttr("url" in cfg["repo"][prj], "repo/%s/url" % prj, fname, True)
        _checkAttr("branch" in cfg["repo"][prj], "repo/%s/branch" % prj, fname, True)

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
      _checkAttr("repo" in testcfg, "repo", fname, True)
      _checkAttr("test-suite" in testcfg["repo"], "repo/test-suite", fname, True)
      _checkAttr("lnt" in testcfg["repo"], "repo/lnt", fname, False,
                 msg="repo/lnt is needed to run test-suite with lnt")

      for prj in testcfg["repo"]:
        _checkAttr("url" in testcfg["repo"][prj], "repo/%s/url" % prj, fname, True)
        _checkAttr("branch" in testcfg["repo"][prj], "repo/%s/branch" % prj, fname, True)

    if args.runcfg:
      fname = args.runcfg
      runcfg = json.load(open(args.runcfg))

      _checkAttr("buildopt" in runcfg, "buildopt", fname, True)
      _checkAttr("benchmark" in runcfg, "benchmark", fname, True)

      if hasAndEquals(runcfg, "use_cset", True):
        _checkAttr("cset_username" in runcfg, "cset_username", fname, True,
                   msg="If use_cset = true, cset_username should be specified.")

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

    if args.sendmailcfg:
      fname = args.sendmailcfg
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


if __name__ == '__main__':
  LLVMScript()

