# Literature Deep Dive: the full process

Amy's (Aimee du Luart's) weekly science newsletter, written by **Nudibranchi**. It arrives on Monday mornings (UK time) and covers the previous Monday–Sunday. The searchable archive lives at https://aimee-duluart.github.io/literature-deep-dive/.

This file was written on 4 Nov 2026. It ports the paper-search upgrade that Mochi built for Patrick's Neurodynamics Digest (his `docs/PROCESS.md`, 1 Nov 2026), retuned for Amy's interests. **Updated 9 Nov 2026** to Patrick's 9 Nov snapshot (upstream commit `7b3af31`, see `upstream-sync.json`): Catch-up section, extra meta rows, archive Catch-up tab, provenance schema, usage flag, monthly gap check, plain-text email card body. `brief.md` is still the authority; if it and this file disagree, follow the brief. **Never mix this digest with Patrick's** (data, site, mail, routines).

## Contents
1. Moving parts
2. File layout
3. Interests and ranking (summary of the brief)
4. Discovery: the combined method (B database sweep → A web pass → 3b Catch-up picks → merge/verify → provenance)
5. Writing and building the issue
6. Publishing and the archive site (graph view, sync)
7. Sending, sent-log and feedback
8. Weekly checklist
9. Not ported from Patrick's process / known gaps
10. Routine prompt (current wording)
11. Catch-up section
12. Keeping in step with Patrick's process (upstream-sync.json)

## 1. Moving parts
| Part | Where |
|---|---|
| Brief (source of truth) | `/workspace/amy-digest/brief.md` |
| Preferences (likes/dislikes) | `/workspace/amy-digest/preferences.md` |
| Sent-log | `/workspace/amy-digest/sent-log.md` |
| Catch-up never-repeat log | `/workspace/amy-digest/catchup-log.jsonl` (checker: `build/catchup_check.py`) |
| Upstream sync marker | `/workspace/amy-digest/upstream-sync.json` (last Patrick commit ported) |
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
  brief.md  preferences.md  sent-log.md  catchup-log.jsonl  upstream-sync.json  HANDOVER.md  docs/PROCESS.md
  pipeline/  common.py sources.py queries.json fetch_candidates.py chatter.py README.md  out/<Sunday>/
  build/     render.py compact.py section_icons.py house_style.py archive_items.py check_issue.py catchup_check.py content_sample_template.py
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

### 4.3b Step 3b: Catch-up picks (after the web pass)
Choose the 5 Catch-up papers for the final section (rules in §11). This is a separate look-back search (about 10 years), not part of the weekly window, and Catch-up papers are **not** counted in A/B/AB.

### 4.4 Provenance
Save `/workspace/amy-digest/ab/<Sunday>/provenance.json`. Since 9 Nov 2026 use Patrick's de-facto schema (Issue 003 carries both the old and new keys):
```json
{"issue": "004", "issue_date": "2026-11-16", "coverage": "2026-11-09 to 2026-11-15",
 "counts": {"total_weekly": 0, "A_only": 0, "B_only": 0, "both": 0, "catchup": 5},
 "note": "Free text: what each method supplied, notable single-method finds, items surfaced but excluded (and why), chatter summary.",
 "items": [{"section": "The headline act", "title": "...", "doi": "10.xxxx/...", "url": "https://doi.org/...", "found_by": "B"}]}
```
- `items` lists only the weekly (in-window) items. The 5 Catch-up papers are counted in `counts.catchup` and have no `found_by`.
- Write the same `found_by` to each weekly archive row; Catch-up rows get `catchup: true` instead (archive_items.py does this automatically for the "Catch-up" section).

