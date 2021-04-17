import argparse
import os
import re
import sys

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

def diffDirs(path1, path2, emitasm, outf):
  ext = '.s' if emitasm else '.bc'
  result1 = [os.path.join(os.path.relpath(dp, path1), f)
              for dp, dn, filenames in os.walk(path1)
              for f in filenames if os.path.splitext(f)[-1] == ext]
  result2 = [os.path.join(os.path.relpath(dp, path2), f)
              for dp, dn, filenames in os.walk(path2)
              for f in filenames if os.path.splitext(f)[-1] == ext]
  # The list of files should be same
  assert(set(result1) == set(result2))
  print("Total %d %s pairs found" % (len(result1), ext))
  # TODO: relate 'tests' variable with results

  cnt = 0
  for asmf in result1:
    cnt = cnt + 1
    asmpath1 = "%s/%s" % (path1, asmf)
    asmpath2 = "%s/%s" % (path2, asmf)
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

class DiffUtil:
  def __init__(self):
    parser = argparse.ArgumentParser(
      usage = '''python3 diffutil.py <command> [<args>]

Commands:
asm     Get assembly diffs
ll      Get LLVM .ll file diffs
''')

    parser.add_argument('command', help='')
    args = parser.parse_args(sys.argv[1:2])
    if not hasattr(self, args.command):
      print ("Unrecognized command")
      parser.print_help()
      exit(1)
    getattr(self, args.command)()

  def asm(self):
    parser = argparse.ArgumentParser(
      description = """
Diffs assembly outputs from two directories.
""")
    parser.add_argument('dir1', help='directory 1')
    parser.add_argument('dir2', help='directory 2')
    parser.add_argument('--out', help='Output file path', required=True,
                        action='store')
    args = parser.parse_args(sys.argv[2:])

    testpath1 = args.dir1
    testpath2 = args.dir2
    print(testpath1)
    print(testpath2)
    diffDirs(testpath1, testpath2, True, open(args.out, "w"))

  def ll(self):
    pass

if __name__ == '__main__':
  DiffUtil()