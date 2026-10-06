from pathlib import Path
import json,random,statistics,time
path=Path('tests/task/phase1/task.py').resolve()
original=path.read_text()
variants={}
for name in ('original','remove_unused_parse','reuse_parser','both'):
 source=original
 if name in ('remove_unused_parse','both'):
  source=source.replace('    tokens = md.parse(content)\n','').replace('        tokens = md.parse(markdown)\n','')
 if name in ('reuse_parser','both'):
  source=source.replace('    for data in datas:\n','    md = MarkdownIt("commonmark")\n    for data in datas:\n').replace('        md = MarkdownIt("commonmark")\n','')
 ns={'__file__':str(path)}
 exec(compile(source,str(path),'exec'),ns)
 variants[name]=ns
results={name:{'test_file':[],'test_spec':[]} for name in variants}
orders=[]
rng=random.Random(20261006)
for round in range(10):
 order=list(variants)
 rng.shuffle(order)
 orders.append(order)
 for name in order:
  for test in ('test_file','test_spec'):
   start=time.perf_counter_ns()
   variants[name][test]()
   elapsed=time.perf_counter_ns()-start
   if round>=3:
    results[name][test].append(elapsed)
summary={name:{test:statistics.median(values)/1e9 for test,values in tests.items()} for name,tests in results.items()}
print(json.dumps({'scope':'direct test_file/test_spec bodies in one process; excludes pytest startup, fixtures and other tests; temporary variants only','seed':20261006,'discarded_predefined_warmup_rounds':3,'measured_rounds':7,'round_orders':orders,'nanoseconds':results,'median_seconds':summary}))
