"""One function per scholarly source. Each returns (records, info) and raises on total failure.
A record: dict(title, authors[list of 'Given Surname'], venue, date, doi, url, abstract, source, pubtypes[list], groups[set])."""
import os, re, time, datetime as dt, xml.etree.ElementTree as ET
from common import get, post, clean, norm_doi, MAILTO, FetchError

def _fill(q, cfg):
    # any top-level "*_terms" string in queries.json can be used as {name} inside a query
    for k, v in cfg.items():
        if k.endswith("_terms") and isinstance(v, str):
            q = q.replace("{" + k + "}", v)
    return q

def group_query(g, cfg, source):
    if isinstance(g.get(source), str):
        return _fill(g[source], cfg)
    if source == "openalex" and "openalex_query" in g:
        return _fill(g["openalex_query"], cfg)
    if "query" in g:
        return _fill(g["query"], cfg)
    return None

# ---------------- PubMed ----------------
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
def _ncbi_params(extra):
    p = {"tool": "ldd-pipeline", "email": MAILTO, **extra}
    if os.environ.get("NCBI_API_KEY"):
        p["api_key"] = os.environ["NCBI_API_KEY"]
    return p

def pubmed(cfg, start, end, log):
    info = {"queries": 0, "query_errors": []}
    pmid_groups = {}
    queries = []
    for g in cfg["groups"]:
        q = group_query(g, cfg, "pubmed")
        if q:
            queries.append((g["name"], q))
    people = cfg.get("named_researchers", {}).get("people", [])
    if people:
        q = " OR ".join(f'"{p["surname"]} {p["first"]}"[fau]' for p in people if not p.get("no_query"))
        queries.append(("named_researchers", q))
    for name, q in queries:
        try:
            r = get(EUTILS + "esearch.fcgi", params=_ncbi_params({"db": "pubmed", "term": q, "datetype": "edat",
                    "mindate": start.strftime("%Y/%m/%d"), "maxdate": end.strftime("%Y/%m/%d"), "retmode": "json", "retmax": 400}))
            ids = r["esearchresult"].get("idlist", [])
            info["queries"] += 1
            info.setdefault("per_group", {})[name] = int(r["esearchresult"].get("count", 0))
            for i in ids:
                pmid_groups.setdefault(i, set()).add(name)
        except Exception as e:
            info["query_errors"].append(f"{name}: {e}")
        time.sleep(0.35)
    if not pmid_groups and info["query_errors"]:
        raise FetchError("; ".join(info["query_errors"][:3]))
    recs = []
    ids = list(pmid_groups)
    for k in range(0, len(ids), 200):
        batch = ids[k:k + 200]
        try:
            xml = post(EUTILS + "efetch.fcgi", data=_ncbi_params({"db": "pubmed", "id": ",".join(batch), "retmode": "xml"}), expect="text", timeout=60)
        except Exception as e:
            info["query_errors"].append(f"efetch: {e}"); continue
        root = ET.fromstring(xml)
        for art in root.findall(".//PubmedArticle"):
            pmid = art.findtext(".//MedlineCitation/PMID")
            a = art.find(".//Article")
            if a is None:
                continue
            title = clean("".join(a.find("ArticleTitle").itertext()) if a.find("ArticleTitle") is not None else "")
            abst = " ".join(clean("".join(x.itertext())) for x in a.findall(".//Abstract/AbstractText"))
            authors = []
            for au in a.findall(".//AuthorList/Author"):
                ln, fn = au.findtext("LastName"), au.findtext("ForeName") or au.findtext("Initials") or ""
                if ln:
                    authors.append(f"{fn} {ln}".strip())
                elif au.findtext("CollectiveName"):
                    authors.append(au.findtext("CollectiveName"))
            venue = a.findtext(".//Journal/Title") or ""
            doi = ""
            for aid in art.findall(".//PubmedData/ArticleIdList/ArticleId"):
                if aid.get("IdType") == "doi":
                    doi = aid.text or ""
            if not doi:
                for el in a.findall("ELocationID"):
                    if el.get("EIdType") == "doi":
                        doi = el.text or ""
            ad = a.find("ArticleDate")
            if ad is not None:
                date = f'{ad.findtext("Year")}-{int(ad.findtext("Month") or 1):02d}-{int(ad.findtext("Day") or 1):02d}'
            else:
                pd = a.find(".//Journal/JournalIssue/PubDate")
                y = pd.findtext("Year") if pd is not None else None
                date = y or ""
            pts = [p.text for p in a.findall(".//PublicationTypeList/PublicationType") if p.text]
            affs = " | ".join(clean(x.text) for x in a.findall(".//AffiliationInfo/Affiliation") if x.text)[:600]
            recs.append({"title": title, "authors": authors, "venue": venue, "date": date, "doi": norm_doi(doi),
                         "url": f"https://doi.org/{norm_doi(doi)}" if doi else f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                         "abstract": abst, "source": "pubmed", "pmid": pmid, "pubtypes": pts, "affiliations": affs,
                         "groups": set(pmid_groups.get(pmid, set()))})
        time.sleep(0.35)
    info["records"] = len(recs)
    return recs, info

