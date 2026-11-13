"""Check that a reading ledger covers every record, and look for records a guide may have missed.

Usage:
  python -I -X utf8 check_coverage.py <records_clean.json> <ledger.tsv>... \
      [--guide 阶段=guide.md]... [--stage 阶段=正则]...

Ledger lines (tab separated, header and blank lines optional):
  id    状态    阶段    备注
状态 is one of: 用了 / 不相关 / 同人 / 无攻略信息. 阶段 lists the stages a used record
belongs to, separated by "," (e.g. "高一,高二"); it may be empty for other states.

Reports, and exits 1 when any of the first three is non-empty:
  - record ids missing from every ledger, and ids listed more than once
  - lines with an unknown 状态 or an id that is not a record
  - records marked 用了 for a stage whose author never appears in that stage's guide
  - (review list) records matching a --stage regex that no ledger assigns to that stage
"""
import json
import re
import sys
from collections import Counter, defaultdict

STATES = {"用了", "不相关", "同人", "无攻略信息"}


def parse_pairs(argv, flag):
    out = {}
    for i, a in enumerate(argv):
        if a == flag and i + 1 < len(argv):
            k, _, v = argv[i + 1].partition("=")
            out[k.strip()] = v
    return out


def main(argv):
    guides = parse_pairs(argv, "--guide")
    stages = parse_pairs(argv, "--stage")
    skip = set()
    for i, a in enumerate(argv):
        if a in ("--guide", "--stage"):
            skip.update((i, i + 1))
    pos = [a for i, a in enumerate(argv) if i not in skip]
    if len(pos) < 2:
        sys.exit(__doc__)
    records = json.load(open(pos[0], encoding="utf-8"))
    by_id = {str(r["id"]): r for r in records}

    seen = Counter()
    status = {}
    rec_stages = defaultdict(set)
    bad_lines = []
    for path in pos[1:]:
        for n, line in enumerate(open(path, encoding="utf-8"), 1):
            line = line.rstrip("\n")
            if not line.strip() or line.startswith("id\t"):
                continue
            cols = line.split("\t")
            rid = cols[0].strip().lstrip("#")
            st = cols[1].strip() if len(cols) > 1 else ""
            if rid not in by_id or st not in STATES:
                bad_lines.append("{}:{}: {}".format(path, n, line[:80]))
                continue
            seen[rid] += 1
            status[rid] = st
            if len(cols) > 2:
                rec_stages[rid].update(s.strip() for s in re.split(r"[,，、]", cols[2]) if s.strip())

    missing = [i for i in by_id if seen[i] == 0]
    dupes = [i for i, c in seen.items() if c > 1]
    print("records: {}  in ledger: {}  missing: {}  duplicated: {}  bad lines: {}".format(
        len(by_id), len(seen), len(missing), len(dupes), len(bad_lines)))
    if missing:
        print("  missing ids:", " ".join(missing))
    if dupes:
        print("  duplicated ids:", " ".join(dupes))
    for b in bad_lines:
        print("  bad line:", b)
    print("  states:", dict(Counter(status.values())))

    unattributed = []
    for stage, path in guides.items():
        text = open(path, encoding="utf-8").read()
        for rid, st in status.items():
            if st == "用了" and stage in rec_stages[rid] and by_id[rid]["author"] not in text:
                unattributed.append((stage, rid, by_id[rid]["author"]))
    if unattributed:
        print("used but author absent from guide ({}):".format(len(unattributed)))
        for stage, rid, au in unattributed:
            print("  [{}] #{} {}".format(stage, rid, au))

    for stage, pattern in stages.items():
        rx = re.compile(pattern)
        review = []
        for rid, r in by_id.items():
            m = rx.search(r.get("text", ""))
            if m and stage not in rec_stages[rid]:
                s = max(0, m.start() - 30)
                review.append("  #{} {} [{}] …{}…".format(rid, r["author"], status.get(rid, "?"),
                                                         r["text"][s:m.end() + 30].replace("\n", " ")))
        print("review [{}]: {} records match /{}/ but are not assigned to it".format(stage, len(review), pattern))
        print("\n".join(review[:80]))
        if len(review) > 80:
            print("  … {} more".format(len(review) - 80))

    sys.exit(1 if (missing or dupes or bad_lines or unattributed) else 0)


if __name__ == "__main__":
    main(sys.argv[1:])
