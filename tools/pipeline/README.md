# Literature Deep Dive pipeline (method B: database sweep)

This is a cheap, broad, LLM-free sweep of free scholarly APIs for Amy's interests. It was ported on 4 Nov 2026 from the Neurodynamics Digest pipeline and retuned; see `../docs/PROCESS.md` §4 for the full scoring description.

```bash
cd /workspace/amy-digest/pipeline
python3 fetch_candidates.py --start 2026-11-02 --end 2026-11-08      # ~45-60 s -> out/2026-11-08/
python3 chatter.py --date 2026-11-08 --top 30 [--discover]           # Bluesky + Hacker News buzz
```

- `--sources pubmed,europepmc,openalex,biorxiv,arxiv,ecoevorxiv,crossref_journals,zenodo` picks a subset; `--top N` sets the size of the primary list; `--queries` points to another config.
- **Config:** `queries.json` holds the query groups (weights, PubMed/EPMC/OpenAlex queries, keyword regexes, `also_requires_re`), the data-modality bonus, core priorities, named researchers, venues, bulk-source categories, Zenodo queries, keyword negations and scoring/penalties (off-domain, no-ecology-context, neuro/psychedelic hard exclude, repository types).
- **Inputs read:** `../archive/items.jsonl`, `../archive/shortlist.jsonl`, `../sent-log.md` (dedupe) and `../preferences.md` (liked/disliked similarity).
- **Outputs:** `out/<end>/candidates.json|md`, `reviews.json`, `pool.jsonl`, `dropped.tsv`, `stats.json`; chatter writes `chatter.json|md`.
- **Environment (all optional):** `LDD_MAILTO` (polite-pool contact; defaults to the +deepdive address, never the unsuffixed one), `NCBI_API_KEY`, `OPENALEX_API_KEY`.
- **Not used:** Altmetric (needs a key), Crossref Event Data (sunset), Reddit (OAuth), biorxiv-top (neuroscience only), ClinicalTrials.gov (not relevant).
- The output is a candidate list, not truth: verify every item against its source before it goes in an issue.
