# Software Evolution — Mesocosm Evaluation Environment

**A benchmark that measures a model's ability to understand software precisely enough that another model can rebuild it from the description alone.**

---

## 1. Overview

Software Evolution is a **Mesocosm evaluation environment** for code understanding fidelity.

**Core question:** Given only a program's source code, can a model produce a specification precise enough that a different model can rebuild working software from it?

The model under test acts as the **summarizer**. It receives source code and nothing else. It produces a structured JSON specification. A fixed reference reconstructor (GPT-4o, held constant) rebuilds the program from that spec — filling in any gaps with its best guess. The rebuild is tested against a private test suite. The model's score is the fraction of tests the rebuild passes.

**One model per run. Two metrics per model. One leaderboard.**

---

## 2. Delivery Strategy — Two Tiers

### Tier 1 — Code Understanding Benchmark (MUST SHIP)

Single-cycle evaluation. One summarization, one reconstruction, one score.

- **Build time:** 12-14 hours
- **Submit as:** Complete Mesocosm environment with 4 heat levels and 1 fixture (Pong)
- **Fallback:** This alone is a valid, submission-worthy benchmark
- **Novelty:** Reconstruction-based evaluation of summarization quality is not a standard benchmark approach

### Tier 2 — Multi-Generation Evolution (STRETCH)

Wraps Tier 1 in a recursive loop. Each rebuild becomes the next generation's input. Token budget shrinks each cycle. Models compete on Software Half-Life.

- **Build time:** +6-8 hours on top of Tier 1
- **Submit as:** Additional 3 heat levels and an extended metric
- **Novelty:** Very high. Nobody measures software concept survival across AI-mediated generations
- **Requires:** Tier 1 fully working first. Tier 2 is `MultiGenEnv(SummarizationEnv)` — a subclass, not a rewrite.

---

## 3. Tier 1 — Single-Cycle Pipeline

```
SOURCE CODE (human-written Pong, ~200 lines)
        │
        ▼
┌──────────────────────────┐
│ MODEL UNDER TEST          │
│ Sees: source code only    │
│ Produces: JSON spec       │
│ Fields: purpose,          │
│ interfaces, behavior,     │
│ constraints, dependencies │
│ Max tokens: per heat level│
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ SPEC VALIDATOR            │
│ Is it valid JSON?         │
│ Are all fields present?   │
│ Are fields non-empty?     │
│ Fail → re-prompt (1x).    │
│ Fail again → score = 0.  │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ REFERENCE RECONSTRUCTOR   │
│ Fixed: GPT-4o.            │
│ Sees: spec only.          │
│ Fills gaps on its own.    │
│ Produces: source code.    │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ BUILD CHECK               │
│ Does it parse? Import?    │
│ No → score = 0           │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ SANDBOX TEST RUNNER       │
│ 20 private test scenarios │
│ subprocess.run() per test │
│ 5s timeout. Temp dir.     │
│ No network.               │
│ Captures stdout JSON.     │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ SCORING                   │
│ FF = passed / 20          │
│ BS = mean output closeness│
│ (edit distance on stdout) │
└──────────────────────────┘
```

### The Task

Model receives:

```json
{
  "source_code": "<full Pong source>",
  "token_budget": 500
}
```

Model produces:

```json
{
  "purpose": "A single-player Pong game...",
  "interfaces": [
    {
      "name": "Headless CLI",
      "args": ["--ball-x", "--ball-y", "--ball-dx", "--ball-dy",
               "--paddle-left", "--paddle-right",
               "--score-left", "--score-right", "--frames"],
      "output": "JSON to stdout with new state",
      "exit_codes": "0 on success, 1 on invalid input"
    }
  ],
  "behavior": "Computes next game state: moves ball, checks wall/paddle collisions, updates score...",
  "constraints": "Ball must stay within field bounds. Paddles are fixed-length. Score increments when ball passes paddle...",
  "dependencies": ["json", "sys", "argparse"]
}
```

The model never writes code, never sees test results, and never sees the reconstructor's output.

### Scoring

**Functional Fidelity (FF)** — Primary. Range 0–1.

```
FF = passed_tests / 20
```

A test passes when: exit code matches expected, and the JSON fields specified in expected output all match within tolerance (integers exact, floats ±1). 20 private scenarios across 6 categories.

