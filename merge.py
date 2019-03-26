#!/usr/bin/python3
import os
import sys
import json
import collections

def median(l):
  ls = sorted(l)
  n = len(ls)
  if n % 2 == 1:
    return ls[n // 2]
  return (ls[n] + ls[n - 1]) / 2.0

def assert_keyseq(dicts):
  ks = [set(d.keys()) for d in dicts]
  for i in range(1, len(dicts)):
    assert(ks[0] == ks[i])

def assert_elemeq(dicts, key):
  for i in range(1, len(dicts)):
    assert (dicts[0][key] == dicts[i][key]), \
           "Value does not match: %s != %s" % (dicts[0][key], dicts[i][key])

def median_test(ts):
  tn = len(ts)

  assert_keyseq(ts)
  assert(ts[0].keys() == set(["code", "elapsed", "metrics", "name", "output"]))
  assert_elemeq(ts, "code")
  assert_elemeq(ts, "output")
  assert_elemeq(ts, "name")

  res = collections.OrderedDict()
  res["code"] = ts[0]["code"]

  if ts[0]["elapsed"] == None:
    assert_elemeq(ts, "elapsed")
    res["elapsed"] = None
  else:
    res["elapsed"] = median([t["elapsed"] for t in ts])

  metrics = [t["metrics"] for t in ts]
  assert_keyseq(metrics)
  metric = collections.OrderedDict()
  res["metrics"] = metric

  res["name"] = ts[0]["name"]
  res["output"] = ts[0]["output"]

  for k in sorted(metrics[0].keys()):
    if k == "exec_time" or k == "compile_time" or k == "link_time":
      metric[k] = median([m[k] for m in metrics])
    else:
      assert_elemeq(metrics, k)
      metric[k] = metrics[0][k]

  return res


if len(sys.argv) < 3:
  print("Merges results of test-suite runs")
  print("python3 merge.py output.json result1.json result2.json ..")
  exit(1)


data = []
for fname in sys.argv[2:]:
  data.append(json.load(open(fname)))

n = len(data)
merged = dict()

# __version__ should be the same
for i in range(1, n):
  assert(data[0]["__version__"] == data[i]["__version__"])

merged["__version__"] = data[0]["__version__"]
merged["elapsed"] = median([d["elapsed"] for d in data])
tests = [d["tests"] for d in data]
tests_res = []
merged["tests"] = tests_res

tn = len(tests[0])

for i in range(0, tn):
  res = median_test([t[i] for t in tests])
  tests_res.append(res)

with open(sys.argv[1], "w") as outfile:
  json.dump(merged, outfile, indent=4)
