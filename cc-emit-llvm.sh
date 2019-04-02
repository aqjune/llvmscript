#!/bin/bash
params=("$@")
params2=( ) # -o updated
i2=0
dest=
for ((i=0; i < $#; i++)); do
  if [ "${params[i]}" == "-o" ]; then
    i=$((i+1))
    dest=${params[i]}
  else
    params2[i2]=${params[i]}
    i2=$((i2+1))
  fi
done

[[CLANG]] -c -emit-llvm [[PARAM]] ${params2[@]} -o "${dest}.bc"
[[CLANG]] ${params[@]}
