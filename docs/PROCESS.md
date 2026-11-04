# Literature Deep Dive: the full process

Amy's (Aimee du Luart's) weekly science newsletter, written by **Nudibranchi**. It arrives on Monday mornings (UK time) and covers the previous Monday–Sunday. The searchable archive lives at https://aimee-duluart.github.io/literature-deep-dive/.

This file was written on 4 Nov 2026. It ports the paper-search upgrade that Mochi built for Patrick's Neurodynamics Digest (his `docs/PROCESS.md`, 1 Nov 2026), retuned for Amy's interests. `brief.md` is still the authority; if it and this file disagree, follow the brief. **Never mix this digest with Patrick's** (data, site, mail, routines).

## Contents
1. Moving parts
2. File layout
3. Interests and ranking (summary of the brief)
4. Discovery: the combined method (B database sweep → A web pass → merge/verify → provenance)
5. Writing and building the issue
6. Publishing and the archive site (graph view, sync)
7. Sending, sent-log and feedback
8. Weekly checklist
9. Not ported from Patrick's process / known gaps
10. Routine prompt (current wording)

## 1. Moving parts
| Part | Where |
|---|---|
| Brief (source of truth) | `/workspace/amy-digest/brief.md` |
| Preferences (likes/dislikes) | `/workspace/amy-digest/preferences.md` |
| Sent-log | `/workspace/amy-digest/sent-log.md` |
| Database pipeline (method B) | `/workspace/amy-digest/pipeline/` (README.md there) |
| Issue build | `/workspace/amy-digest/build/` (render.py, compact.py, section_icons.py, house_style.py, archive_items.py, check_issue.py) |
| Per-issue folders | `/workspace/amy-digest/issue-<nnn>/` (content.py, research/, built HTML + txt) |
| Provenance | `/workspace/amy-digest/ab/<Sunday>/provenance.json` |
| Archive rows | `/workspace/amy-digest/archive/items.jsonl`, `archive/shortlist.jsonl` |
| Site repo (GitHub Pages) | `/workspace/amy-digest/site` → `aimee-duluart/literature-deep-dive` (main) |
| Publish | `AMY_GITHUB_TOKEN=… build/publish.sh "message"` (Amy's token from the env only; never the box gh login) |
| Mail | from `pk-neuro-digest+deepdive@mail.grokbot.com` to `<RECIPIENT_EMAIL>` |

## 2. File layout
```
amy-digest/
  brief.md  preferences.md  sent-log.md  HANDOVER.md  docs/PROCESS.md
  pipeline/  common.py sources.py queries.json fetch_candidates.py chatter.py README.md  out/<Sunday>/
  build/     render.py compact.py section_icons.py house_style.py archive_items.py check_issue.py
             build_archive_site.py tag_map.json config.py favicon.py publish.sh
  archive/   items.jsonl shortlist.jsonl
  ab/<Sunday>/provenance.json
  issue-<nnn>/
  site/      index.html issues/<nnn>.html archive/{index,search,shortlist,graph}.html archive/sync.js archive/vendor/
             archive/items.json shortlist.json item/<id>.html  docs/PROCESS.md  tools/pipeline/ (published copies)
```

## 3. Interests and ranking (from the brief)
Priority order, highest first:
1. CV/ML for species interactions (video/imagery first)
2. Multimodal AI and interaction networks
3. Bioacoustics / passive acoustic monitoring
4. Coral reefs
5. Behaviour classification (lower weight)
6. Transferable CV/ML (methods from outside ecology that she could use)
7. All environments (terrestrial, freshwater and marine)
8. Emerging tools
9. Climate and human impacts, ecosystem services
10. Restoration and nature-based solutions
11. Big papers from the wider field

Regular sections: ML/CV explainer, datasets & tools, critiques & nulls, policy & ocean news, conferences & training, funding. The Lab corner is used only for the QMUL lab (Ian McFadden, Iran Roman) or Amy's own work, and only when the item is key. **No neuroscience or psychedelic content, ever.** Light ocean style, the greeting "Hi Mermaid Queen!", the sign-off "— Nudibranchi" and the occasional touch of sass.

## 4. Discovery: the combined method
Same order as Patrick's: **B first (cheap, broad), then A (targeted web pass for B's gaps), then merge into one issue.** The issue never labels items by method.