# ---------------- Europe PMC ----------------
EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
def europepmc(cfg, start, end, log):
    info = {"queries": 0, "query_errors": [], "per_group": {}}
    out = {}
    queries = []
    for g in cfg["groups"]:
        if "pubmed" in g and "europepmc" not in g and "query" not in g:
            continue
        q = group_query(g, cfg, "europepmc")
        if q:
            queries.append((g["name"], q))
    people = [p for p in cfg.get("named_researchers", {}).get("people", []) if not p.get("strict") and not p.get("no_query")]
    if people:
        queries.append(("named_researchers", " OR ".join(f'AUTH:"{p["surname"]} {p["first"][0]}"' for p in people)))
    for name, q in queries:
        full = f"({q}) AND (FIRST_PDATE:[{start} TO {end}])"
        cursor, pages = "*", 0
        try:
            while pages < 3:
                r = get(EPMC, params={"query": full, "format": "json", "resultType": "core", "pageSize": 200, "cursorMark": cursor}, timeout=45)
                info["queries"] += 1; pages += 1
                if pages == 1:
                    info["per_group"][name] = r.get("hitCount", 0)
                for x in r.get("resultList", {}).get("result", []):
                    key = x.get("id")
                    if key in out:
                        out[key]["groups"].add(name); continue
                    pts = (x.get("pubTypeList") or {}).get("pubType", [])
                    venue = ((x.get("journalInfo") or {}).get("journal") or {}).get("title") or (x.get("bookOrReportDetails") or {}).get("publisher") or ""
                    if x.get("source") == "PPR" and not venue:
                        venue = "Preprint"
                    authors = [clean(f'{a.get("firstName","")} {a.get("lastName","")}') if a.get("lastName") else a.get("fullName", "")
                               for a in (x.get("authorList") or {}).get("author", [])]
                    doi = norm_doi(x.get("doi"))
                    affs = " | ".join(a.get("affiliation", "") for a in (x.get("authorList") or {}).get("author", []) if a.get("affiliation"))[:600]
                    out[key] = {"title": clean(x.get("title")), "authors": authors, "venue": venue,
                                "date": x.get("firstPublicationDate", ""), "doi": doi,
                                "url": f"https://doi.org/{doi}" if doi else f'https://europepmc.org/article/{x.get("source")}/{x.get("id")}',
                                "abstract": clean(x.get("abstractText")), "source": "europepmc" + ("-preprint" if x.get("source") == "PPR" else ""),
                                "pmid": x.get("pmid"), "pubtypes": pts, "affiliations": affs, "groups": {name}}
                nxt = r.get("nextCursorMark")
                if not nxt or nxt == cursor or len(r.get("resultList", {}).get("result", [])) < 200:
                    break
                cursor = nxt
        except Exception as e:
            info["query_errors"].append(f"{name}: {e}")
    if not out and info["query_errors"]:
        raise FetchError("; ".join(info["query_errors"][:3]))
    info["records"] = len(out)
    return list(out.values()), info

