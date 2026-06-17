import json, pathlib, sys
sys.stdout.reconfigure(encoding='utf-8')
output = json.loads(pathlib.Path('tests/eval/results/pipeline_output.json').read_text(encoding='utf-8'))
print(f'총 {len(output)}개')
for o in output:
    gid = o.get('golden_id', '?')
    status = o.get('status', '?')
    error = str(o.get('error', ''))[:100]
    print(f'  [{gid}] status={status}  error={error}')