### 4.1 Step B: database sweep
```bash
cd /workspace/amy-digest/pipeline
python3 fetch_candidates.py --start <Monday> --end <Sunday>        # ~45–60 s
python3 chatter.py --date <Sunday> --top 30 [--discover]           # ~2–5 min
```
It uses only free scholarly APIs, with no LLM. The sources run in parallel, each in its own try/except, and any failure is logged in `stats.json`.

| Source | Notes |
|---|---|
| PubMed | E-utilities, by query group (optional `NCBI_API_KEY`) |
| Europe PMC | REST search, by query group |
| OpenAlex | groups with `openalex: true` (optional `OPENALEX_API_KEY`) |
| bioRxiv | `api.biorxiv.org/details`, categories: ecology, animal_behavior_and_cognition, zoology, evolutionary_biology, bioinformatics. Bulk: must reach `min_keyword_score` 3.0 |
| arXiv | q-bio.PE, q-bio.QM; cs.CV/LG/AI pre-filtered by ecology abstract terms; eess.AS/cs.SD by bioacoustics terms; cs.CV transferable-method titles (HOI, scene graphs, MOT, video foundation, open-vocabulary…) |
| EcoEvoRxiv | via Crossref (replaces medRxiv, which is irrelevant here) |
| Crossref journals | new DOIs in the window for ~40 ecology/marine/acoustics/methods journals that PubMed indexes late (MEE, Ecol Inform, RSEC, Coral Reefs, JASA, Bioacoustics…) |
| Zenodo | new datasets/models (replaces ClinicalTrials.gov) → "Datasets & tools" candidates |

**Merge and dedupe.** Records merge by DOI, else by normalised title (over 25 characters). Metadata preference: pubmed > europepmc = crossref > openalex > preprints (bioRxiv, EcoEvoRxiv, arXiv).

**Dropped before scoring:**
- anything already in `archive/items.jsonl`, `archive/shortlist.jsonl` or the `sent-log.md` DOIs
- errata, retractions, notices, conference-abstract books and GBIF "Occurrence Download" records
- bulk records outside the window or below the keyword threshold

**Scoring.** All of it is tunable in `pipeline/queries.json`.
- **Query groups** (weight): interaction_cv 10; interaction_video 9, interaction_networks_ml 9, multimodal_eco 9, coral_reef_ml 9; bioacoustics_ml 8.5; interaction_networks 7, bioacoustics_pam 7, coral_reef 7; own_lab 6; behaviour_classification 5.5; eco_tools 5; transferable_cv_ml 4.5; datasets_benchmarks 4, restoration_nbs 4; climate_human_impacts 3.5; critiques_nulls 3, marine_conservation 3; wildcard_top_journals 0 (retrieval only); reviews_core / reviews_top_journals (reviews only). Groups can also require an ecology-context regex (`also_requires_re`).
- **Keyword score:** weight × hit (title 1.0, abstract 0.6), with multiple groups combined using decay [1, .5, .3, .2].
- **Data-modality bonus** (replaces EEG > fMRI): multimodal +4, video/imagery +3.5, acoustics +3, other sensors +1. An abstract-only hit needs ≥2 mentions and is multiplied by 0.6.
- **Core-priority bonus:** +3 × hit for interaction_cv, interaction_video, interaction_networks_ml and multimodal_eco.
- **Named researchers:** +5 (Ian McFadden, Iran Roman, Aimee du Luart; first names required).
- **Venue tiers:** ecology, methods and CV/ML venues give a small tie-break only.
- **Similarity:** TF-IDF similarity to the archive × 8; liked × 10, disliked × −6 (from `preferences.md`).
- **Penalties:**
  - no abstract −1.5
  - stale pubdate (>60 days) −1.5
  - repository deposits / non-article types −8
  - off-domain regex −4 (unless there is clear ecological context)
  - **no ecological context −5** (unless transferable CV/ML)
  - **hard exclude −25** for neuroscience/psychedelic terms; ecological context exempts the general neuro words but never the psychedelic ones
