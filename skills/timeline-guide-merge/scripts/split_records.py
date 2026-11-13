"""Split a records JSON into fixed-size text parts so every record is read in full.

Usage:
  python -I -X utf8 split_records.py <records_clean.json> <out_dir> [--chars 30000]

Writes <out_dir>/partNN.txt (each record headed "=== 记录#id | 作者 | 日期 | tags ===")
and <out_dir>/parts.tsv (part, first id, last id, record count, chars), then prints the
same table. Records are never split across parts; a single record longer than --chars
gets a part of its own.
"""
import json
import os
import sys


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    limit = 30000
    if "--chars" in argv:
        limit = int(argv[argv.index("--chars") + 1])
        args = [a for a in args if a != str(limit)]
    if len(args) != 2:
        sys.exit(__doc__)
    src, out_dir = args
    records = json.load(open(src, encoding="utf-8"))
    if not records:
        sys.exit("no records in " + src)
    os.makedirs(out_dir, exist_ok=True)

    parts, cur, size = [], [], 0
    for rec in records:
        block = "=== 记录#{} | 作者：{} | 日期：{} | tags：{} ===\n{}\n\n".format(
            rec.get("id"), rec.get("author"), rec.get("date"), rec.get("tags"), rec.get("text", ""))
        if cur and size + len(block) > limit:
            parts.append(cur)
            cur, size = [], 0
        cur.append((rec, block))
        size += len(block)
    if cur:
        parts.append(cur)

    rows = ["part\tfirst_id\tlast_id\trecords\tchars"]
    for i, part in enumerate(parts, 1):
        name = "part{:02d}.txt".format(i)
        text = "".join(b for _, b in part)
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as f:
            f.write(text)
        rows.append("{}\t{}\t{}\t{}\t{}".format(name, part[0][0].get("id"), part[-1][0].get("id"), len(part), len(text)))
    with open(os.path.join(out_dir, "parts.tsv"), "w", encoding="utf-8") as f:
        f.write("\n".join(rows) + "\n")
    print("\n".join(rows))
    print("records: {}  parts: {}  total chars: {}".format(
        len(records), len(parts), sum(len(b) for p in parts for _, b in p)))


if __name__ == "__main__":
    main(sys.argv[1:])
