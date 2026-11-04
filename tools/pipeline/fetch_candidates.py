#!/usr/bin/env python3
"""Version B candidate finder for Amy's Literature Deep Dive (ecology x AI; ported from the Neurodynamics Digest pipeline, Nov 2026).
Queries free scholarly APIs for the window (PubMed, Europe PMC, OpenAlex, bioRxiv, arXiv incl. filtered cs.CV/eess.AS,
EcoEvoRxiv, Crossref ecology/methods journals, Zenodo datasets), dedupes against the archive/shortlist/sent-log, scores cheaply
(keyword weights by brief priority, data modality video>acoustic>other, lab-corner researchers, venue, TF-IDF similarity
to the archive, learned preferences) and writes out/<end>/candidates.json, candidates.md, reviews.json, pool.jsonl, stats.json.

Usage: python3 fetch_candidates.py --start 2026-10-19 --end 2026-10-25 [--sources pubmed,europepmc,...] [--top 60]
"""
import argparse, json, math, os, re, sys, time, datetime as dt
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import HERE, NEWS, norm_doi, norm_title, strip_accents, load_jsonl, daterange_ok
import sources

ALL_SOURCES = ["pubmed", "europepmc", "openalex", "biorxiv", "arxiv", "ecoevorxiv", "crossref_journals", "zenodo"]
BULK = ("biorxiv", "medrxiv", "arxiv", "ecoevorxiv", "crossref")
DROP_RE = re.compile(r"^(occurrence download$|abstracts? (of|from)|proceedings of|abstract book|correction|corrigendum|erratum|retraction|retracted|expression of concern|withdrawn|notice of|author correction|publisher correction)", re.I)
DROP_PT = {"Congress", "Published Erratum", "Retraction of Publication", "Retracted Publication", "Expression of Concern", "erratum", "retraction", "paratext"}
LOW_PT = {"Editorial", "Comment", "Letter", "News", "editorial", "letter", "comment", "Interview", "Biography", "Congress"}
REVIEW_PT = {"Review", "Systematic Review", "Meta-Analysis", "Scoping Review", "review", "systematic-review", "meta-analysis",
             "review-article", "Review article", "Research Support, Review", "Practice Guideline"}
REVIEW_TITLE_RE = re.compile(r"\b(review|meta-analys[ie]s|meta-analytic|systematic review|scoping review|umbrella review|perspective|primer|"
                             r"state of the art|roadmap|tutorial|narrative synthesis|overview)\b", re.I)
REVIEW_ABS_RE = re.compile(r"\b(this review|we review|in this perspective|this perspective|we systematically reviewed|systematic search of|"
                           r"meta-analysis of|we searched (pubmed|medline|embase|web of science))\b", re.I)

def log(*a):
    print(time.strftime("%H:%M:%S"), *a, file=sys.stderr, flush=True)

# ---------------- exclusion sets ----------------
def exclusions():
    dois, titles = set(), set()
    for f in ("archive/items.jsonl", "archive/shortlist.jsonl"):
        for r in load_jsonl(os.path.join(NEWS, f)):
            if r.get("doi"):
                dois.add(norm_doi(r["doi"]))
            m = re.search(r"10\.\d{4,9}/\S+", r.get("url") or "")
            if m:
                dois.add(norm_doi(m.group(0)))
            if r.get("title"):
                titles.add(norm_title(r["title"]))
    sl = os.path.join(NEWS, "sent-log.md")
    if os.path.exists(sl):
        for m in re.finditer(r"10\.\d{4,9}/[^\s)\]>\"'<,;]+", open(sl, encoding="utf-8").read()):
            dois.add(norm_doi(m.group(0)))
    return dois, titles