- **Keyword negations:** e.g. Google Coral TPU, "random forest", "bird's-eye view", "ecologically valid", PAM = pulse-amplitude modulation, CorelDraw.

**Outputs** go to `pipeline/out/<Sunday>/`: `candidates.json/.md` (top 60 primary, top 15 reviews, Zenodo datasets), `reviews.json`, `pool.jsonl` (score_parts), `dropped.tsv`, `stats.json`, plus `chatter.json/.md` from chatter.py.

Example run (window 26 Oct–1 Nov 2026, run 4 Nov): 3173 raw hits → 2780 after merge → 2161 scored → 60 candidates + 15 reviews + 7 datasets in 48 s, with zero source failures and zero neuro/psychedelic hits in the candidates.

**Chatter.** chatter.py searches Bluesky (URL variants plus quoted titles, bot accounts excluded) and Hacker News. buzz = 3×(distinct authors) + 2×√(engagement) + HN. The in-window buzz is the weekly signal. `--discover` searches ecology, coral reef, bioacoustics, camera trap, biodiversity and species-interaction posts for papers the sweep missed.

**The pipeline is not automatic truth.** Read `candidates.md`, discard leftover noise (e.g. urban soundscape design, heritage "conservation") and verify every claim against the abstract or full text.

### 4.2 Step A: targeted web pass
Search the same window by browsing, aiming at what B missed:
- high-profile journals that index slowly (Nature, Science, Nat Ecol Evol, Curr Biol, PNAS, MEE)
- CVPR/ICCV/ECCV/NeurIPS CV4Animals-type workshop papers
- named researchers and the QMUL lab
- policy and ocean news (IPBES, UN Ocean, ISA deep-sea mining, 30x30, UK marine policy)
- conferences and training, and funding calls
- notable slightly older **ICYMI** papers

### 4.3 Merge, dedupe, verify
- Take the union of A and B, deduped by DOI, else by title.
- Rank by relevance (the priority order above) and study quality; the venue is only a tie-break.
- **Verify every item against its real source.** Never invent papers, authors, numbers, deadlines or links.

### 4.4 Provenance
Save `/workspace/amy-digest/ab/<Sunday>/provenance.json`:
```json
{"date": "2026-11-08", "window": ["2026-11-02", "2026-11-08"],
 "counts": {"A": 0, "B": 0, "AB": 0, "total": 0},
 "items": [{"section": "Headline", "title": "...", "doi": "10.xxxx/...", "url": "https://doi.org/...", "found_by": "AB"}],
 "notes": "Notable single-method finds: ..."}
```
Write the same `found_by` value to each new archive row.

