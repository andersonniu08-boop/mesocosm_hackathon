# AI Self-Recreation Benchmark — Design Document

## Overview

An RL-gym-style benchmark that measures how well AI can recreate programs from summaries. The pipeline: a **summarizer AI** analyzes human-written source code and produces a structured spec with I/O pairs; a **recreator AI** rebuilds the program from that summary; a **benchmark evaluator** scores the recreation across three dimensions — behavioral, structural, and human — and produces both an equal-weighted comprehensive score (the primary ranking metric) and the full 3-vector alongside.

The project is a **measurement instrument**, not a fixed problem set. The gym API is stable; the source programs fed into it can grow harder as models improve. This is the "wind tunnel" model of benchmarking: the instrument outlives any single test subject.

**Hackathon:** May 2026 | **Team:** 4 people (2 noobs, 2 mediocre vibecoders) | **Theme:** Novel ways to benchmark AI

---

## Core Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   RecreationGym (gym-style API)           │
│                                                          │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────┐   │
│  │ SOURCE   │    │ SUMMARY  │    │ RECREATION       │   │
│  │ PROGRAM  │───▶│ (struct  │───▶│ (one-shot code   │   │
│  │ (human-  │    │  spec +  │    │  generation;     │   │
│  │ written) │    │  public  │    │  iterative opt.) │   │
│  │          │    │  I/O ex) │    │                  │   │
│  └──────────┘    └──────────┘    └────────┬─────────┘   │
│                                           │             │
│                           ┌──────────┐    │             │
│                           │ PRIVATE  │    │             │
│                           │ I/O TESTS│◀───┘             │
│                           │ (hidden) │                  │
│                           └──────────┘                  │
│                                           │             │
│                                           ▼             │
│  ┌──────────────────────────────────────────────────┐   │
│  │              BENCHMARK EVALUATOR                  │   │
│  │                                                  │   │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────┐ │   │
│  │  │ BEHAVIORAL   │ │ STRUCTURAL   │ │  HUMAN   │ │   │
│  │  │ (I/O tests)  │ │ (ML model)   │ │ (rubric) │ │   │
│  │  └──────────────┘ └──────────────┘ └──────────┘ │   │
│  │                                                  │   │
│  │       ▼              ▼                ▼          │   │
│  │  ┌──────────────────────────────────────────┐   │   │
│  │  │  COMPREHENSIVE SCORE + 3-VECTOR (+ Pareto)  │   │   │
│  │  └──────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

---

## Decision Summary

| Decision | Choice | Priority |
|---|---|---|
| Measurement | Equal-weighted comprehensive score (33/33/33) with 3-vector returned alongside | Core |
| Summary format | Structured spec + public I/O examples + private test set | Core |
| Source material | Curate from open source (3 CLIs at 3 complexity bands) | Core |
| Recreator mode | One-shot (default), iterative with test feedback (optional) | Core / Optional |
| ML component | Semantic structural similarity scoring model (tree-sitter + linear regression) | Core |
| Pipeline architecture | Gym-style API (RecreationGym class) | Core |
| Spec completeness validator | Programmatic check before summary reaches recreator | Core |
| Prompt design | Dedicated prompt files in version control — prompts ARE the product | Core |
| Sandbox execution | Temp directory, 5s timeout, no network, cleanup after scoring | Core |
| Demo flow | 90-second scripted demo with side-by-side visualization | Core |
| Human rubric | Live-graded Saturday evening after pipeline works (30 min, 2 people) | Core |
| Extra metrics (efficiency, robustness, sim-to-real) | Time permitting | Optional |
| Cross-model baselines | Time permitting | Optional |
| Iterative recreator mode | Time permitting | Optional |
| Programmatic I/O mutation | Future work | Out of scope |

---

## The 3 Scores

### Score 1: Behavioral (Automated)

Run the recreated CLI against the exact same golden I/O pairs included in the summary. For each pair, compare stdout, stderr, and exit code.

```
behavioral_score = passed_pairs / total_pairs  (0-100)
```