# ---------------- preferences ----------------
def preferences():
    p = os.path.join(NEWS, "preferences.md")
    liked, disliked = [], []
    if not os.path.exists(p):
        return liked, disliked
    sec = None
    for line in open(p, encoding="utf-8"):
        if line.startswith("## "):
            sec = "liked" if "Liked" in line else "disliked" if "Disliked" in line else None
            continue
        if line.lstrip().startswith("<!--"):
            continue
        m = re.match(r"\s*-?\s*\d{4}-\d{2}-\d{2}\s*\|\s*([^|]+)\|(.+)", line)   # Patrick-style: date | signal | rest
        m2 = re.match(r"\s*-?\s*\d{4}-\d{2}-\d{2}\s*·\s*(.+?)(?:\s*·\s*([^·|]+))?\s*$", line)   # Amy-style: date · title | ... · signal
        if m and sec:
            sig, rest = m.group(1).upper(), m.group(2).replace("|", " ")
        elif m2 and sec:
            sig, rest = (m2.group(2) or ("NOT INTERESTED" if sec == "disliked" else "STAR")).upper(), m2.group(1).replace("|", " ")
        else:
            m = None
        if (m or m2) and sec:
            if "NOT INTERESTED" in sig or sec == "disliked":
                disliked.append(rest)
            else:
                w = 0.4 if sig.strip().startswith("READ") else 1.0
                if "UN-STAR" in sig or "RESTORED" in sig:
                    continue
                liked.append((rest, w))
    return liked, disliked

# ---------------- TF-IDF ----------------
STOP = set("the a an of and or in on for to with by from at as is are was were be been this that these those we our their its into than not no "
           "using use used based study studies via between within across during after before over under both more less can may also which "
           "it they there here such data results result effects effect show shows showed new two one".split())
def toks(s):
    return [w for w in re.findall(r"[a-z][a-z0-9\-]{2,}", strip_accents(s).lower()) if w not in STOP]

class Tfidf:
    def __init__(self, docs):
        self.df = Counter()
        for d in docs:
            self.df.update(set(toks(d)))
        self.n = max(1, len(docs))
    def vec(self, s):
        tf = Counter(toks(s))
        v = {w: (1 + math.log(c)) * math.log((self.n + 1) / (self.df.get(w, 0) + 1)) for w, c in tf.items()}
        nrm = math.sqrt(sum(x * x for x in v.values())) or 1
        return {w: x / nrm for w, x in v.items()}
    @staticmethod
    def cos(a, b):
        if len(a) > len(b):
            a, b = b, a
        return sum(x * b.get(w, 0) for w, x in a.items())

def archive_text(r):
    parts = [r.get("title", ""), r.get("summary", ""), r.get("notes", "") or ""]
    for k in ("topics", "methods", "tasks", "realms", "taxa"):
        parts.append(" ".join(r.get(k) or []) * 2)
    return " ".join(parts)

# ---------------- scoring ----------------
def compile_cfg(cfg):
    for g in cfg["groups"]:
        g["_kw"] = [re.compile(k, re.I) for k in g.get("keywords", [])]
        g["_also"] = re.compile(g["also_requires_re"], re.I) if g.get("also_requires_re") else None
    for k, v in cfg.get("keyword_negations", {}).items():
        if not k.startswith("_"):
            NEG[k] = re.compile(v, re.I)
    mb = cfg["data_modality_bonus"]
    for k in ("video", "acoustic", "multimodal", "other"):
        cfg["_" + k] = re.compile(mb[k + "_re"], re.I)
    _sc = cfg.get("scoring", {})
    cfg["_hardx"] = re.compile(_sc["hard_exclude_re"], re.I) if _sc.get("hard_exclude_re") else None
    cfg["_hardx_ok"] = re.compile(_sc["hard_exclude_ok_re"], re.I) if _sc.get("hard_exclude_ok_re") else None
    cfg["_hardx_all"] = re.compile(_sc["hard_exclude_always_re"], re.I) if _sc.get("hard_exclude_always_re") else None
    cfg["_special"] = {"@" + k: re.compile(v, re.I) for k, v in cfg.get("special_res", {}).items()}
    sc = cfg["scoring"]
    cfg["_offdom"] = re.compile(sc["off_domain_re"], re.I) if sc.get("off_domain_re") else None
    cfg["_offdom_ok"] = re.compile(sc["off_domain_exempt_re"], re.I) if sc.get("off_domain_exempt_re") else None
    v = cfg["venues"]
    cfg["_t1"], cfg["_t2"] = {x.lower() for x in v["tier1"]}, {x.lower() for x in v["tier2"]}

NEG = {}
def _hit(k, s, full):
    m = k.search(s)
    if not m:
        return False
    neg = NEG.get(k.pattern)
    return not (neg and neg.search(full))
