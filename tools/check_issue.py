#!/usr/bin/env python3
"""Pre-send checks for a built Literature Deep Dive issue (ported from the Neurodynamics Digest's check_issue.py, retuned for Amy).
Checks: compact size limit, no CJK text, no neuroscience/psychedelic content, only the +deepdive contact address,
no Neurodynamics/Patrick/Mochi mix-ups, light ocean palette (no dark page backgrounds), Nudibranchi sign-off,
and from Issue 004 on: a 'Catch-up' section that is the LAST section, with 5 items (ported from Patrick's 9 Nov 2026 check).
Usage: python3 build/check_issue.py issue-003/issue-003-compact.html [issue-003/issue-003.html issue-003/issue-003.txt]"""
import re, sys, os
MAIL = "pk-neuro-digest+deepdive@mail.grokbot.com"
OK_TEXT = {"<RECIPIENT_EMAIL>"}  # Amy's own address may be named in text ("Replies from ..."), never as a mailto
NEURO = re.compile(r"\b(psychedel\w*|psilocybin|ayahuasca|mescaline|LSD|DMT|ketamine|neuroscien\w*|fMRI|EEG|hippocamp\w*|cortical|neurotransmit\w*|telencephal\w*)\b", re.I)
CATCHUP_FROM = 4  # Catch-up starts with Issue 004 (Issues 001-003 predate it)
MIXUP = re.compile(r"Neurodynamics|Mochi|Patrick|Pattricksk", re.I)
bad = 0
for f in sys.argv[1:]:
    s = open(f, encoding="utf-8").read(); kb = os.path.getsize(f) / 1024; msgs = []
    if f.endswith("compact.html") and kb > 80: msgs.append(f"compact HTML is {kb:.1f} KB (hard limit 80, target <60)")
    if re.search(r"[\u2E80-\u2FFF\u3000-\u30FF\u3100-\u9FFF\uAC00-\uD7AF\uF900-\uFAFF\uFF00-\uFFEF]", s): msgs.append("CJK characters found")
    m = sorted(set(x.group(0) for x in NEURO.finditer(s)))
    if m: msgs.append("neuroscience/psychedelic terms: " + ", ".join(m[:8]))
    addrs = set(a.lower() for a in re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", s))
    other = sorted(a for a in addrs if a != MAIL and a not in OK_TEXT)
    other += sorted(set("mailto:" + a.lower() for a in re.findall(r"mailto:([\w.+-]+@[\w.-]+)", s, re.I) if a.lower() != MAIL))
    if other: msgs.append("unexpected email address(es): " + ", ".join(other))
    if "pk-neuro-digest@" in s.lower(): msgs.append("Patrick's unsuffixed address found")
    m = sorted(set(x.group(0) for x in MIXUP.finditer(s)))
    if m: msgs.append("possible digest mix-up: " + ", ".join(m))
    if f.endswith(".html") and re.search(r'<body[^>]*(bgcolor="#(0|1)[0-9a-f]{5}"|background(-color)?:\s*#(0|1)[0-9a-f]{5})', s, re.I): msgs.append("dark body background (Amy's style is light ocean)")
    if "Nudibranchi" not in s: msgs.append("missing Nudibranchi sign-off")
    n = re.search(r"issue-(\d{3})", os.path.basename(f))
    if n and int(n.group(1)) >= CATCHUP_FROM:
        if f.endswith(".html"):
            secs = re.findall(r'data-section="([^"]+)"', s)
            if "Catch-up" not in secs: msgs.append("missing 'Catch-up' section")
            elif secs[-1] != "Catch-up": msgs.append("'Catch-up' must be the last section (last is %r)" % secs[-1])
            else:
                tail = s[s.rfind('data-section="Catch-up"'):]
                # full/web copy: 5 cards with SINCE THEN rows; compact email: 5 condensed pointer bullets
                k = tail.count("SINCE THEN") if not f.endswith("compact.html") else tail[:tail.find("data-section", 30) if tail.find("data-section", 30) > 0 else len(tail)].count("&bull; <a")
                if k != 5: msgs.append(f"Catch-up has {k} items (expected exactly 5)")
        elif f.endswith(".txt") and "CATCH-UP" not in s: msgs.append("missing 'Catch-up' in plain text")
    print(f"{f}: {kb:.1f} KB", "OK" if not msgs else "; ".join(msgs)); bad += len(msgs)
sys.exit(1 if bad else 0)