**Behavioral Similarity (BS)** — Secondary. Range 0–1.

```
BS = mean over passing tests: 1 - edit_distance(actual_stdout, expected_stdout) / max(|actual|, |expected|)
```

### Leaderboard

```
Rank | Model       | FF   | BS
-----|-------------|------|------
  1  | Claude      | 0.95 | 0.91
  2  | DeepSeek    | 0.85 | 0.82
  3  | GPT-4       | 0.75 | 0.73
```

Ranked by FF. Ties broken by BS.

---

## 4. Tier 2 — Multi-Generation Evolution (STRETCH)

```python
class MultiGenEnv(SummarizationEnv):
    def run(self, model, generations=50):
        code = self.original_source
        budget = 500
        temp = 0.1
        results = []

        for gen in range(generations):
            spec = model.summarize(code, budget)     # reuses Tier 1 summarizer
            code = self.reconstructor.build(spec)     # reuses Tier 1 reconstructor
            ff, bs = self.harness.evaluate(code)      # reuses Tier 1 harness
            results.append({"gen": gen, "ff": ff, "bs": bs, "budget": budget})
            budget *= 0.95
            temp = self._temp_schedule(gen)

        return {"half_life": self._half_life(results), "trajectory": results}
```

### Evolution Pressure

| Generations | Token Budget | Temperature |
|-------------|-------------|-------------|
| 0–3 | 500 tokens | 0.1 |
| 4–15 | 500 × 0.95^gen | 0.3 |
| 16–35 | Shrinking further | 0.5 |
| 36+ | Floor at 50 tokens | 0.7 |

### Software Half-Life (HL)

Generation at which smoothed FF (5-gen rolling average) drops below 0.5. Primary Tier 2 metric.

### Tier 2 Leaderboard

```
Rank | Model       | Half-Life | Extinction | FF@10 | FF@25
-----|-------------|-----------|------------|-------|------
  1  | Claude      | 42        | 55         | 0.94  | 0.71
  2  | DeepSeek    | 37        | 40         | 0.91  | 0.64
  3  | GPT-4       | 24        | 28         | 0.82  | 0.36
```

---

## 5. Heat Levels

| Heat | Tier | Token Budget | Behavior |
|------|------|-------------|----------|
| 0 | 1 | No limit | Baseline. No pressure. |
| 1 | 1 | 500 tokens | Standard. Moderate constraint. |
| 2 | 1 | 300 tokens | Compression. Must prioritize. |
| 3 | 1 | 150 tokens | Extreme. Minimal information budget. |
| 4 | 2 | 500 → shrink 5%/gen | Multi-gen baseline. |
| 5 | 2 | 500 → shrink 8%/gen | Accelerated decay. |
| 6 | 2 | 500 → shrink 10%/gen | Aggressive. Concept survival at the limit. |

---

## 6. Pong Fixture

### CLI interface

```
python pong.py --ball-x 100 --ball-y 200 --ball-dx 5 --ball-dy 0 \
               --paddle-left 250 --paddle-right 300 \
               --score-left 0 --score-right 0 --frames 1
```

Stdout:

```json
{"ball_x": 105, "ball_y": 200, "ball_dx": 5, "ball_dy": 0,
 "paddle_left": 250, "paddle_right": 300,
 "score_left": 0, "score_right": 0}
```

Exit 0 on success. Exit 1 on invalid input or internal error.

### Test scenario categories (20 total, 3-4 per category)

| Category | What it tests |
|----------|---------------|
| **Ball movement** | Position updates correctly with given velocity. |
| **Wall bounce** | Ball reverses dy on top/bottom walls. |
| **Paddle hit** | Ball reverses dx on paddle contact. |
| **Scoring** | Ball passing paddle increments opponent score, resets position. |
| **Edge case** | Zero velocity, ball at exact boundary, paddle at extreme position. |
| **Invalid input** | Missing args, non-numeric values, out-of-range values. Returns exit code 1. |

### Test scenario format