def kw_hit(g, title, abst):
    full = title + " " + abst
    t = any(_hit(k, title, full) for k in g["_kw"])
    a = t or any(_hit(k, abst, full) for k in g["_kw"])
    return 1.0 if t else (0.6 if a else 0.0)

def special_hit(cfg, req, title, abst):
    rx = cfg["_special"].get(req)
    if rx is None:
        return 0.0
    return 1.0 if rx.search(title) else (0.6 if rx.search(abst) else 0.0)

def group_scores(cfg, rec):
    title, abst = rec["title"] or "", rec.get("abstract") or ""
    text = title + " " + abst
    byname = {g["name"]: g for g in cfg["groups"]}
    raw = {g["name"]: kw_hit(g, title, abst) for g in cfg["groups"]}
    out = {}
    for g in cfg["groups"]:
        if g.get("reviews_only"):
            continue
        n = g["name"]
        s = raw[n]
        if g.get("all_of"):
            parts = []
            for req in g["all_of"]:
                if req in cfg["_special"]:
                    parts.append(special_hit(cfg, req, title, abst))
                elif req == "@self":
                    parts.append(raw[n])
                else:
                    parts.append(raw.get(req, 0.0))
            s = min(parts) if parts else 0.0
        if n in rec["groups"] and not abst and g.get("all_of") and not s:
            s = 0.4   # returned by this group's API query but no abstract to re-check
        if s and g["_also"] is not None and not g["_also"].search(text):
            s = 0.0
        if n in rec["groups"] and not g.get("keywords") and not g.get("all_of"):
            s = max(s, 1.0)   # affiliation / journal groups: the API match is the signal
        elif n in rec["groups"] and not abst and rec.get("source") == "pubmed":
            s = max(s, 0.4)   # PubMed matched title/MeSH but we have no abstract to re-check
        if s:
            out[n] = round(g["weight"] * s, 2)
    return out

def modality(cfg, title, text):
    """Data-modality bonus (Amy: video/imagery > acoustics > other eco sensors; both = multimodal)."""
    mb, f = cfg["data_modality_bonus"], cfg["scoring"].get("modality_abstract_factor", 0.6)
    def lvl(key):
        rx = cfg["_" + key]
        return 1.0 if rx.search(title) else (f if len(rx.findall(text)) >= 2 else 0.0)   # abstract-only needs >= 2 mentions
    v, a = lvl("video"), lvl("acoustic")
    mm = lvl("multimodal")
    if v and a:
        return "Multimodal", round(mb["multimodal"] * min(v, a), 2)
    if mm and (v or a):
        return "Multimodal", round(mb["multimodal"] * min(mm, max(v, a)), 2)
    if v:
        return "Video / imagery", round(mb["video"] * v, 2)
    if a:
        return "Acoustics", round(mb["acoustic"] * a, 2)
    o = lvl("other")
    if o:
        return "Other sensors", round(mb["other"] * o, 2)
    return "", 0.0

def named_hits(cfg, authors):
    hits = []
    for p in cfg.get("named_researchers", {}).get("people", []):
        sns = [p["surname"]] + p.get("alt_surnames", [])
        for a in authors:
            a0 = strip_accents(a).lower()
            for sn in sns:
                sn0 = strip_accents(sn).lower()
                if re.search(r"(^|\s)" + re.escape(sn0) + r"$", a0):
                    given = a0[: -len(sn0)].strip()
                    f0 = strip_accents(p["first"]).lower()
                    ok = given.startswith(f0) if p.get("strict") else given[:1] == f0[:1]
                    if ok:
                        hits.append(p["name"])
    return sorted(set(hits))

def venue_bonus(cfg, venue):
    v = (venue or "").lower().strip()
    v = re.sub(r"\s*\(.*\)$", "", v)
    if v in cfg["_t1"]:
        return cfg["venues"]["tier1_bonus"]
    if v in cfg["_t2"]:
        return cfg["venues"]["tier2_bonus"]
    return 0.0

def is_review(rec):
    pts = set(rec.get("pubtypes") or [])
    if pts & REVIEW_PT:
        return True
    if REVIEW_TITLE_RE.search(rec["title"] or ""):
        return True
    return bool(REVIEW_ABS_RE.search((rec.get("abstract") or "")[:600]))

