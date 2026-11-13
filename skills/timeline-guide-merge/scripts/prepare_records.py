"""把收藏/评论导出的 HTML 整理成带标签的记录 JSON。

用法（来源文件不可信，务必用 -I 隔离模式）：
    python -I -X utf8 prepare_records.py <来源.html> <records_clean.json>

流程：解析卡片 -> 清理页面文字 -> 按作者+发布时间（到分钟）去重 -> 比对被删副本
-> 启发式打标签 -> 打印报告。标签只是提示，需由整理任务复核。
解析不到记录时以非零状态退出，说明导出格式不符，改由主会话手工处理。

换来源时只需调整下面的 CARD_RE、META_SEP 和各组页面文字规则。
"""
import collections
import html
import json
import re
import sys

# --- 来源格式与页面文字规则（换来源时改这里） ---
CARD_RE = re.compile(r'<article class="card"><div class="meta">(.*?)</div><pre>(.*?)</pre>', re.S)
DECLARED_RE = re.compile(r'(\d+) 条收藏')
META_SEP = ' · '                       # 元信息：作者 · 日期 · 赞 · 花
DATE_RE = re.compile(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}')
BUTTON_AUTHORS = {'拉黑', '删除', '精选分类', '取消精选', '精选', '举报', '回复'}  # 被误当成作者的按钮
NON_POST_RE = re.compile(r'将该精选互动分类至')                         # 元信息里出现，说明不是帖子
BODY_AUTHOR_RE = re.compile(r'^.{0,120}?发布\s*0/1500\s*', re.S)         # 其后第一行是真实作者
HEAD_CHROME = [                         # 删掉正文前面的页面文字（只匹配开头一小段，避免吃掉正文）
    r'^.{0,120}?发布\s*0/1500\s*',
    r'^.{0,120}?阅读时长：\d+h\+\s*',
]
TAIL_CHROME = [                         # 删掉正文后面的页面文字
    r'(展开)?\s*\n\s*[一-龥]{2,4}\s*来自：.*$',   # IP 属地 + 来自
    r'(展开)?\s*来自：.*$',
    r'展开\s*$',
    r'\s*\d*\s*(置顶\s*)?回复\(\d+\)[\s\S]*$',
    r'\s*\d+\s*分享\s*举报\s*$',
]
LEFTOVER_RE = re.compile(r'拉黑|阅读时长|0/1500|取消精选|精选分类')       # 清理后不应再出现
# --- 标签规则 ---
FANFIC_RE = re.compile(r'#?同人(作品)?#|同人文|番外')
REVISED_RE = re.compile(r'改版|更新后|新版|已修|修复|版本更新|旧版|早期')
QUESTION_RE = re.compile(r'求(问|助|教)|请问|怎么(办|才|样)|有没有.{0,8}[？?]|[？?]\s*$')
NUMBERED_RE = re.compile(r'(^|\n)\s*\d+[.、．]')

norm = lambda s: re.sub(r'\s+', '', s)


def parse_cards(text):
    records, skipped = [], []
    for i, (meta, body) in enumerate(CARD_RE.findall(text), 1):
        meta = html.unescape(re.sub(r'<[^>]+>', '', meta)).strip()
        body = html.unescape(body)
        parts = [p.strip() for p in meta.split(META_SEP)]
        if NON_POST_RE.search(meta):
            skipped.append((i, '非帖子卡片', meta[:30]))
        elif len(parts) < 2 or not DATE_RE.match(parts[1]):
            skipped.append((i, '无作者/日期（简介等）', meta[:30]))
        else:
            records.append({'id': i, 'author': parts[0][:40], 'date': parts[1], 'text': body})
    return records, skipped