Implementation: recreate CLI code in a temp directory, run with `subprocess.run()` inside a Docker container (or `preexec_fn` sandbox if Docker unavailable). 5-second timeout per test pair, no network access, restricted filesystem. If Docker is not available on the deployment platform, fall back to running in `/tmp/sandbox/<uuid>/` with restricted permissions. Each test pair runs in a clean temp directory that gets removed after scoring.

### Score 2: Structural (ML-Powered)

A two-stage pipeline that replaces naive AST diffing:

**Stage 1 — Feature extraction:** Parse both codebases using **tree-sitter** (language-agnostic AST parser, one `pip install tree-sitter`). Extracts the same features regardless of source language:
- AST node type counts (function definitions, conditionals, loops, error handlers)
- Cyclomatic complexity per function
- Function signature similarity (edit distance)
- Call graph structure
- Module/import/dependency structure
- Code-to-comment ratio

Tree-sitter supports Python, Go, Rust, JavaScript, and more — so the benchmark works across languages without changing the extraction code. If a source CLI uses an unsupported language, fall back to regex-based heuristics.

**Stage 2 — Similarity model:** A model trained on feature distances between original/recreation pairs. Human rubric scores serve as training labels. Two model options:
- **Default:** Linear regression (scikit-learn) — handles small N better than random forest, fewer parameters to overfit
- **Stretch:** Random forest regressor — if enough calibration data is generated (15+ examples)

With 10-15 calibration examples, linear regression gives data-derived weights — less arbitrary than hand-picked weights, but still noisy with small data. Report the model's r-squared alongside the score so users know how much to trust it. As the result database grows post-hackathon, the model improves without changing the interface. If training fails entirely, fall back to equal-weighted feature distance (all sub-features weighted equally — the least arbitrary default).

Why ML here: a naive AST diff says quicksort vs bubble sort = 0% similar. A trained model learns that different implementations of the same algorithm are semantically similar.

### Score 3: Human Rubric (Live-Graded)

2-3 team members grade recreations using a fixed rubric. Grading happens **Saturday evening** once the pipeline produces its first recreation outputs — no pre-hackathon prep needed. A simple grading UI (one HTML page, three sliders) makes it fast: 3-5 recreations graded in ~30 minutes with 2 people.

| Dimension | Weight | Scored 1-5 on... |
|---|---|---|
| Correctness | 40% | Does it do what the spec says? |
| Completeness | 30% | Are all features/subcommands present? |
| Code quality | 15% | Readable, well-structured, no obvious bugs? |
| Edge case handling | 15% | Error paths, bad input, graceful failure? |

Process: once the pipeline produces recreations Saturday evening, 2 people grade 3-5 recreations independently, then reconcile scores. These labeled examples also serve as training data for the structural ML model. More can be added Sunday as the pipeline runs more CLIs.

**Score independence caveat:** The three dimensions are partially correlated — the human rubric includes a correctness component that overlaps with behavioral scores, and the structural ML is trained on human labels. In practice, the scores will show some correlation. The Pareto method still surfaces cases where dimensions genuinely diverge (e.g., high behavioral + low structural = different implementation, same behavior).

**Live demo handling:** During the hackathon demo:
- **All runs** report all three scores — human grading was done Saturday evening, so scores exist for every recreation
- The grading UI can be shown to judges as part of the demo: "here's how we grade — and here's what the model produced"
- For a live interactive element: let a judge grade one recreation using the UI, then reveal the team's grade and compare

**Scale normalization:** The human rubric produces a 1-5 score. It is converted to 0-100 for consistency with behavioral and structural scores:

```
human_100 = (rubric_score - 1) / 4 * 100
```

| Rubric (1-5) | 0-100 equivalent |
|---|---|
| 5 (perfect) | 100 |
| 4 (good) | 75 |
| 3 (adequate) | 50 |
| 2 (poor) | 25 |
| 1 (broken) | 0 |

### Combined Output: Comprehensive Score + Vector

Each run produces:

- **Comprehensive score:** equal-weighted average of the three dimensions, each normalized to 0-100:

  ```
  comprehensive = (behavioral + structural + human) / 3
  ```

  This is the primary ranking metric — the answer to "which model did the best job overall?"

- **3-vector returned alongside:** `[behavioral, structural, human]` — so users can see *why* a model scored how it did, and re-weight themselves if they disagree with equal weighting.