# ---------------- merge ----------------
SOURCE_PREF = {"pubmed": 0, "europepmc": 1, "crossref": 1, "openalex": 2, "biorxiv": 3, "medrxiv": 3, "ecoevorxiv": 3, "europepmc-preprint": 4, "arxiv": 3}
def merge(all_recs):
    by_doi, by_title, merged = {}, {}, []
    for r in all_recs:
        d, t = r.get("doi") or "", norm_title(r.get("title"))
        if not t:
            continue
        hit = by_doi.get(d) if d else None
        if hit is None and len(t) > 25:
            hit = by_title.get(t)
        if hit is None:
            r["sources"] = [r["source"]]; r["groups"] = set(r["groups"])
            merged.append(r)
            if d: by_doi[d] = r
            by_title[t] = r
            continue
        hit["sources"] = sorted(set(hit["sources"]) | {r["source"]})
        hit["groups"] |= set(r["groups"])
        hit["pubtypes"] = sorted(set(hit.get("pubtypes") or []) | set(r.get("pubtypes") or []))
        if len(r.get("abstract") or "") > len(hit.get("abstract") or ""):
            hit["abstract"] = r["abstract"]
        if SOURCE_PREF.get(r["source"], 9) < SOURCE_PREF.get(hit["source"], 9):
            for k in ("title", "authors", "venue", "date", "url", "source"):
                if r.get(k):
                    hit[k] = r[k]
        if d and not hit.get("doi"):
            hit["doi"] = d
        if d:
            by_doi[d] = hit
        if not hit.get("affiliations") and r.get("affiliations"):
            hit["affiliations"] = r["affiliations"]
    return merged

