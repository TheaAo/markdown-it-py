from pathlib import Path
import sys
sys.path.insert(0, '/Users/ruoyur/Code/Chalmers/MasterThesis/markdown-it-py')
from scripts.collect_execution_time import _timed_pytest, _controlled_environment
from dataclasses import asdict
import difflib, io, json, statistics, subprocess, tarfile, tempfile
import xml.etree.ElementTree as ET
repo=Path('/Users/ruoyur/Code/Chalmers/MasterThesis/markdown-it-py')
sha='18fd41b1b12246ff35950dd17fac7de826da9cd9'
output=repo/'results/phase2/execution_time/diagnostics/experiment-05'
output.mkdir(parents=True, exist_ok=True)
raw=json.loads((repo/'results/phase2/execution_time/formal/raw/experiment-05.json').read_text())
nodes=raw['execution_time']['selected_nodeids']
report={'purpose':'Diagnostic temporary-copy ablation; does not replace participant results.', 'participant_commit':sha,'python_executable':sys.executable,'nodes':nodes,'warmup_count':3,'measurement_count':7,'variants':{}}
archive=subprocess.check_output(['git','archive',sha],cwd=repo)
for variant in ('original','remove_unused_parse','reuse_parser','both'):
 with tempfile.TemporaryDirectory(prefix='phase2-diagnose05-') as tmp:
  checkout=Path(tmp)
  with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
   tar.extractall(checkout,filter='data')
  path=checkout/'tests/task/phase1/task.py'
  original=path.read_text()
  changed=original
  if variant in ('remove_unused_parse','both'):
   assert changed.count('    tokens = md.parse(content)\n')==1
   assert changed.count('        tokens = md.parse(markdown)\n')==1
   changed=changed.replace('    tokens = md.parse(content)\n','').replace('        tokens = md.parse(markdown)\n','')
  if variant in ('reuse_parser','both'):
   assert changed.count('    for data in datas:\n')==1
   assert changed.count('        md = MarkdownIt("commonmark")\n')==1
   changed=changed.replace('    for data in datas:\n','    md = MarkdownIt("commonmark")\n    for data in datas:\n').replace('        md = MarkdownIt("commonmark")\n','')
  path.write_text(changed)
  (output/f'{variant}.patch').write_text(''.join(difflib.unified_diff(original.splitlines(True),changed.splitlines(True),fromfile='original',tofile=variant)))
  runs=[]
  for phase,count in (('warmup',3),('measurement',7)):
   for index in range(1,count+1):
    run=_timed_pytest(python_executable=sys.executable,repo_root=checkout,nodeids=nodes,timeout=120,phase=phase,index=index)
    assert run.returncode==0 and not run.timed_out,run.failure_output
    runs.append(asdict(run))
  values=[r['elapsed_nanoseconds']/1e9 for r in runs if r['phase']=='measurement']
  result={'runs':runs,'median_seconds':statistics.median(values),'cv':statistics.stdev(values)/statistics.mean(values)}
  if variant=='original':
   result_xml=output/'original_pytest.xml'
   p=subprocess.run([sys.executable,'-m','pytest','-q','-p','no:cacheprovider',f'--junitxml={result_xml}',*nodes],cwd=checkout,env=_controlled_environment(),capture_output=True,text=True)
   assert p.returncode==0,p.stdout
   result['pytest_case_seconds']=[{'name':c.attrib['name'],'seconds':float(c.attrib['time'])} for c in ET.parse(result_xml).iter('testcase')]
  report['variants'][variant]=result
  print(variant,result['median_seconds'],result['cv'],flush=True)
(output/'diagnostic_results.json').write_text(json.dumps(report,indent=2)+'\n')
(output/'diagnostic_runner.py').write_text(Path(__file__).read_text())