- **Pareto frontier (secondary):** An entry dominates another if it is better or equal in ALL dimensions and strictly better in at least one. The frontier is computed and reported but the leaderboard ranks by comprehensive score.

Equal weights are the least arbitrary default. The weights are disclosed — users can recompute with their own preferences from the vector.

**Small-N caveat:** With few data points (3-5 runs), the Pareto frontier will be trivially flat. Pre-generate 10+ runs per band for a meaningful demo visualization.

---

## Summary Format: Structured Spec + Golden I/O Pairs

The summarizer receives source code and produces a document with three parts:

**Part 1 — Structured Spec:** A JSON template covering name, language, subcommands, flags, exit codes, error behavior, and dependencies.

**Part 2 — Public I/O Examples (shown to recreator):** 3-5 input/output examples per CLI, extracted by running the actual original program through a capture harness. These help the recreator understand expected behavior. Covers the main happy path for each subcommand.

**Part 3 — Private I/O Test Set (hidden from recreator):** 12-15 additional input/output pairs covering happy paths, error paths, edge cases, and boundary conditions. These are generated by the same capture harness but are **never shown to the recreator**. They are used exclusively for behavioral scoring.

The split prevents test leakage: the recreator sees enough examples to understand the program, but the behavioral score measures genuine recreation, not memorization of the test set.

### Spec Completeness Validator

Before the summary is passed to the recreator, a programmatic validator checks it:

- Structured spec has all required fields (name, language, subcommands, flags, exit codes)
- Public I/O examples exist for every subcommand (at least 1 each)
- At least 3 public examples and 12 private test pairs
- All I/O pairs are valid (parseable commands, non-empty expected output or documented error)

If any check fails, re-prompt the summarizer automatically (max 3 attempts). This is ~30 lines of Python and prevents the most common failure mode: the recreator receiving an incomplete or malformed spec.

---

## Source Material

Curate 3 human-written CLI tools from open source at escalating complexity:

| Band | Size | Characteristics |
|---|---|---|
| 1 | ~200 lines | Single purpose, stateless, 2-3 flags |
| 2 | ~500 lines | Multiple subcommands, file I/O, error handling |
| 3 | ~1000 lines | Stateful, algorithmic depth, multiple modules |

Selection criteria: human-written (verified via git history), self-contained, readable. Existing tests are nice-to-have but not required — the I/O capture harness generates the test set.

**Sourcing strategy:** Write 1-2 CLIs yourselves if finding 3 suitable open-source tools proves difficult. Your team-written CLIs are human-written and satisfy the constraint. Start searching this week — pick 5 candidates, narrow to 3 before Saturday.

The gym accepts any source directory — not hardcoded to 3 paths. After the hackathon, the pool can grow without code changes.

---

## Gym API

```python
from recreation_gym import RecreationGym

gym = RecreationGym(source_dir="./benchmarks/band2-csvtool")

result = gym.run(
    summarizer="claude-sonnet-4-6",
    recreator="claude-sonnet-4-6",
    mode="oneshot"  # or "iterative" (optional)
)

# result.comprehensive → 82.7  (equal-weighted: (92+71+85)/3)
# result.scores → {"behavioral": 92, "structural": 71, "human": 85}
# result.is_pareto_optimal → True
```

The API follows gymnasium conventions where applicable. Key principle: anyone can swap in their own summarizer or recreator and get comparable scores.

### Internal Pipeline Flow

1. **SummarizePhase:** LLM API call → structured_spec.json + public_io_examples.json (3-5 pairs) + private_io_tests.json (12-15 pairs, hidden)
2. **RecreatePhase:** LLM API call (one-shot or iterative) → recreated code directory. Recreator receives structured_spec.json + public_io_examples.json only. Private tests are never shown.
3. **EvaluatePhase:** Run behavioral tests (private I/O pairs) → extract features via tree-sitter → run ML model → look up human scores (scale to 0-100) → compute comprehensive score (equal-weighted avg) + Pareto ranking

---

## Platform Independence

The gym core is a pure Python package. Zero platform assumptions.