# ---------------- OpenAlex ----------------
OA = "https://api.openalex.org/works"
def _inv(ii):
    if not ii:
        return ""
    pos = {}
    for w, ps in ii.items():
        for p in ps:
            pos[p] = w
    return " ".join(pos[i] for i in sorted(pos))

def openalex(cfg, start, end, log):
    """Only groups flagged openalex=true (shared free budget ~$0.10/day per IP without a key, ~$0.001 per call)."""
    info = {"queries": 0, "query_errors": [], "per_group": {}, "cost_usd": 0.0}
    out = {}
    for g in cfg["groups"]:
        if not g.get("openalex"):
            continue
        q = group_query(g, cfg, "openalex")
        q = q.replace("*", "")
        params = {"filter": f"title_and_abstract.search:{q},from_publication_date:{start},to_publication_date:{end}",
                  "per-page": 100, "mailto": MAILTO,
                  "select": "id,doi,display_name,publication_date,type,primary_location,authorships,abstract_inverted_index"}
        if os.environ.get("OPENALEX_API_KEY"):
            params["api_key"] = os.environ["OPENALEX_API_KEY"]
        try:
            r = get(OA, params=params, timeout=45)
            info["queries"] += 1
            info["per_group"][g["name"]] = r.get("meta", {}).get("count", 0)
            info["cost_usd"] += float(r.get("meta", {}).get("cost_usd") or 0)
            for w in r.get("results", []):
                key = w["id"]
                if key in out:
                    out[key]["groups"].add(g["name"]); continue
                loc = w.get("primary_location") or {}
                src = (loc.get("source") or {})
                doi = norm_doi(w.get("doi"))
                out[key] = {"title": clean(w.get("display_name")), "authors": [a["author"]["display_name"] for a in w.get("authorships", [])],
                            "venue": src.get("display_name") or "", "date": w.get("publication_date", ""), "doi": doi,
                            "url": f"https://doi.org/{doi}" if doi else (loc.get("landing_page_url") or key),
                            "abstract": _inv(w.get("abstract_inverted_index")), "source": "openalex",
                            "pubtypes": [w.get("type") or ""], "groups": {g["name"]}}
        except Exception as e:
            info["query_errors"].append(f'{g["name"]}: {e}')
        time.sleep(0.2)
    if not out and info["query_errors"]:
        raise FetchError("; ".join(info["query_errors"][:3]))
    info["records"] = len(out)
    return list(out.values()), info

# ---------------- bioRxiv / medRxiv ----------------
def rxiv(server, cats, start, end, log):
    info = {"per_category": {}, "versions_skipped": 0, "query_errors": []}
    recs = []
    for cat in cats:
        cursor, total, n = 0, None, 0
        try:
            while total is None or cursor < total:
                r = get(f"https://api.biorxiv.org/details/{server}/{start}/{end}/{cursor}", params={"category": cat}, timeout=45)
                m = (r.get("messages") or [{}])[0]
                total = int(m.get("total", 0) or 0)
                col = r.get("collection", []) or []
                if not col:
                    break
                for x in col:
                    if str(x.get("version")) != "1":
                        info["versions_skipped"] += 1; continue
                    authors = []
                    for a in (x.get("authors") or "").split(";"):
                        a = a.strip()
                        if "," in a:
                            ln, fn = a.split(",", 1); authors.append(f"{fn.strip()} {ln.strip()}")
                        elif a:
                            authors.append(a)
                    doi = norm_doi(x.get("doi"))
                    recs.append({"title": clean(x.get("title")), "authors": authors, "venue": f"{server} ({x.get('category')})",
                                 "date": x.get("date", ""), "doi": doi, "url": f"https://www.{server}.org/content/{doi}v1",
                                 "abstract": clean(x.get("abstract")), "source": server, "pubtypes": [x.get("type", "")],
                                 "affiliations": x.get("author_corresponding_institution", ""), "groups": set()})
                    n += 1
                cursor += len(col)
                time.sleep(0.2)
            info["per_category"][cat] = n
        except Exception as e:
            info["query_errors"].append(f"{cat}: {e}")
    if not recs and info["query_errors"]:
        raise FetchError("; ".join(info["query_errors"][:3]))
    info["records"] = len(recs)
    return recs, info