## 5. Writing and building the issue
- Copy the latest `issue-<nnn>/content.py` as a template (Issue 003 is the first with Catch-up; `build/content_sample_template.py` has an `EXAMPLE_CATCHUP` skeleton) and fill it in following the brief's sections and tone.
- **Section order:** headline act first, thematic sections, explainer, datasets/tools, critiques/nulls, policy & ocean, events/training, funding, then **Catch-up always last** (from Issue 004; Issue 003's updated edition already has it).
- **`extra` rows:** a `main` item may carry `extra=[(LABEL, text), ...]`, rendered after "Why it matters for you" and before the refs in the web copy, and as `Label: text` lines in the plain text. Catch-up uses SINCE THEN / READING LEVEL / CODE/DATA.
- **Compact email copy (≤80 KB):** to stay under the cap, `compact.py` shows the explainer as a short teaser and Catch-up as one linked line per paper (title, authors, venue, year, reading level), both pointing to the web issue (Patrick's email does the same for the explainer). The full web copy (`--full`) has everything. Issue 003 updated is 79.5 KB compact, so keep weekly items lean (the brief asks for a ~20-minute read).
- `render.py` writes to the absolute `OUT_*` paths in `content.py`. When testing a template, change those first or you'll overwrite that issue's real outputs.
- Build with `python3 build/render.py --full` to get the full HTML, the compact HTML (<80 KB) and the plain text.
- **Then run the pre-send checks:** `python3 build/check_issue.py issue-<nnn>/issue-<nnn>-compact.html issue-<nnn>/issue-<nnn>.html issue-<nnn>/issue-<nnn>.txt`. These check:
  - compact ≤80 KB and no CJK
  - no neuroscience/psychedelic terms
  - only the +deepdive address (Amy's own address may appear only as text)
  - no Neurodynamics/Patrick/Mochi mix-ups
  - no dark body background and the Nudibranchi sign-off
  - from Issue 004 on: a `Catch-up` section that is the **last** section with exactly 5 items (web copy: 5 SINCE THEN rows; compact: 5 linked lines; plain text: a CATCH-UP heading)
- Fix anything flagged before you send.

## 6. Publishing and the archive site
- In `site/`, add `issues/<nnn>.html`, update `index.html` (below the `<!-- ISSUES (newest first) -->` marker), append to `archive/items.jsonl`, run `python3 build/build_archive_site.py`, then `AMY_GITHUB_TOKEN=… build/publish.sh "Issue nnn"`.
- Never force-push, and never touch the `user-state` branch.
- **Archive** (`archive/index.html`): section tabs (the tab list is the `SECTIONS` array in `archive/index.html` and `archive/graph.html`; a tab appears once a section has items; **Catch-up 🐢 tab added 9 Nov 2026** so Catch-up papers form their own shelf. Add any new section name to both arrays and to `build/section_icons.py`); chips for ecosystem, data modality, task, study type and **publication status (new)**; more filters; star / to-read / read / not interested; More like this; Send my preferences to Nudibranchi. A **publication-status badge** (Peer reviewed / Preprint / Reviewed preprint) appears on cards, also on the shortlist.
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
- Item pages show the Catch-up extras (area, Since then, reading level, code/data) when present.
- `site/docs/PROCESS.md` and `site/tools/pipeline/` are published copies (no outputs, no secrets).

## 7. Sending, sent-log and feedback
- Send one email from the +deepdive inbox to <RECIPIENT_EMAIL> (automatic, no draft card, per Amy 3 Nov 2026), with the subject "Literature Deep Dive #<n>: <highlights>".
- **Email body (from Patrick's 9 Nov process):** if the send path only takes basic HTML or plain text (draft cards do), send a condensed plain-text body in this order: (1) title line `Literature Deep Dive #<n>. <date>, covering <window>.`; (2) `Full issue (with caveats and why-it-matters notes): <web link>`; (3) the "Hi Mermaid Queen!" intro and theme paragraph; (4) each section as a numbered heading (`01 THE HEADLINE ACT`, …) with one bullet per item: headline (authors · venue · date) <DOI link>; short items one line; the explainer says "(in the web issue)"; (5) the 5 Catch-up papers last (title, authors, venue, year, DOI); (6) feedback line, next-issue time, "— Nudibranchi 🐚" and the disclaimer. Issue 003 went out via a draft card that Amy pressed Send on.
- **Chat note:** status, web link, 2–3 lines with A-only / B-only / both counts. **Usage flag:** check usage after the run and mention it only if the run used roughly double the baseline or more (baseline: set from the first measured combined+Catch-up run). **Gap check:** in the chat note for the first issue of each month, ask Amy for 2–3 papers she considers essential and log them in `catchup-log.jsonl` with `known: true`.
- Append the items to `sent-log.md` (`## Issue nnn · date · STATUS` header, then `- [nnn] Title — URL — date`). The pipeline drops DOIs listed there.
- The email-requests routine handles the archive/shortlist/preferences mailto subjects, always to the +deepdive address.

## 8. Weekly checklist
- [ ] Read `brief.md`, `preferences.md`, `sent-log.md` and `catchup-log.jsonl`.
- [ ] B: run `fetch_candidates.py` and `chatter.py` for Mon–Sun, and check `stats.json` failures.
- [ ] A: do the web pass for gaps (journals, CV workshops, named researchers/lab, policy & ocean, events, funding, ICYMI).
- [ ] Pick 5 **Catch-up** papers (§11): rotate areas (themed week ~monthly), ≤1 pre-2016, `python3 build/catchup_check.py <doi|title> …` must print ok for each, verify each, find Since then / reading level / code-data.
- [ ] Merge, dedupe, rank and verify everything. No neuro/psychedelic content.
- [ ] Write content.py, run `render.py --full`, then `check_issue.py`.
- [ ] Write `ab/<Sunday>/provenance.json`.
- [ ] Append to `archive/items.jsonl` with `build/archive_items.py` (found_by on weekly items; Catch-up rows get `catchup: true` + extras automatically).
- [ ] Append 5 lines to `catchup-log.jsonl`.
- [ ] Publish (`build_archive_site.py`, `publish.sh`) and check the issue URL returns 200.
- [ ] Send, append to `sent-log.md` and post the chat note (status, link, 2–3 line summary with A/B/AB counts; usage flag only if ~2× baseline; gap-check question on the first issue of the month).

## 9. Not ported from Patrick's process / known gaps
- **biorxiv-top tracker:** its data covers neuroscience only, so it doesn't apply. bioRxiv ecology plus chatter cover this instead.
- **ClinicalTrials.gov:** irrelevant here; replaced by Zenodo datasets.
- **Altmetric** (needs a key), **Crossref Event Data** (sunset), **Reddit** (OAuth/blocked): not used.
- **Undermind / Edison:** no connector or plan for Amy; not used.
- **Optional keys:** `NCBI_API_KEY` and `OPENALEX_API_KEY` are optional and not set; the free tiers suffice.
- **Sync:** needs Amy's own PAT per device; it cannot be set up on her behalf.
- **Bot-voice check:** Patrick's "bro voice" check is dropped; Amy's check guards mix-ups and neuro content instead.
- **9 Nov 2026 upstream changes not ported:** "Best reviews of the week" moving to second-to-last (Amy's brief has no Best reviews section); the EEG-section, biorxiv-top and psychedelic-specific rules; `PROCESS_shared.md` (Patrick's generic shareable doc; this file already serves that role for Amy); a "themed week" was not used for Issue 003 (first Catch-up), so the first themed week is still to come.

## 10. Routine prompt (current wording)
See the final report of the 4 Nov 2026 upgrade; the scheduled routine text is managed by the main bot. The key change: the step order is B sweep → A web pass → 3b Catch-up picks → merge/verify → check_issue → provenance → archive (+ catchup-log) → publish → send → sent-log → chat note (counts; usage flag; monthly gap check).

## 11. Catch-up section (ported 9 Nov 2026 from Patrick's 4–5 Nov rule; first used in Issue 003's updated edition)
Purpose: make sure Mermaid Queen hasn't missed the field's must-read papers.
- **Exactly 5 papers** per issue from roughly the **last 10 years** (2016 on); now and then (at most about one a week) a truly foundational pre-2016 paper. Aim for high-impact, well-cited or foundational methods and findings.
- **Rotate across Amy's areas** week to week and record each pick's area: CV/ML for species interactions; multimodal AI and interaction networks; bioacoustics/PAM and soundscape ecology; coral reef ecology and restoration; behaviour classification, pose and tracking; transferable CV/ML (camera traps, detection/tracking, self-supervised and foundation models); emerging tools (eDNA, remote sensing, biologging, ML for conservation); climate and human impacts and ecosystem services; restoration and NbS; community ecology theory. Issue 003 covered: camera-trap CV, interaction networks, bioacoustics, coral reef soundscapes, ML for conservation.
- **Never repeat a paper:** check `catchup-log.jsonl`, `archive/items.jsonl`, `archive/shortlist.jsonl` and `sent-log.md` by DOI and title (`build/catchup_check.py` does all four). Skip Amy's own papers and anything she says she already knows.
- **No neuroscience or psychedelic content**, including neuroscience-journal papers (check_issue would flag the venue name).
- **Verify every paper** (Crossref/DOI page, Europe PMC, OpenAlex, arXiv). Never invent.
- **Each item** is a normal `main` item: tags (status, year, type, area), the paper title as headline, byline (authors · venue · year), what it found, "Why it mattered:", caveats, "Why it matters for you" tied to her work, then the extras as `extra` rows:
  - **SINCE THEN:** one verified line on what came next (replication, critique, standard tool), with a link.
  - **READING LEVEL:** exactly one of "Skim the abstract", "Read the methods", "Worth a full read".
  - **CODE/DATA:** public code or data she could reuse; **omit the row if none is found**.
- **Themed week**, about once a month: all 5 tell one connected story (e.g. "from Snapshot Serengeti to MegaDetector", "how reef soundscapes became a restoration tool"), ordered so each builds on the last, with a one-line theme intro.
- **Gap check:** in the chat note for the first issue of each month, ask Amy for 2–3 essential papers; log them in `catchup-log.jsonl` with `"known": true` (no issue) so they're never recommended back.
- **After the issue:** append one line per paper to `catchup-log.jsonl`: `{"date": "2026-11-09", "doi": "10.xxxx/...", "title": "...", "year": 2018, "interest_area": "...", "issue": "003"}`; archive them with section "Catch-up" (own archive tab).
- Look: icon 🐢, accent turtle copper `#8a4a1c` on tint `#fbeadb` (6.8:1 on white).

## 12. Keeping in step with Patrick's process
- `upstream-sync.json` records the last commit of `Pattricksk/neurodynamics-digest` that has been reviewed and ported. To check for new upstream changes (read-only): clone or fetch the public repo into a temp dir and run `git log <synced_commit>..origin/main` and `git diff <synced_commit> origin/main -- docs/ tools/ archive/index.html archive/graph.html archive/sync.js`. Ignore issue content (`issues/`, `archive/item/`, `archive/items.json`).
- Port only process changes, retuned to Amy (no neuroscience/psychedelic rules, +deepdive address only, light ocean style), then update this file, the brief change log and `upstream-sync.json`.
- Never push to, comment on or modify Patrick's repo or `/workspace/newsletter`.