**Dependencies:** `anthropic`, `scikit-learn`, `numpy`, `tree-sitter`. Optionally `gradio` for the demo UI.

**Design rules:**
- No web framework in the core — the demo UI wraps the gym, not the reverse
- All state in JSON files on disk — no databases, no Redis, no migrations
- CLI-first entry point (`python -m gym demo`) always works
- Pre-compute LLM results — demos show cached output, no live API dependency

**Worst-case fallbacks:**
- No internet → replay cached LLM results
- SSH-only, no browser → CLI demo prints formatted results to terminal
- Read-only filesystem → write results to /tmp or stdout

---

## Project File Structure

```
ai-self-recreation/
├── gym/                    # Pure Python. Zero platform assumptions.
│   ├── __init__.py
│   ├── recreation_gym.py   # Main gym class
│   ├── summarizer.py       # LLM summarizer backend
│   ├── recreator.py        # LLM recreator backend
│   ├── spec_validator.py   # Spec completeness checker (~30 lines)
│   ├── evaluator/
│   │   ├── __init__.py
│   │   ├── behavioral.py   # I/O pair test runner
│   │   ├── structural.py   # Feature extractor + ML model
│   │   └── human.py        # Rubric loader / grader
│   └── pareto.py           # Pareto frontier computation
├── prompts/                # Prompt files — these ARE the product
│   ├── summarizer_system.txt
│   └── recreator_system.txt
├── cli.py                  # CLI entry point. Always works.
├── demo/
│   ├── gradio_app.py       # OPTIONAL. Only if platform supports web.
│   └── static_dashboard/   # OPTIONAL. Pre-generated HTML results.
├── benchmarks/             # Source CLIs + I/O pairs (plain files)
├── calibration/
│   ├── human_scores.json   # Graded rubric scores (live-graded Saturday evening)
│   └── train_model.py      # Train structural similarity model
├── results/
│   └── runs/               # JSON output per benchmark run
└── requirements.txt        # anthropic, scikit-learn, numpy, tree-sitter
```

---

## Weekend Plan

### Pre-Hackathon Prep (this week)

| Task | Who | Hours |
|---|---|---|
| Find and vet 5 open-source CLI candidates, narrow to 3 | 1 person | 3 |
| Write I/O capture harness (run original, capture outputs) | 1 person | 2 |
| Generate public + private I/O pairs for all 3 CLIs | 1 person | 2 |
| Set up project scaffolding + dependencies + git repo | 1 person | 1 |

### Saturday — Build the Pipeline

| Time | Task | Who |
|---|---|---|
| 9am-11am | **Whole team together:** scaffolding, summarizer prompt, first manual end-to-end | Everyone |
| 11am-1pm | Summarizer backend + spec validator | Vibecoder 1 + Noob 1 (pair) |
| 11am-1pm | Recreator backend + sandbox runner | Vibecoder 2 + Noob 2 (pair) |
| 1pm-3pm | Behavioral evaluator | Noob 1 (solo) |
| 1pm-3pm | Structural feature extractor | Noob 2 (solo) |
| 1pm-3pm | Wire up RecreationGym class | Vibecoder 1 |
| 1pm-3pm | Build grading UI (HTML page, 3 sliders) | Vibecoder 2 |
| 3pm-5pm | Train structural ML model | Vibecoder 1 + Noob 2 (pair) |
| 5pm-6pm | End-to-end integration test (Band 1) | Everyone |
| 6pm-6:30pm | **Human grading session** — grade 3-5 recreations | 2 people |
| 6pm-7pm | Run Band 2 + Band 3, collect all results | Everyone |

**Saturday target:** All 3 bands run + human grading done. Demo visualization roughed out.

### Sunday — Polish and Demo

| Task | Who | Hours |
|---|---|---|
| Build Pareto frontier + result visualizations | Noob 2 | 3 |
| Build demo UI (Gradio or CLI or static HTML) | Vibecoder 2 | 3 |
| Polish + edge cases + error handling | Vibecoder 1 + Noob 1 | 3 |
| Prepare demo script + practice presentation | Everyone | 2 |
| Demo! | Everyone | — |

**Sunday target:** Polished demo with all 3 bands, live grading UI, Pareto visualization, and the 90-second script.

