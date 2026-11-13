"""Machine checks of a finished guide against the source records.

Usage:
  python -I -X utf8 check_guide.py <records_clean.json> <guide.md>...

For each guide prints:
  - numbers of 3+ digits that appear nowhere in the source (years 2010-2029 are skipped)
  - quoted text (“…”) that is not in the source, with a 3-gram overlap score; low scores
    are likely invented or heavily rewritten quotes, high scores are usually paraphrase
  - "做法（作者）" clauses naming one author whose 2+ digit numbers are not in that
    author's own records (wrong attribution, or a number taken from another author)
Everything printed is a lead to look up in the source, not a verdict.
"""
import json
import re
import sys

PUNCT = r"[\s，,。.、：:；;！!？?（）()\"“”‘’…—\-~～*＋+＝=/／【】\[\]「」『』·]"


def norm(s):
    return re.sub(PUNCT, "", s)


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    records = json.load(open(argv[0], encoding="utf-8"))
    raw = "\n".join(r.get("text", "") for r in records)
    flat = raw.replace(",", "").replace("，", "")
    src = norm(raw)
    by_author = {}
    for r in records:
        by_author[r["author"]] = by_author.get(r["author"], "") + r.get("text", "").replace(",", "").replace("，", "")
    names = sorted(by_author, key=len, reverse=True)

    for path in argv[1:]:
        text = open(path, encoding="utf-8").read()
        print("=====", path)

        nums = sorted(set(re.findall(r"\d{3,}", text.replace(",", ""))))
        miss = [n for n in nums if n not in flat and not re.fullmatch(r"20[12]\d", n)]
        print("numbers: {} checked, not in source: {}".format(len(nums), miss or "none"))

        quotes = re.findall(r"“([^”\n]{6,120})”", text)
        for line in text.splitlines():  # straight quotes: only lines where they pair up
            parts = line.split('"')
            if len(parts) > 1 and len(parts) % 2 == 1:
                quotes += [p for p in parts[1::2] if 6 <= len(p) <= 120]
        weak = []
        for q in quotes:
            n = norm(q)
            if len(n) < 4 or n in src:
                continue
            grams = [n[i:i + 3] for i in range(len(n) - 2)] or [n]
            score = sum(g in src for g in grams) / len(grams)
            weak.append((score, q))
        print("quotes: {} checked, not verbatim: {}".format(len(quotes), len(weak)))
        for score, q in sorted(weak):
            print("  {:.2f} {}".format(score, q))

        checked, flagged = 0, []
        for ln, line in enumerate(text.splitlines(), 1):
            line = re.sub(r"20[12]\d[-./年]\d{1,2}(?:[-./月]\d{1,2})?", " ", line)  # publish dates are not game data
            for m in re.finditer(r"([^；;。\n（(]{4,120})[（(]([^）)]{2,40})[）)]", line):
                body, par = m.groups()
                authors = [a for a in names if a in par]
                if len(authors) != 1:
                    continue
                ns = [x for x in re.findall(r"\d{2,}", body.replace(",", "")) if not re.fullmatch(r"20[12]\d", x)]
                if not ns:
                    continue
                checked += 1
                bad = [x for x in ns if x not in by_author[authors[0]]]
                if bad:
                    flagged.append("  line {} {} {} | {}".format(ln, authors[0], bad, body.strip()[:90]))
        print("single-author numbers: {} clauses checked, {} flagged".format(checked, len(flagged)))
        print("\n".join(flagged))


if __name__ == "__main__":
    main(sys.argv[1:])
