#!/usr/bin/env python3
"""태그 불일치 분석 스크립트"""
import json, pathlib, re, sys
sys.stdout.reconfigure(encoding='utf-8')

def normalize_text(s: str) -> str:
    return re.sub(r"[\s\-_\(\)（）·]+", "", s.lower())

EVAL_DIR = pathlib.Path(__file__).parent
golden_raw = json.loads((EVAL_DIR / "golden_dataset.json").read_text(encoding="utf-8"))
output_raw = json.loads((EVAL_DIR / "results/pipeline_output.json").read_text(encoding="utf-8"))

# golden_dataset.json 구조 확인
print("=== golden 구조 샘플 ===")
print(type(golden_raw), type(golden_raw[0] if isinstance(golden_raw, list) else None))
if isinstance(golden_raw, list):
    first = golden_raw[0]
    print("Keys:", list(first.keys()))

print()
print("=== pipeline_output 구조 샘플 ===")
if isinstance(output_raw, list):
    first_o = output_raw[0]
    print("Keys:", list(first_o.keys()))
    print("tags sample:", first_o.get("tags", [])[:5])

# golden을 id → entry 맵핑
if isinstance(golden_raw, list):
    # 리스트 형태: [{"id": "md_01", "expected": {...}, ...}]
    golden_map = {g["id"]: g for g in golden_raw}
    def get_golden_tags(g):
        return g.get("expected", {}).get("tags", [])
    def get_golden_entities(g):
        return g.get("expected", {}).get("entities", {})
else:
    golden_map = golden_raw
    def get_golden_tags(g):
        return g.get("tags", [])
    def get_golden_entities(g):
        return g.get("entities", {})

output_map = {o["golden_id"]: o for o in output_raw if o.get("golden_id")}

print()
print("=== 태그 F1 상세 분석 ===")
f1_list = []
for gid, o in sorted(output_map.items()):
    g = golden_map.get(gid)
    if not g:
        print(f"  [{gid}] GOLDEN NOT FOUND")
        continue
    exp = get_golden_tags(g)
    act = o.get("tags", [])
    if not exp:
        print(f"  [{gid}] golden tags 없음")
        continue
    exp_norm = {normalize_text(t) for t in exp}
    act_norm = {normalize_text(t) for t in act}
    tp = len(exp_norm & act_norm)
    recall = tp / len(exp_norm) if exp_norm else 1.0
    prec = tp / len(act_norm) if act_norm else 1.0
    f1 = 2*recall*prec/(recall+prec) if recall+prec else 0.0
    f1_list.append(f1)
    miss = sorted(exp_norm - act_norm)
    extra = sorted(act_norm - exp_norm)
    flag = "❌" if f1 < 0.6 else "✅"
    print(f"  {flag} [{gid}] f1={f1:.3f} R={recall:.2f} P={prec:.2f}")
    if miss:
        print(f"     MISS : {miss[:8]}")
    if extra:
        print(f"     EXTRA: {extra[:6]}")

if f1_list:
    print(f"\n  평균 tags_f1 = {sum(f1_list)/len(f1_list):.4f} (n={len(f1_list)})")

print()
print("=== 엔티티 recall 상세 분석 ===")
recall_list = []
for gid, o in sorted(output_map.items()):
    g = golden_map.get(gid)
    if not g: continue
    golden_entities = get_golden_entities(g)
    # 전체 golden entity names
    all_expected_names = [n for names in golden_entities.values() for n in names]
    if not all_expected_names:
        continue
    actual_all = {normalize_text(n) for names in o.get("entities", {}).values() for n in names}
    matched = sum(1 for n in all_expected_names if normalize_text(n) in actual_all)
    recall = matched / len(all_expected_names)
    recall_list.append(recall)
    miss_names = [n for n in all_expected_names if normalize_text(n) not in actual_all]
    flag = "❌" if recall < 0.6 else "✅"
    print(f"  {flag} [{gid}] recall={recall:.3f}  matched={matched}/{len(all_expected_names)}")
    if miss_names:
        print(f"     MISS: {miss_names[:6]}")
    # golden entity type breakdown
    for etype, names in golden_entities.items():
        found = [n for n in names if normalize_text(n) in actual_all]
        if len(found) < len(names):
            print(f"     [{etype}] {found}/{names} missing={[n for n in names if normalize_text(n) not in actual_all]}")

if recall_list:
    print(f"\n  평균 entity_name_recall = {sum(recall_list)/len(recall_list):.4f} (n={len(recall_list)})")