## 5. Writing and building the issue
- Copy the latest `issue-<nnn>/content.py` as a template and fill it in following the brief's sections and tone.
- Build with `python3 build/render.py --full` to get the full HTML, the compact HTML (<80 KB) and the plain text.
- **Then run the pre-send checks:** `python3 build/check_issue.py issue-<nnn>/issue-<nnn>-compact.html issue-<nnn>/issue-<nnn>.html issue-<nnn>/issue-<nnn>.txt`. These check:
  - compact ≤80 KB and no CJK
  - no neuroscience/psychedelic terms
  - only the +deepdive address (Amy's own address may appear only as text)
  - no Neurodynamics/Patrick/Mochi mix-ups
  - no dark body background and the Nudibranchi sign-off
- Fix anything flagged before you send.

## 6. Publishing and the archive site
- In `site/`, add `issues/<nnn>.html`, update `index.html` (below the `<!-- ISSUES (newest first) -->` marker), append to `archive/items.jsonl`, run `python3 build/build_archive_site.py`, then `AMY_GITHUB_TOKEN=… build/publish.sh "Issue nnn"`.
- Never force-push, and never touch the `user-state` branch.
- **Archive** (`archive/index.html`): section tabs; chips for ecosystem, data modality, task, study type and **publication status (new)**; more filters; star / to-read / read / not interested; More like this; Send my preferences to Nudibranchi. A **publication-status badge** (Peer reviewed / Preprint / Reviewed preprint) appears on cards, also on the shortlist.
- **Graph view (new, `archive/graph.html`):**
  - d3-force graph, vendored locally in `archive/vendor/` (ISC licence)
  - node colour = data modality
  - links by shared ecosystem / modality / task / method family, with optional taxon, topic tags, authors or text similarity
  - tag nodes, filters, the same marks as the archive, a side panel and shortlist/quarantine toggles
  - settings saved in `ldd-graph`
- **Cross-device sync (new, `archive/sync.js`):**
  - Stars, read marks, shortlist marks and "Sent to Nudibranchi" marks (`ldd-archive`, `ldd-shortlist`, `ldd-search-sent`) sync through `user-state.json` on the `user-state` branch of Amy's repo, using the GitHub contents API.
  - Merging is per mark with timestamps and tombstones.
  - It needs a fine-grained PAT that Amy creates herself: owner aimee-duluart, only literature-deep-dive, Contents read+write. She pastes it into the ⇅ dialog on each device, and it is stored only in that browser's localStorage. Without a token the pages work locally exactly as before.
  - The repo is public, so the marked item ids in `user-state.json` are publicly visible; nothing else is stored there. Automation (publish.sh, routines) must never touch the `user-state` branch.
- `site/docs/PROCESS.md` and `site/tools/pipeline/` are published copies (no outputs, no secrets).

## 7. Sending, sent-log and feedback
- Send one email from the +deepdive inbox to <RECIPIENT_EMAIL> (automatic, no draft card, per Amy 3 Nov 2026), with the subject "Literature Deep Dive #<n>: <highlights>".
- Append the items to `sent-log.md` (`## Issue nnn · date · STATUS` header, then `- [nnn] Title — URL — date`). The pipeline drops DOIs listed there.
- The email-requests routine handles the archive/shortlist/preferences mailto subjects, always to the +deepdive address.

## 8. Weekly checklist
- [ ] Read `brief.md`, `preferences.md` and `sent-log.md`.
- [ ] B: run `fetch_candidates.py` and `chatter.py` for Mon–Sun, and check `stats.json` failures.
- [ ] A: do the web pass for gaps (journals, CV workshops, named researchers/lab, policy & ocean, events, funding, ICYMI).
- [ ] Merge, dedupe, rank and verify everything. No neuro/psychedelic content.
- [ ] Write content.py, run `render.py --full`, then `check_issue.py`.
- [ ] Write `ab/<Sunday>/provenance.json`.
- [ ] Append to `archive/items.jsonl` with found_by.
- [ ] Publish (`build_archive_site.py`, `publish.sh`) and check the issue URL returns 200.
- [ ] Send, append to `sent-log.md` and post the chat note (status, link, 2–3 line summary with A/B/AB counts).

## 9. Not ported from Patrick's process / known gaps
- **biorxiv-top tracker:** its data covers neuroscience only, so it doesn't apply. bioRxiv ecology plus chatter cover this instead.
- **ClinicalTrials.gov:** irrelevant here; replaced by Zenodo datasets.
- **Altmetric** (needs a key), **Crossref Event Data** (sunset), **Reddit** (OAuth/blocked): not used.
- **Undermind / Edison:** no connector or plan for Amy; not used.
- **Optional keys:** `NCBI_API_KEY` and `OPENALEX_API_KEY` are optional and not set; the free tiers suffice.
- **Sync:** needs Amy's own PAT per device; it cannot be set up on her behalf.
- **Bot-voice check:** Patrick's "bro voice" check is dropped; Amy's check guards mix-ups and neuro content instead.

## 10. Routine prompt (current wording)
See the final report of the 4 Nov 2026 upgrade; the scheduled routine text is managed by the main bot. The key change: the step order is B sweep → A web pass → merge/verify → check_issue → provenance → archive → publish → send → sent-log.
