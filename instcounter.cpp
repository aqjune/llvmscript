// http://stackoverflow.com/questions/30195204/how-to-parse-llvm-ir-line-by-line
// http://llvm.org/docs/doxygen/html/InstCount_8cpp_source.html
#include <iostream>
#include <string>
#include <sstream>
#include <set>
#include <llvm/Support/MemoryBuffer.h>
#include <llvm/Support/ErrorOr.h>
#include <llvm/Pass.h>
#include <llvm/IR/Module.h>
#include <llvm/IR/InstVisitor.h>
#include <llvm/IR/LLVMContext.h>
#include <llvm/IR/Instructions.h>
#include <llvm/IR/Operator.h>
#include <llvm/Bitcode/BitcodeReader.h>
#include <llvm/Support/raw_ostream.h>

using namespace llvm;

namespace{
class InstCountPass : public FunctionPass, public InstVisitor<InstCountPass> {
  friend class InstVisitor<InstCountPass>;

  void visitFunction(Function &F) { 
    ++TotalFuncs;
  }
  void visitBasicBlock(BasicBlock &BB) { 
    ++TotalBlocks; 
  }

#define HANDLE_INST(N, OPCODE, CLASS) \
  void visit##OPCODE(CLASS &I) { \
    std::string str = ""#OPCODE; \
    std::string str2 = str; \
    std::transform(str.begin(), str.end(), str2.begin(), ::tolower); \
    ++NumInst[str2]; ++TotalInsts; \
    countIntrinsics(&I); visitConstExpr(&I); \
  }
#include <llvm/IR/Instruction.def>
  
  void visitInstruction(Instruction &I) {
    errs() << "Instruction Count does not know about " << I;
    llvm_unreachable(nullptr);
  }
  void countIntrinsics(Instruction *I) {
    if (IntrinsicInst *II = dyn_cast<IntrinsicInst>(I)) {
      NumIntrinsics[II->getCalledFunction()->getName()]++;
    }
  }
  void visitConstExpr(User *U) {
    if (isa<ConstantExpr>(U)) {
      ConstantExpr *CE = dyn_cast<ConstantExpr>(U);
      if (Visited.find(CE) != Visited.end()) return;
      Visited.insert(CE);
      NumConstExpr[Instruction::getOpcodeName(CE->getOpcode())]++;
    }

    for (auto I = U->op_begin(); I != U->op_end(); ++I) {
      Value *V = *I;
      if (!isa<ConstantExpr>(V)) continue;
      visitConstExpr(dyn_cast<ConstantExpr>(V));
    }
  }
public:
  static char ID;
  InstCountPass():FunctionPass(ID) { }
  
  virtual bool runOnFunction(Function &F);

  int TotalInsts = 0;
  int TotalFuncs = 0;
  int TotalBlocks = 0;

  std::set<ConstantExpr *> Visited;
  std::map<std::string, int> NumInst;
  std::map<std::string, int> NumConstExpr;
  std::map<std::string, int> NumIntrinsics;
};

bool InstCountPass::runOnFunction(Function &F) {
  visit(F);
  return false;
}

}

char InstCountPass::ID = 0;
static RegisterPass<InstCountPass> X("hello", "Hello World Pass",
                             false /* Only looks at CFG */,
                             false /* Analysis Pass */);

void printMapAsJson(const std::map<std::string, int> &m, std::stringstream &ss) {
  bool first = true;
  for (auto itr = m.begin(); itr != m.end(); itr++) {
    if (!first)
      ss << ",\n";
    ss << "\t\t\"" << itr->first << "\":" << itr->second;
    first = false;
  }
}

int main(int argc, char *argv[]){
  if (argc != 2 && argc != 3) {
    errs() << "Usage : " << argv[0] << " <.bc file>" << "\n";
    return 1;
  }

  StringRef filename = argv[1];
  LLVMContext context;

  ErrorOr<std::unique_ptr<MemoryBuffer>> fileOrErr = 
    MemoryBuffer::getFileOrSTDIN(filename);
  if (std::error_code ec = fileOrErr.getError()) {
    errs() << "Error opening input file: " << ec.message() << "\n";
    return 2;
  }
  ErrorOr<Expected<std::unique_ptr<llvm::Module>>> moduleOrErr = 
    parseBitcodeFile(fileOrErr.get()->getMemBufferRef(), context);
  if (std::error_code ec = moduleOrErr.getError()) {
    errs() << "Error reading module : " << ec.message() << "\n";
    return 3;
  }

  Expected<std::unique_ptr<llvm::Module>> moduleExpct = std::move(moduleOrErr.get());
  std::unique_ptr<Module> m;
  if (moduleExpct) {
    m = std::move(moduleExpct.get());
  } else {
    errs() << "Error reading module\n";
    return 3;
  }
  
  InstCountPass *ip = new InstCountPass();
  for (auto fitr = m->getFunctionList().begin(); 
      fitr != m->getFunctionList().end(); fitr++) {
    Function &f = *fitr;
    ip->runOnFunction(f);
  }

  std::stringstream ss;
  ss << "{\n";
  ss << "\t\"total\":" << ip->TotalInsts << ",\n";
  ss << "\t\"instrs\": {\n";
  printMapAsJson(ip->NumInst, ss);
  ss << "\n\t},\n";
  ss << "\t\"intrinsics\": {\n";
  printMapAsJson(ip->NumIntrinsics, ss);
  ss << "\n\t},\n";
  ss << "\t\"constexprs\": {\n";
  printMapAsJson(ip->NumConstExpr, ss);
  ss << "\n\t}\n";
  ss << "}";

  std::cout << ss.str();
  return 0;
}