# ---------------- main ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True); ap.add_argument("--end", required=True)
    ap.add_argument("--sources", default=",".join(ALL_SOURCES))
    ap.add_argument("--top", type=int); ap.add_argument("--out")
    ap.add_argument("--queries", default=os.path.join(HERE, "queries.json"))
    a = ap.parse_args()
    start, end = dt.date.fromisoformat(a.start), dt.date.fromisoformat(a.end)
    cfg = json.load(open(a.queries, encoding="utf-8")); compile_cfg(cfg)
    top_n = a.top or cfg["scoring"]["top_n"]
    want = [s.strip() for s in a.sources.split(",") if s.strip()]
    outdir = a.out or os.path.join(HERE, "out", str(end)); os.makedirs(outdir, exist_ok=True)
    t0 = time.time()
    stats = {"window": [str(start), str(end)], "generated": dt.datetime.now().isoformat(timespec="seconds"), "sources": {}, "failures": {}}
    bulk = cfg["bulk_sources"]
    jobs = {
        "pubmed": lambda: sources.pubmed(cfg, start, end, log),
        "europepmc": lambda: sources.europepmc(cfg, start, end, log),
        "openalex": lambda: sources.openalex(cfg, start, end, log),
        "biorxiv": lambda: sources.rxiv("biorxiv", bulk["biorxiv_categories"], start, end, log),
        "medrxiv": lambda: sources.rxiv("medrxiv", bulk["medrxiv_categories"], start, end, log),
        "arxiv": lambda: sources.arxiv(bulk["arxiv_categories"], start, end, log),
        "ecoevorxiv": lambda: sources.ecoevorxiv(cfg, start, end, log),
        "crossref_journals": lambda: sources.crossref_journals(cfg, start, end, log),
        "zenodo": lambda: sources.zenodo(cfg, start, end, log),
    }
    def run(name):
        ts = time.time()
        try:
            res = jobs[name]()
            return name, res, None, round(time.time() - ts, 1)
        except Exception as e:
            return name, None, f"{type(e).__name__}: {e}", round(time.time() - ts, 1)
    results, timings = {}, {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for name, res, err, secs in ex.map(run, [s for s in want if s in jobs]):
            log(f"{name}: {'FAILED ' + err if err else 'ok'} ({secs}s)")
            if err:
                stats["failures"][name] = err; stats["sources"][name] = {"hits": 0, "seconds": secs, "error": err}
            else:
                results[name] = res; timings[name] = secs
    all_recs, datasets = [], []
    for name, res in results.items():
        if name == "zenodo":
            datasets, info = res
            stats["sources"][name] = {"hits": len(datasets), **{k: v for k, v in info.items() if k != "records"}}
        else:
            recs, info = res
            info = {k: v for k, v in info.items() if k != "records"}
            stats["sources"][name] = {"hits": len(recs), **info}
            all_recs += recs
    for n, secs in timings.items():
        stats["sources"].setdefault(n, {})["seconds"] = secs
    stats["raw_hits_total"] = len(all_recs)

    # merge + filters
    merged = merge(all_recs)
    stats["after_merge_dedupe"] = len(merged)
    ex_dois, ex_titles = exclusions()
    kept, dropped = [], Counter()
    droplog = open(os.path.join(outdir, "dropped.tsv"), "w", encoding="utf-8")
    for r in merged:
        if (r.get("doi") and r["doi"] in ex_dois) or norm_title(r["title"]) in ex_titles:
            dropped["already_in_archive_shortlist_or_sent"] += 1; droplog.write(f"already_in_archive_shortlist_or_sent\t{r.get('doi')}\t{r['title']}\n"); continue
        if DROP_RE.search(r["title"] or "") or (set(r.get("pubtypes") or []) & DROP_PT):
            dropped["errata_retractions_notices"] += 1; droplog.write(f"errata_retractions_notices\t{r.get('doi')}\t{r['title']}\n"); continue
        if r["source"] in ("biorxiv", "medrxiv", "arxiv", "ecoevorxiv") and not daterange_ok(r.get("date", ""), start, end):
            dropped["outside_window"] += 1; droplog.write(f"outside_window\t{r.get('doi')}\t{r['title']}\n"); continue
        kept.append(r)
    stats["dropped"] = dict(dropped)

    # TF-IDF vs archive + preferences
    arch = load_jsonl(os.path.join(NEWS, "archive/items.jsonl")) + load_jsonl(os.path.join(NEWS, "archive/shortlist.jsonl"))
    arch = [x for x in arch if not str(x.get("issue", "")).startswith("TEST")]
    liked, disliked = preferences()
    cand_text = [(r["title"] or "") + " " + (r.get("abstract") or "")[:1500] for r in kept]
    tf = Tfidf([archive_text(x) for x in arch] + cand_text)
    arch_v = [tf.vec(archive_text(x)) for x in arch]
    liked_v = [(tf.vec(t), w) for t, w in liked]
    dis_v = [tf.vec(t) for t in disliked]
    sc = cfg["scoring"]

    scored = []
    for r, text in zip(kept, cand_text):
        gs = group_scores(cfg, r)
        mod, mbonus = modality(cfg, r["title"] or "", text)
        decay = sc.get("group_decay", [1.0])
        kw = sum(v * (decay[i] if i < len(decay) else decay[-1]) for i, v in enumerate(sorted(gs.values(), reverse=True)))
        if r["source"] in BULK and not set(r["sources"]) & {"pubmed", "europepmc", "openalex", "europepmc-preprint"}:
            if kw + mbonus < bulk["min_keyword_score"] or not gs:
                dropped["bulk_below_keyword_threshold"] += 1; droplog.write(f"bulk_below_keyword_threshold\t{r.get('doi')}\t{r['title']}\n"); continue
        named = named_hits(cfg, r.get("authors") or [])
        v = tf.vec(text)
        sim = max((Tfidf.cos(v, av) for av in arch_v), default=0.0)
        lik = max((Tfidf.cos(v, lv) * w for lv, w in liked_v), default=0.0)
        dis = max((Tfidf.cos(v, dv) for dv in dis_v), default=0.0)
        vb = venue_bonus(cfg, r.get("venue"))
        cac = cfg.get("core_priorities", {})
        ca_hits = [gs[g] / next(x["weight"] for x in cfg["groups"] if x["name"] == g) for g in cac.get("groups", []) if gs.get(g)]
        ca = round(cac.get("bonus", 0) * max(ca_hits), 2) if ca_hits else 0.0
        parts = {"keywords": round(kw, 2), "modality": mbonus, "named": cfg["named_researchers"]["weight"] if named else 0.0,
                 "top_venue_bonus": vb, "core_priority": ca, "archive_sim": round(sc["tfidf_archive_weight"] * sim, 2),
                 "liked": round(sc["liked_weight"] * lik, 2), "disliked": round(sc["disliked_weight"] * dis, 2),
                 "no_abstract": sc["no_abstract_penalty"] if len(r.get("abstract") or "") < 100 else 0.0,
                 "low_type": -2.0 if set(r.get("pubtypes") or []) & LOW_PT else 0.0}
        if cfg["_offdom"] is not None and cfg["_offdom"].search(text) and not (cfg["_offdom_ok"] and cfg["_offdom_ok"].search(text)):
            parts["off_domain"] = sc["off_domain_penalty"]   # ML aimed at medical / driving / faces with no ecological target
        ven = (r.get("venue") or "").lower()
        if (cfg["_hardx"] is not None and cfg["_hardx"].search(text) and not (cfg["_hardx_ok"] and cfg["_hardx_ok"].search(text))) \
                or (cfg["_hardx_all"] is not None and cfg["_hardx_all"].search(text)):
            parts["neuro_excluded"] = sc.get("hard_exclude_penalty", -25.0)   # brief: no neuroscience / psychedelic content
        if not cfg["_special"]["@eco"].search(text) and "transferable_cv_ml" not in gs:
            parts["no_eco_context"] = sc.get("no_eco_context_penalty", -5.0)
        if any(x in ven for x in sc.get("repository_venues", [])) or set(r.get("pubtypes") or []) & set(sc.get("repository_types", [])):
            parts["repository"] = sc["repository_penalty"]   # Zenodo/OSF etc: no moderation, often single-author self-deposits
        try:
            if (start - dt.date.fromisoformat((r.get("date") or "")[:10])).days > sc.get("stale_pubdate_days", 60):
                parts["stale_pubdate"] = sc["stale_penalty"]   # newly indexed but published long ago
        except ValueError:
            pass
        if not gs and not named:
            parts["off_topic"] = -3.0   # matched nothing in the brief (e.g. only via generic venue query)
        score = round(sum(parts.values()), 2)
        rev = is_review(r)
        scored.append({"title": r["title"], "authors": r.get("authors") or [], "venue": r.get("venue"), "date": r.get("date"),
                       "doi": r.get("doi"), "url": r.get("url"), "abstract": r.get("abstract") or "", "source": r["source"],
                       "sources": r["sources"], "pubtypes": r.get("pubtypes") or [], "is_review": rev,
                       "is_preprint": r["source"] in ("biorxiv", "medrxiv", "arxiv", "ecoevorxiv", "europepmc-preprint") or "preprint" in (r.get("pubtypes") or []) or "posted-content" in (r.get("pubtypes") or []),
                       "score": score, "score_parts": parts, "matched_queries": sorted(gs, key=lambda k: -gs[k]),
                       "api_queries": sorted(r["groups"]), "modality": mod, "named_researchers": named,
                       "lab_corner_candidate": bool(set(named) & set(cfg["named_researchers"].get("lab_corner_names", []))),
                       "archive_similarity": round(sim, 3)})
    stats["dropped"] = dict(dropped); droplog.close()
    scored.sort(key=lambda x: -x["score"])
    primary = [x for x in scored if not x["is_review"]]
    reviews = [x for x in scored if x["is_review"]]
    cands, revs = primary[:top_n], reviews[:sc["reviews_top_n"]]
    stats["scored_pool"] = len(scored); stats["primary_pool"] = len(primary); stats["review_pool"] = len(reviews)
    stats["candidates_out"] = len(cands); stats["reviews_out"] = len(revs); stats["datasets_out"] = len(datasets)
    stats["runtime_seconds"] = round(time.time() - t0, 1)
    stats["archive_items_used_for_similarity"] = len(arch); stats["preference_signals"] = {"liked": len(liked), "disliked": len(disliked)}

    # Zenodo datasets/software: light ranking by brief keyword groups (feeds "Datasets, tools and code"; verify before use)
    for d in datasets:
        gs = group_scores(cfg, {"title": d["title"], "abstract": d.get("description") + " " + " ".join(d.get("keywords") or []), "groups": set(), "source": "zenodo"})
        d["brief_keyword_score"] = round(sum(gs.values()), 1); d["matched"] = sorted(gs, key=lambda k: -gs[k])
    datasets = sorted([d for d in datasets if d["brief_keyword_score"] > 0], key=lambda d: -d["brief_keyword_score"])[:25]
    stats["datasets_out"] = len(datasets)

    json.dump({"window": [str(start), str(end)], "generated": stats["generated"], "candidates": cands, "reviews": revs,
               "datasets": datasets}, open(os.path.join(outdir, "candidates.json"), "w"), indent=1, ensure_ascii=False)
    json.dump({"window": [str(start), str(end)], "reviews": revs}, open(os.path.join(outdir, "reviews.json"), "w"), indent=1, ensure_ascii=False)
    with open(os.path.join(outdir, "pool.jsonl"), "w", encoding="utf-8") as f:   # every scored item, for auditing/A-B comparison
        for x in scored:
            f.write(json.dumps({k: x[k] for k in ("score", "title", "doi", "url", "venue", "date", "is_review", "matched_queries", "score_parts", "sources", "modality", "named_researchers")}, ensure_ascii=False) + "\n")
    json.dump(stats, open(os.path.join(outdir, "stats.json"), "w"), indent=1, ensure_ascii=False)
    write_md(os.path.join(outdir, "candidates.md"), start, end, cands, revs, datasets, stats)
    log(f"done in {stats['runtime_seconds']}s: {len(cands)} candidates, {len(revs)} reviews, {len(datasets)} datasets -> {outdir}")

def snippet(s, n=260):
    s = re.sub(r"^(abstract|background|introduction)[:.\s]+", "", s or "", flags=re.I)
    return (s[:n].rsplit(" ", 1)[0] + "…") if len(s) > n else s

def auth(a):
    return "" if not a else (a[0] if len(a) == 1 else f"{a[0]} … {a[-1]}" + (f" (+{len(a) - 2})" if len(a) > 2 else ""))

def write_md(path, start, end, cands, revs, datasets, stats):
    L = [f"# Version B candidates (Literature Deep Dive): {start} to {end}", "",
         f"Generated {stats['generated']} · raw hits {stats['raw_hits_total']} → {stats['after_merge_dedupe']} after merge → pool {stats['scored_pool']} "
         f"(primary {stats['primary_pool']}, reviews {stats['review_pool']}) · failures: {', '.join(stats['failures']) or 'none'}",
         "Score = brief keyword groups (interactions x CV/ML first) + data modality (video>acoustic>other; both = multimodal) + core-priority boost + "
         "lab-corner researcher + venue + archive/preference similarity − penalties. Every item still needs verification against its source before use.", "",
         f"## Primary research (top {len(cands)})", ""]
    for i, c in enumerate(cands, 1):
        tags = " ".join(filter(None, ["PREPRINT" if c["is_preprint"] else "", c["modality"],
                                      ("★ LAB " if c.get("lab_corner_candidate") else "★ ") + ", ".join(c["named_researchers"]) if c["named_researchers"] else ""]))
        L += [f"{i}. **{c['title']}** [{c['score']}] {tags}",
              f"   {auth(c['authors'])} · {c['venue']} · {c['date']} · {c['url']} · q: {', '.join(c['matched_queries'][:4])}",
              f"   {snippet(c['abstract'])}", ""]
    L += [f"## Reviews, perspectives, meta-analyses (top {len(revs)}) → explainer / critiques candidates", ""]
    for i, c in enumerate(revs, 1):
        pt = ", ".join(p for p in c["pubtypes"] if p and p != "Journal Article")[:60]
        L += [f"{i}. **{c['title']}** [{c['score']}] {pt}",
              f"   {auth(c['authors'])} · {c['venue']} · {c['date']} · {c['url']} · q: {', '.join(c['matched_queries'][:4])}",
              f"   {snippet(c['abstract'], 200)}", ""]
    L += [f"## New datasets / software on Zenodo ({len(datasets)}) → 'Datasets, tools and code' candidates", ""]
    for d in datasets:
        L.append(f"- [{d['brief_keyword_score']}] {d['type']} · {d['title']} · {', '.join(d['creators'][:3])} · {d['date']} · {d['url']} · q: {', '.join(d['matched'][:3])}")
    if "zenodo" in stats["failures"]:
        L.append(f"- Zenodo FAILED: {stats['failures']['zenodo']}")
    L.append("")
    open(path, "w", encoding="utf-8").write("\n".join(L))

if __name__ == "__main__":
    main()