### Optional (if ahead of schedule)

1. Iterative recreator mode — recreator sees test results and can revise (1-2 hrs)
2. Efficiency & robustness metrics — time runs, test with malformed input (1 hr)
3. Cross-model matrix — Claude + GPT + Gemini combos (1 hr if API keys ready)
4. Live human grading at demo — let judges grade one recreation live (30 min)

---

## Demo Flow

The 90-second demo script:

```
0:00-0:20  THE PROBLEM
           "AI can write code. But can it understand code well enough
           to recreate it from a description? There's no benchmark for that."

0:20-0:50  THE WIND TUNNEL (live playback)
           Show the gym running: source CLI on the left, summary in the center,
           recreation on the right. Scores overlay at the bottom.
           (Pre-computed, played back fast — not waiting for live API calls.)

0:50-1:15  THE LEADERBOARD
           Show comprehensive scores for all tested models, with 3-vector breakdowns.
           "Claude Opus: 82.7 overall [92B, 71S, 85H].
            GPT-4: 74.7 overall [88B, 56S, 80H].
            Opus wins across the board — but GPT-4 closes the gap on behavior."

1:15-1:30  THE PITCH
           "The gym is open-source. It never retires — just feed it harder
           programs. Like the wind tunnel, the instrument outlasts any single test."
```

The wow moment is the side-by-side recreation comparison with scores. Build that one visualization really well. Everything else (grading UI, leaderboard) can be functional but basic.

### Optional interactive element

Let a judge type a command into the original CLI, see the output, then run the same command through the recreation. Live A/B testing. Requires pre-warming both CLIs so they respond instantly.

---

## Risk Mitigation

| Risk | Mitigation |
|---|---|
| Can't find 3 good open-source CLIs | Write 1-2 yourselves; your code is human-written. Search 5 candidates this week. |
| ML model doesn't train well on small data | Use linear regression; fall back to equal-weighted feature distance (least arbitrary default) |
| Summarizer produces bad specs | Spec completeness validator — check required fields, re-prompt up to 3 times |
| Recreator produces broken code | That's valid data — a score of 0 is a benchmark result, not a bug |
| Recreator overfits to public I/O examples | Private test set (12-15 pairs) is never shown to recreator; catches memorization |
| Recreator generates unsafe code | Run in temp sandbox directory; 5s timeout; no network; clean up after scoring |
| LLM API rate limits or costs | Pre-generate and cache all LLM outputs before demo |
| Pareto frontier is trivial with small N | Pre-generate 10+ runs per band so demo shows meaningful dominance |
| Cross-language AST parsing fails | tree-sitter handles Python/Go/Rust/JS; regex fallback for unsupported languages |
| Human grading bottleneck on Saturday night | Grading UI takes 30 min for 2 people; 3-5 recreations is the target |

---

## Benchmarking Principles (from Turing RL Gym article)

The design is informed by 7 benchmarking principles. Items marked optional are stretched goals.

1. **Completeness criteria** — test suites must cover every flag, subcommand, and error path. I/O pairs capture real behavior including edge cases.
2. **Complexity bands** — three CLIs at escalating difficulty serve as tiered evaluation levels. Models that fail Band 2 get retested on Band 1.
3. **Multi-dimensional metrics** — five metric categories: success rate, constraint satisfaction, efficiency, robustness, sim-to-real delta. The three scores cover the first two; efficiency, robustness, and sim-to-real delta are **optional** stretch goals.
4. **Layered verifier architecture** — programmatic (behavioral tests), model-based (structural ML), human-in-the-loop (rubric grading). This maps directly to the three scores.
5. **Baselines and ablation** — cross-model comparison matrix (Claude vs GPT vs Gemini as summarizer and recreator). **Optional** stretch goal.
6. **Workflow diversity** — vary language, domain, and paradigm across source CLIs to prevent overfitting.
7. **Standardized interface** — the RecreationGym API enables reproducible experiments and cross-model comparison.

---

## Pitch

"We built the wind tunnel for AI self-recreation. Here are three programs we tested in it today. The gym is open-source — the community can add harder programs as models improve. The instrument doesn't retire when the test subjects get easy."