# ---------------- arXiv ----------------
def arxiv(cats, start, end, log):
    ns = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    recs, info = [], {"per_category": {}}
    for cat in cats:
        # "cs.CV" = whole category; "cs.CV|abs:coral OR abs:reef" = category AND a filter (big CS categories)
        cat, _, filt = cat.partition("|")
        cq = "(" + " OR ".join(f"cat:{c}" for c in cat.split("+")) + ")"
        q = f"{cq}{' AND (' + filt + ')' if filt else ''} AND submittedDate:[{start:%Y%m%d}0000 TO {end:%Y%m%d}2359]"
        startn, n = 0, 0
        while True:
            xml = get("https://export.arxiv.org/api/query", params={"search_query": q, "start": startn, "max_results": 200,
                      "sortBy": "submittedDate", "sortOrder": "descending"}, expect="text", timeout=60)
            root = ET.fromstring(xml)
            ents = root.findall("a:entry", ns)
            for e in ents:
                aid = (e.findtext("a:id", "", ns) or "").rsplit("/abs/", 1)[-1]
                base = re.sub(r"v\d+$", "", aid)
                doi = norm_doi(e.findtext("arxiv:doi", "", ns)) or f"10.48550/arxiv.{base}".lower()
                recs.append({"title": clean(e.findtext("a:title", "", ns)), "authors": [clean(a.findtext("a:name", "", ns)) for a in e.findall("a:author", ns)],
                             "venue": f"arXiv ({cat.split('+')[0]})", "date": (e.findtext("a:published", "", ns) or "")[:10], "doi": doi,
                             "url": f"https://arxiv.org/abs/{base}", "abstract": clean(e.findtext("a:summary", "", ns)),
                             "source": "arxiv", "pubtypes": ["preprint"], "groups": set()})
                n += 1
            if len(ents) < 200:
                break
            startn += 200; time.sleep(3)
        info["per_category"][cat + (" (filtered)" if filt else "")] = info["per_category"].get(cat + (" (filtered)" if filt else ""), 0) + n
        time.sleep(3)
    info["records"] = len(recs)
    return recs, info

# ---------------- Crossref: ecology/ML journals (new DOIs registered in the window) ----------------
CR = "https://api.crossref.org"
def _cr_rec(w, source, venue=None):
    doi = norm_doi(w.get("DOI"))
    dp = ((w.get("published") or w.get("posted") or w.get("issued") or {}).get("date-parts") or [[None]])[0]
    date = "-".join(f"{int(x):02d}" if i else str(x) for i, x in enumerate(dp) if x) if dp and dp[0] else ""
    authors = [clean(f"{a.get('given', '')} {a.get('family', '')}") or a.get("name", "") for a in (w.get("author") or [])]
    affs = " | ".join(af.get("name", "") for a in (w.get("author") or []) for af in (a.get("affiliation") or []))[:600]
    return {"title": clean((w.get("title") or [""])[0]), "authors": [a for a in authors if a],
            "venue": venue or (w.get("container-title") or [""])[0],
            "date": date, "created": ((w.get("created") or {}).get("date-time") or "")[:10], "doi": doi, "url": f"https://doi.org/{doi}",
            "abstract": clean(w.get("abstract")), "source": source, "pubtypes": [w.get("type") or ""], "affiliations": affs, "groups": set()}