```json
{
  "id": "ball_move_01",
  "category": "ball_movement",
  "args": {"ball_x": 100, "ball_y": 200, "ball_dx": 5, "ball_dy": 0,
           "paddle_left": 250, "paddle_right": 300,
           "score_left": 0, "score_right": 0, "frames": 1},
  "expected": {
    "exit_code": 0,
    "stdout_keys": {
      "ball_x": 105, "ball_y": 200, "ball_dx": 5, "ball_dy": 0,
      "score_left": 0, "score_right": 0
    }
  }
}
```

The harness passes `args` as CLI flags, captures stdout JSON, checks `exit_code` and compares `stdout_keys` fields against actual output.

---

## 7. Spec Validator

Checks (in order):

1. Output is valid JSON.
2. All required fields present: `purpose`, `interfaces`, `behavior`, `constraints`, `dependencies`.
3. No field is empty or contains only placeholder text.
4. Token count is within budget (if over by 20+ tokens, re-prompt; otherwise accept).

Max 2 attempts. Fail twice → score = 0.

---

## 8. Prompts

### Summarizer (model under test)

Tone: pure technician. No roleplay. No persona.

```
Analyze the following source code. Produce a JSON specification with these fields:

- purpose: What does this program do? (2-3 sentences)
- interfaces: How is the program invoked? List CLI arguments, expected input format, output format, exit codes.
- behavior: How does the program compute its output from its inputs? Be precise.
- constraints: What limits, invariants, and error conditions must the program enforce?
- dependencies: What libraries or modules does the program require?

Be precise. A different developer will rebuild the program from your specification alone.
They will not see the original source code. Your specification is all they have.
```

### Reconstructor (reference, GPT-4o)

```
You are rebuilding a program from a specification. You do not have access to
the original source code.

Write complete, runnable Python code that implements the specification.
If the specification is ambiguous or incomplete, fill in the gaps with your
best reasonable guess to produce a working program.

The program will be tested via command line. It must print JSON to stdout
and exit 0 on success, exit 1 on error.

Return ONLY the source code. No explanation.
```

---

## 9. Architecture

```
software-evolution/
│
├── environment.py              # SummarizationEnv (Tier 1, ~200 lines)
├── environment_multi.py        # MultiGenEnv(SummarizationEnv) (Tier 2, ~100 lines)
├── test_harness.py             # subprocess runner, FF + BS scoring
├── spec_validator.py           # JSON schema + field checks
├── reference.py                # GPT-4o reconstructor
│
├── adapters/
│   ├── base.py                 # AbstractModel
│   ├── deepseek.py             # ~30 lines each
│   ├── claude.py
│   └── openai.py
│
├── fixtures/
│   └── pong/
│       ├── source.py           # Human-written (~200 lines)
│       ├── tests.json          # 20 private test scenarios
│       └── runner.sh           # Wraps: python pong.py --ball-x X ...
│
├── prompts/
│   ├── summarizer.txt
│   └── reconstructor.txt
│
├── run.py                      # python run.py --model deepseek --heat 1
├── rank.py                     # Reads results/, prints leaderboard
├── benchanything.json          # Mesocosm registration
└── requirements.txt            # openai
```

No React. No FastAPI. No database. No WebSocket. No SQLite. No frontend framework. No Docker.

---

## 10. Mesocosm Integration

### benchanything.json

```json
{
    "name": "software-evolution",
    "version": "1.0.0",
    "type": "benchmark",
    "track": "agi-real-world-modeling",
    "description": "Measures a model's ability to produce specifications from which a different model can rebuild working software. In multi-generation mode (Tier 2), measures software concept survival across recursive AI-mediated transmission.",
    "primary_metric": "functional_fidelity",
    "secondary_metric": "behavioral_similarity",
    "extended_metrics": ["software_half_life"],
    "heat_levels": [0, 1, 2, 3, 4, 5, 6],
    "observation_space": {
        "source_code": "string",
        "token_budget": "integer"
    },
    "action_space": {
        "specification": "structured_json"
    },
    "reward": "functional_fidelity",
    "fixtures": ["pong"]
}
```

### Run export (Tier 1)

```json
{
    "benchmark": "software-evolution",
    "tier": 1,
    "heat_level": 1,
    "model_under_test": "deepseek-chat",
    "reference_reconstructor": "gpt-4o",
    "fixture": "pong",
    "functional_fidelity": 0.85,
    "behavioral_similarity": 0.82,
    "tests_passed": 17,
    "tests_total": 20,
    "build_succeeded": true,
    "spec_token_count": 423,
    "spec_is_valid": true
}
```

