#!/usr/bin/env python3
"""Never-repeat check for Catch-up picks (ported from Patrick's 4-5 Nov 2026 Catch-up rule, retuned for Amy).
Checks each candidate DOI or title against catchup-log.jsonl, archive/items.jsonl, archive/shortlist.jsonl and sent-log.md.
Usage: python3 build/catchup_check.py 10.1073/pnas.1719367115 "Some paper title" ...   (exit 1 if any is already used)"""
import json, re, sys, html, os
ROOT = "/workspace/amy-digest"
def norm(t): return re.sub(r"[^a-z0-9]", "", html.unescape(t or "").lower())
dois, titles = {}, {}
def add(src, doi, title):
    if doi: dois.setdefault(doi.lower().strip(), src)
    if title and len(norm(title)) > 20: titles.setdefault(norm(title)[:80], src)
for f, src in (("catchup-log.jsonl", "catchup-log"), ("archive/items.jsonl", "archive"), ("archive/shortlist.jsonl", "shortlist")):
    p = os.path.join(ROOT, f)
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            if line.strip():
                o = json.loads(line); add(src + (" (known)" if o.get("known") else ""), o.get("doi"), o.get("title"))
sent = open(os.path.join(ROOT, "sent-log.md"), encoding="utf-8").read().lower()
bad = 0
for q in sys.argv[1:]:
    ql = q.lower().strip(); hit = None
    if ql.startswith("10."): hit = dois.get(ql) or ("sent-log" if ql in sent else None)
    else: hit = titles.get(norm(q)[:80]) or next((s for t, s in titles.items() if len(norm(q)) > 30 and norm(q)[:60] in t), None)
    print(("USED in " + hit if hit else "ok") + "  " + q); bad += bool(hit)
sys.exit(1 if bad else 0)