def _cr_page(path, flt, log, cap=2000):
    out, cursor = [], "*"
    sel = "DOI,title,container-title,published,posted,issued,created,abstract,author,type"
    while len(out) < cap:
        r = get(CR + path, params={"filter": flt, "rows": 500, "cursor": cursor, "select": sel, "mailto": MAILTO}, timeout=60, retries=3)
        m = r.get("message", {})
        items = m.get("items", [])
        out += items
        if len(items) < 500 or not m.get("next-cursor"):
            break
        cursor = m["next-cursor"]
    return out

def crossref_journals(cfg, start, end, log):
    """Every journal-article whose DOI was registered (created) in the window, for each ISSN in bulk_sources.crossref_journals.
    Catches ecology / methods journals that PubMed indexes late or not at all (MEE, Ecol Inform, RSEC, Coral Reefs...). Bulk: keyword threshold applies."""
    info = {"per_journal": {}, "query_errors": []}
    recs = []
    for name, issn in cfg["bulk_sources"].get("crossref_journals", {}).items():
        if name.startswith("_"):
            continue
        try:
            items = _cr_page(f"/journals/{issn}/works", f"from-created-date:{start},until-created-date:{end},type:journal-article", log, cap=1500)
            info["per_journal"][name] = len(items)
            recs += [_cr_rec(w, "crossref") for w in items]
        except Exception as e:
            info["query_errors"].append(f"{name}: {e}")
        time.sleep(0.15)
    if not recs and info["query_errors"]:
        raise FetchError("; ".join(info["query_errors"][:3]))
    info["records"] = len(recs)
    return recs, info

def ecoevorxiv(cfg, start, end, log):
    """EcoEvoRxiv preprints (Crossref prefix 10.32942), posted in the window. Bulk: keyword threshold applies."""
    items = _cr_page("/prefixes/10.32942/works", f"from-posted-date:{start},until-posted-date:{end}", log, cap=1000)
    recs = [_cr_rec(w, "ecoevorxiv", venue="EcoEvoRxiv") for w in items if w.get("type") == "posted-content"]
    for r in recs:
        r["pubtypes"] = ["preprint"]
    return recs, {"records": len(recs)}

# ---------------- Zenodo: new datasets / software (feeds "Datasets, tools and code", kept out of the paper ranking) ----------------
def zenodo(cfg, start, end, log):
    info = {"queries": 0, "query_errors": []}
    out = {}
    for q in cfg.get("zenodo_queries", []):
        try:
            r = get("https://zenodo.org/api/records", params={"q": f"({q}) AND publication_date:[{start} TO {end}]",
                    "size": 25, "sort": "mostrecent"}, timeout=45, retries=2)
            info["queries"] += 1
            for h in (r.get("hits") or {}).get("hits", []):
                md = h.get("metadata", {})
                rt = (md.get("resource_type") or {}).get("type", "")
                if rt not in ("dataset", "software"):
                    continue
                doi = norm_doi(h.get("doi") or md.get("doi"))
                key = (h.get("conceptdoi") or doi or str(h.get("id")))
                if key in out:
                    continue
                out[key] = {"title": clean(md.get("title")), "type": rt, "creators": [c.get("name") for c in md.get("creators", [])][:8],
                            "date": md.get("publication_date"), "doi": doi, "url": (h.get("links") or {}).get("self_html") or f"https://doi.org/{doi}",
                            "description": clean(md.get("description"))[:500], "keywords": md.get("keywords", [])[:10]}
        except Exception as e:
            info["query_errors"].append(f"{q[:40]}: {e}")
        time.sleep(0.5)
    if not out and info["query_errors"] and len(info["query_errors"]) == len(cfg.get("zenodo_queries", [])):
        raise FetchError("; ".join(info["query_errors"][:3]))
    info["records"] = len(out)
    return list(out.values()), info