### Run export (Tier 2)

```json
{
    "benchmark": "software-evolution",
    "tier": 2,
    "heat_level": 4,
    "model_under_test": "deepseek-chat",
    "reference_reconstructor": "gpt-4o",
    "fixture": "pong",
    "software_half_life": 37,
    "extinction_generation": 40,
    "trajectory": [
        {"gen": 0, "ff": 1.00, "bs": 1.00, "budget": 500, "temp": 0.1},
        {"gen": 1, "ff": 0.96, "bs": 0.94, "budget": 475, "temp": 0.1}
    ]
}
```

---

## 11. Development Plan — 24 Hours

| Block | Hours | Task | Ships |
|-------|-------|------|-------|
| 0–2 | Fixture | Write Pong source + 20 test scenarios + runner.sh | Test data exists |
| 2–4 | Harness | subprocess runner, JSON parsing, FF + BS scoring | Scoring works |
| 4–5 | Prompts | Write summarizer.txt + reconstructor.txt | Prompts ready |
| 5–7 | Env | SummarizationEnv: model→spec→validate→reconstruct→test→score | **Tier 1 engine** |
| 7–8 | Adapters | AbstractModel + DeepSeek/Claude/GPT adapters | Models pluggable |
| 8–10 | Run | End-to-end per model. Debug prompts. Iterate. | **Tier 1 results** |
| 10–11 | Rank | rank.py, leaderboard table | **Tier 1 leaderboard** |
| 11–12 | Mesocosm | benchanything.json, export format | **Tier 1 shippable** |
| 12–13 | Buffer | Edge cases, error handling, pre-compute demo data | **Tier 1 solid** |
| | | | |
| 13–16 | T2 engine | MultiGenEnv subclass: loop, budget shrink, temp ramp, collapse recovery | Tier 2 running |
| 16–18 | T2 runs | 50-gen runs all models. Extract half-life. | Tier 2 results |
| 18–20 | T2 rank | Half-life leaderboard, trajectory export | **Tier 2 shippable** |
| 20–22 | Demo viz | Static HTML: comparison + leaderboard + trajectory graph | Demo ready |
| 22–24 | Rehearse | Practice pitch, verify offline | Ready |

---

## 12. Why Mesocosm AGI & Real-World Modeling

The benchmark measures **informational precision of understanding**. A model must read a working system, build an internal model of its behavior, and encode that understanding into a specification — with enough fidelity that a different model can faithfully rebuild the system.

This maps directly to real-world technical handoffs: product specs from PM to engineering, architecture documents across teams, API contracts between services. Every software organization runs on transmitted understanding. The benchmark measures whether a model's description is a lossless encoding of intent, or whether meaning decays in transmission.

In Tier 2 multi-generation mode, this becomes a model of information degradation through repeated handoff — the software equivalent of the telephone game. Different models produce different evolutionary trajectories. Simplification, mutation, and collapse are emergent properties of the environment, not scripted behavior.

---

## 13. Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Tier 1 delayed | Tier 1 is the submission. 13 hours budgeted for a 24-hour hackathon. It ships. Tier 2 is additive bonus. |
| Pong too complex | 200 lines. Headless CLI mode. No rendering. Pure game logic. Deterministic. Testable with exact outputs. |
| Model outputs bad JSON | Spec validator catches it. Re-prompt once. Score 0 on second failure. |
| Reconstructor builds broken code | Score = 0. Valid data. A model whose spec can't be rebuilt IS a worse model. |
| Multi-gen too stable (no drift) | Budget shrinks 5%/gen at heat 4. By gen 50 budget is ~40 tokens. At heat 6 with 10% shrink and high temp, something will break. If not: the benchmark is saturated. Publish it. Add harder fixtures post-hackathon. |
| API rate limits | Pre-compute and cache all LLM responses. Demos read cached JSON. |
| Reconstructor inconsistency | GPT-4o at temp 0. Retry reconstruct up to 2 times if build check fails. |
| Test harness breaks on valid variations | stdout comparison uses key-level JSON matching, not string equality. Tolerates whitespace/order differences. |

---

*Document v3.1 — Dual-tier, Mesocosm-native. May 2026 Hackathon.*