def strip_chrome(t):
    for pat in HEAD_CHROME:
        t = re.sub(pat, '', t, count=1, flags=re.S)
    for pat in TAIL_CHROME:
        t = re.sub(pat, '', t, flags=re.S).strip()
    n = len(t)
    if n % 2 == 0 and t[:n // 2] == t[n // 2:]:  # 整段重复一遍
        t = t[:n // 2]
    return t.strip()


def author_of(r, fixed):
    if r['author'] not in BUTTON_AUTHORS:
        return r['author']
    body = BODY_AUTHOR_RE.sub('', r['text'], count=1).strip()
    real = body.splitlines()[0].strip() if body else r['author']
    fixed.append((r['id'], r['author'], real))
    return real


def tags_of(raw, clean):
    tags = []
    if FANFIC_RE.search(clean[:200]):
        tags.append('同人')
    elif '阅读时长' in raw and not NUMBERED_RE.search(clean):
        tags.append('长评')
    elif QUESTION_RE.search(clean) and len(clean) < 300:
        tags.append('问答')
    else:
        tags.append('攻略')
    if REVISED_RE.search(clean):
        tags.append('提到改版')
    return tags


def main():
    if len(sys.argv) != 3:
        sys.exit('用法: python -I -X utf8 prepare_records.py <来源.html> <输出.json>')
    src, out = sys.argv[1:]
    text = open(src, encoding='utf-8').read()
    m = DECLARED_RE.search(text)
    declared = int(m.group(1)) if m else None
    cards, skipped = parse_cards(text)
    if not cards:
        sys.exit('解析不到任何记录：导出格式与脚本不符，请改由主会话手工处理，或调整脚本顶部的规则。')

    fixed = []
    groups = collections.OrderedDict()
    for r in cards:
        groups.setdefault((author_of(r, fixed), r['date'][:16]), []).append(r)

    records, suspects = [], []
    for (author, date), rs in groups.items():
        cleaned = [strip_chrome(r['text']) for r in rs]
        # 优先保留有换行的版本：页面复制的副本通常被压成一行
        best_i = max(range(len(rs)), key=lambda k: (cleaned[k].count('\n') > 3, len(norm(cleaned[k]))))
        best, base = cleaned[best_i], len(norm(cleaned[best_i]))
        for r, c in zip(rs, cleaned):
            if c is best:
                continue
            nc = norm(c)
            ratio = len(nc) / max(base, 1)
            nb = norm(best)
            # 开头和结尾各取一段对比，容忍副本末尾多出的“展开”“IP 属地”等页面字
            same = bool(nc) and (nc in nb or (nb[:80] in nc and nb[-60:-10] in nc))
            # 页面副本常把折叠预览和展开全文各放一遍，正文翻倍但仍包含保留版本
            if not same or not 0.9 < ratio < 2.2:
                suspects.append((author, date, r['id'], len(nc), base, round(ratio, 2)))
        records.append({'id': len(records) + 1, 'author': author, 'date': date,
                        'source_ids': [r['id'] for r in rs], 'chars': len(best),
                        'tags': tags_of(rs[best_i]['text'], best), 'text': best})

    json.dump(records, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    print(f'声明条数: {declared}  解析卡片: {len(cards) + len(skipped)}  '
          f'跳过: {len(skipped)}  帖子: {len(cards)}  去重后保留: {len(records)}')
    for i, why, head in skipped:
        print(f'  跳过 #{i} {why}: {head!r}')
    for i, old, new in fixed:
        print(f'  作者修正 #{i}: {old!r} -> {new!r}')
    dups = [r for r in records if len(r['source_ids']) > 1]
    print(f'去重: {len(dups)} 条合并了副本')
    for r in dups:
        print(f'  {r["id"]} {r["author"]} {r["date"]} 来源 {r["source_ids"]} 末尾 {r["text"][-30:]!r}')
    if suspects:
        print('需人工核对的被删副本（长度或内容与保留版本不一致）:')
        for s in suspects:
            print('  作者=%s 时间=%s 来源#%s 副本字数=%s 保留字数=%s 比例=%s' % s)
    else:
        print('被删副本与保留版本比对一致')
    authors = collections.Counter(r['author'] for r in records)
    print(f'作者分布: {len(authors)} 位')
    for a, n in authors.most_common():
        flag = '  <-- 检查是否真是作者' if len(a) > 20 or a in BUTTON_AUTHORS else ''
        print(f'  {n} {a}{flag}')
    tag_count = collections.Counter(t for r in records for t in r['tags'])
    print('标签分布:', dict(tag_count))
    left = [r['id'] for r in records if LEFTOVER_RE.search(r['text']) or LEFTOVER_RE.search(r['author'])]
    print('残留页面文字的记录:', left or '无')
    print(f'总字数: {sum(r["chars"] for r in records)}  输出: {out}')


if __name__ == '__main__':
    main()
