# Software Evolution — Mesocosm Benchmark Plan

A Mesocosm evaluation environment that measures a model's ability to understand software precisely enough that another model can rebuild it from the description alone.

---

## 1. What This Measures

A model receives source code. It produces a genome (structured JSON spec). A fixed reconstructor (GPT-4o) rebuilds the program from the genome alone. The rebuild is tested against a private test suite. The model's score is the fraction of tests the rebuild passes.

The question: given only source code, can a model produce a spec precise enough that a different model can faithfully rebuild working software from it? This is the software equivalent of technical handoffs between teams. It measures informational precision of model understanding — how much meaning survives transmission.

---

## 2. Tier 1 — Single-Cycle Evaluation (MUST SHIP)

### Pipeline

```
Source Code (human-written Pong, ~100 lines)
        │
        ▼
┌──────────────────────────┐
│ MODEL UNDER TEST          │
│ Sees: source code only    │
│ Produces: genome JSON     │
│ Max tokens: per heat level│
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ SPEC VALIDATOR            │
│ Valid JSON?               │
│ All required fields?      │
│ Fields non-empty?         │
│ Within token budget?      │
│ Fail → re-prompt (1x)     │
│ Fail again → score = 0    │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ REFERENCE RECONSTRUCTOR   │
│ Fixed: GPT-4o, temp 0     │
│ Sees: genome only         │
│ Fills gaps on its own     │
│ Produces: source code     │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ BUILD CHECK               │
│ Does it compile?          │
│ No → score = 0            │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ SANDBOX TEST RUNNER       │
│ 20 private test scenarios │
│ subprocess.run() per test │
│ 5s timeout, temp dir      │
│ No network, no filesystem │
│ Captures stdout JSON      │
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

### The Genome (What the Model Produces)

The genome is a structured JSON specification. It replaces the old 5-field prose schema (purpose, interfaces, behavior, constraints, dependencies) with 8 typed, atomic fields that degrade gracefully under budget pressure.

```json
{
  "invocation": "python pong.py --ball-x <int> --ball-y <int> --ball-dx <int> --ball-dy <int> --paddle-left <int> --paddle-right <int> --score-left <int> --score-right <int> --frames <int>",
  "output_contract": {
    "format": "json",
    "on_success": "print all state vars as JSON to stdout, exit 0",
    "on_error": "exit 1, no stdout"
  },
  "arguments": [
    {"name": "ball-x", "type": "integer", "range": [0, 600], "required": true, "default": null},
    {"name": "ball-y", "type": "integer", "range": [0, 400], "required": true, "default": null},
    {"name": "ball-dx", "type": "integer", "required": true, "default": null},
    {"name": "ball-dy", "type": "integer", "required": true, "default": null},
    {"name": "paddle-left", "type": "integer", "range": [0, 400], "required": true, "default": null},
    {"name": "paddle-right", "type": "integer", "range": [0, 400], "required": true, "default": null},
    {"name": "score-left", "type": "integer", "required": true, "default": null},
    {"name": "score-right", "type": "integer", "required": true, "default": null},
    {"name": "frames", "type": "integer", "required": true, "default": null}
  ],
  "constants": [
    {"symbol": "FIELD_WIDTH", "value": 600},
    {"symbol": "FIELD_HEIGHT", "value": 400},
    {"symbol": "PADDLE_LENGTH", "value": 60},
    {"symbol": "PADDLE_LEFT_X", "value": 20},
    {"symbol": "PADDLE_RIGHT_X", "value": 580},
    {"symbol": "BALL_SIZE", "value": 6},
    {"symbol": "BALL_RADIUS", "value": 3},
    {"symbol": "HALF_PADDLE", "value": 30}
  ],
  "rules": [
    {
      "id": "move_ball",
      "trigger": "each frame",
      "effect": "ball_x += ball_dx * frames; ball_y += ball_dy * frames"
    },
    {
      "id": "wall_bounce_top",
      "trigger": "ball_y - BALL_RADIUS <= 0",
      "effect": "ball_dy = abs(ball_dy); ball_y = BALL_RADIUS"
    },
    {
      "id": "wall_bounce_bottom",
      "trigger": "ball_y + BALL_RADIUS >= FIELD_HEIGHT",
      "effect": "ball_dy = -abs(ball_dy); ball_y = FIELD_HEIGHT - BALL_RADIUS"
    },
    {
      "id": "left_paddle_hit",
      "trigger": "ball_x - BALL_RADIUS <= PADDLE_LEFT_X AND |ball_y - paddle_left| <= HALF_PADDLE",
      "effect": "ball_dx = abs(ball_dx); ball_x = PADDLE_LEFT_X + BALL_RADIUS"
    },
    {
      "id": "right_paddle_hit",
      "trigger": "ball_x + BALL_RADIUS >= PADDLE_RIGHT_X AND |ball_y - paddle_right| <= HALF_PADDLE",
      "effect": "ball_dx = -abs(ball_dx); ball_x = PADDLE_RIGHT_X - BALL_RADIUS"
    },
    {
      "id": "left_scoring",
      "trigger": "ball_x + BALL_RADIUS <= 0",
      "effect": "score_right += 1; ball_x = FIELD_WIDTH/2; ball_y = FIELD_HEIGHT/2; ball_dx = 5; ball_dy = 0"
    },
    {
      "id": "right_scoring",
      "trigger": "ball_x - BALL_RADIUS >= FIELD_WIDTH",
      "effect": "score_left += 1; ball_x = FIELD_WIDTH/2; ball_y = FIELD_HEIGHT/2; ball_dx = -5; ball_dy = 0"
    }
  ],
  "rule_order": [
    "move_ball", "wall_bounce_top", "wall_bounce_bottom",
    "left_paddle_hit", "right_paddle_hit",
    "left_scoring", "right_scoring"
  ],
  "error_conditions": [
    {"when": "any required argument is missing", "action": "exit 1"},
    {"when": "any argument is not a valid integer", "action": "exit 1"}
  ]
}
```

### Why This Schema (vs the Old 5-Field Schema)

| Old field | Problem | New design | Why better |
|-----------|---------|------------|------------|
| `purpose` (prose) | Zero reconstruction utility. Wasted tokens. | Removed entirely. | — |
| `interfaces` (prose) | Vague. "List CLI arguments" doesn't specify types or ranges. | `invocation` + `arguments[]` + `output_contract` | Each argument is typed, has range, has required/default. Independently compressible. |
| `behavior` (prose) | Monolithic blob. Dropping a sentence breaks logical coherence. | `rules[]` + `rule_order[]` | Each rule is an atomic trigger/effect pair. Dropping one rule breaks one feature, not the whole program. Graceful degradation. |
| `constraints` (prose) | Conflates invariants, error conditions, and numeric limits into one blob. | `constants[]` + `error_conditions[]` | Constants are typed (symbol + value). Error conditions are atomic trigger/action pairs. Separable. |
| `dependencies` | Lists imports without usage context. | Implicit in invocation and rules. | The reconstructor prompt tells GPT-4o what stdlib is available. Explicit listing adds noise. |
| *(new)* | No data flow described. | `rule_order[]` | Tells the reconstructor the pipeline: what fires first, second, third. Critical for correct behavior when rules interact. |
| *(new)* | No state vocabulary. | `state_vars[]` (in full genome) | Gives the reconstructor variable names for internal state beyond arguments. |

### Graceful Degradation

Under budget pressure, the model drops fields in this priority order (lowest first):

1. Drop individual rules (keep most critical ones)
2. Drop `rule_order` (reconstructor infers from dependencies)
3. Drop argument sub-fields (`range`, `default`) — keep `name` and `type`
4. Drop individual constants (least critical first)
5. Drop `error_conditions`
6. **NEVER drop** `invocation`, `output_contract`, or the first constant

Each field dropped causes a predictable, small FF reduction. The degradation curve is smooth, not a cliff.

### Scoring

**Functional Fidelity (FF)** — Primary. Range 0–1.

```
FF = passed_tests / 20
```

A test passes when: exit code matches expected, and the JSON fields in `stdout_keys` match the actual output exactly. 20 private scenarios across 6 categories (ball movement, wall bounce, paddle hit, scoring, edge cases, invalid input).

**Behavioral Similarity (BS)** — Secondary. Range 0–1.

```
BS = mean over passing tests: 1 - edit_distance(actual_stdout, expected_stdout) / max(|actual|, |expected|)
```

Failed tests contribute 0 to the BS average.

### Heat Levels

| Heat | Token Budget | Meaning |
|------|-------------|---------|
| 0 | Unlimited | Baseline. Saturate. Measures ceiling FF. |
| 1 | 500 | Standard. Moderate constraint. |
| 2 | 300 | Compression. Must prioritize what to keep. |
| 3 | 150 | Extreme. Below information-theoretic floor. Measures degradation quality. |

### Tier 1 Leaderboard

```
Rank | Model       | FF   | BS
-----|-------------|------|------
  1  | Claude      | 0.95 | 0.91
  2  | DeepSeek    | 0.85 | 0.82
  3  | GPT-4       | 0.75 | 0.73
```

Ranked by FF. Ties broken by BS.

---

## 3. Tier 2 — Multi-Generation Evolution (STRETCH)

### The Loop

Each rebuild becomes the next generation's source code. Token budget shrinks. Temperature ramps. The software evolves, degrades, or collapses.

```
Gen 0: Original Pong → [Summarizer] → Genome 0 → [Reconstructor] → Rebuild 0 → Test: FF=1.00
Gen 1: Rebuild 0   → [Summarizer] → Genome 1 → [Reconstructor] → Rebuild 1 → Test: FF=0.96
Gen 2: Rebuild 1   → [Summarizer] → Genome 2 → [Reconstructor] → Rebuild 2 → Test: FF=0.91
Gen 3: Rebuild 2   → [Summarizer] → Genome 3 → [Reconstructor] → Rebuild 3 → Test: FF=0.82
Gen 4: Rebuild 3   → [Summarizer] → Genome 4 → [Reconstructor] → Rebuild 4 → Test: FF=0.71
Gen 5: Rebuild 4   → [Summarizer] → Genome 5 → [Reconstructor] → Rebuild 5 → Test: FF=0.63
Gen 6: Rebuild 5   → [Summarizer] → Genome 6 → [Reconstructor] → Rebuild 6 → Test: FF=0.55
Gen 7: Rebuild 6   → [Summarizer] → Genome 7 → [Reconstructor] → Rebuild 7 → Test: FF=0.48
Gen 8: Rebuild 7   → [Summarizer] → Genome 8 → [Reconstructor] → Rebuild 8 → Test: FF=0.41
Gen 9: Rebuild 8   → [Summarizer] → Genome 9 → [Reconstructor] → Rebuild 9 → Test: FF=0.37
```

### Software Half-Life (HL)

The generation where the 5-generation rolling average of FF drops below 0.50. This is the number of AI-mediated handoffs the software survives before its behavior degrades beyond recognition.

```
Gen | FF    | 5-Gen Rolling Avg
----|-------|------------------
0   | 1.00  | -
1   | 0.96  | -
2   | 0.91  | -
3   | 0.82  | -
4   | 0.71  | 0.880
5   | 0.63  | 0.806
6   | 0.55  | 0.724
7   | 0.48  | 0.638
8   | 0.41  | 0.556
9   | 0.37  | 0.488  ← HL = 7 (center of the 5-gen window)
```

Why rolling average: a single bad genome (random LLM output) shouldn't kill the run. The average smooths noise and measures the sustained trend.

Why 0.50: below 50% of tests passing, the software has lost more behavior than it's retained. It's no longer recognizable as the original program.

### Extinction Generation

The generation where FF hits exactly 0. A secondary metric for when the software dies completely.

### Collapse Recovery

When FF drops to 0, the code resets to the original source. Budget resets to 500 tokens. Temperature resets to 0.1. This tests whether the model can recover from collapse or whether the environment fatally destabilizes.

### Evolutionary Pressure (Multi-Axis)

A single pressure axis (budget shrinking) measures ONE thing. Multiple axes produce a richer fitness profile.

| Pressure Axis | How It Works | What It Measures |
|---------------|-------------|------------------|
| **Budget** | Tokens shrink 5% per generation (floor at 50) | Information triage quality under scarcity |
| **Temperature** | T ramps 0.1 → 0.3 → 0.5 → 0.7 across generations | Robustness to stochastic noise (mutations) |
| **Reconstructor Switch** | Every 10 generations, swap GPT-4o → Claude and back | Cross-model portability of the genome |
| **Silent Mutation** | After summarization, randomly corrupt 10% of genome fields before reconstruction | Error correction capability |
| **Field Lock** | Some genome fields are locked — summarizer can only modify unlocked fields | Innovation within constraints |

### Fitness Score

Mean of all half-life scores across all pressure axes.

```
Rank | Model    | HL_budget | HL_temp | HL_recon | HL_mutate | Fitness
-----|----------|-----------|---------|----------|-----------|--------
  1  | Claude   | 42        | 38      | 35       | 29        | 36.0
  2  | DeepSeek | 37        | 41      | 22       | 31        | 32.8
  3  | GPT-4    | 24        | 28      | 18       | 19        | 22.3
```

This prevents a model hyper-optimized for one pressure from dominating. Different models have different weaknesses. A multi-axis benchmark finds them all.

### Minimum Viable Pressure Set for Hackathon

If all five axes are too much, ship these two:

1. **Budget shrinkage** — already designed, easy to implement
2. **Reconstructor switch every 10 generations** — requires two reconstructor models, low implementation cost

### Tier 2 Leaderboard

```
Rank | Model       | Half-Life | Extinction | FF@10 | FF@25 | Fitness
-----|-------------|-----------|------------|-------|-------|--------
  1  | Claude      | 42        | 55         | 0.94  | 0.71  | 36.0
  2  | DeepSeek    | 37        | 40         | 0.91  | 0.64  | 32.8
  3  | GPT-4       | 24        | 28         | 0.82  | 0.36  | 22.3
```

Ranked by Half-Life. Ties broken by Extinction. Second tie broken by mean FF across all generations.

### Sigmoid Budget Curve

Percentage-based shrinking (5%/gen) is too gradual at first and too aggressive at the end. Use a sigmoid:

```
budget(gen) = floor + (start - floor) × (1 / (1 + e^(k × (gen - midpoint))))
```

Where `k` controls steepness, `midpoint` is where half the budget is gone, `floor` prevents collapse to zero. This ramps up smoothly and stabilizes.

---

## 4. Pong Fixture

### What It Is

A headless, deterministic Pong game. No GUI. No randomness. One frame per CLI invocation. The program computes one frame and exits.

### CLI Interface

```
python pong.py \
  --ball-x 100 --ball-y 200 --ball-dx 5 --ball-dy 0 \
  --paddle-left 250 --paddle-right 300 \
  --score-left 0 --score-right 0 \
  --frames 1
```

### What It Computes (Per Frame)

1. Move ball: `ball_x += ball_dx`, `ball_y += ball_dy`
2. Wall bounce (top): if `ball_y - BALL_RADIUS <= 0`, flip `ball_dy`, clamp position
3. Wall bounce (bottom): if `ball_y + BALL_RADIUS >= FIELD_HEIGHT`, flip `ball_dy`, clamp position
4. Left paddle hit: if ball reaches `PADDLE_LEFT_X` and Y is within paddle range, flip `ball_dx`
5. Right paddle hit: if ball reaches `PADDLE_RIGHT_X` and Y is within paddle range, flip `ball_dx`
6. Left scoring: if ball past left edge, right scores +1, ball resets to center
7. Right scoring: if ball past right edge, left scores +1, ball resets to center
8. Print resulting state as JSON to stdout, exit 0

### Constants

```
FIELD_WIDTH = 600
FIELD_HEIGHT = 400
PADDLE_LENGTH = 60
PADDLE_LEFT_X = 20
PADDLE_RIGHT_X = 580
BALL_SIZE = 6
BALL_RADIUS = 3
HALF_PADDLE = 30
```

### Test Scenarios (20 Total, 3-4 Per Category)

| Category | Tests | What It Covers |
|----------|-------|----------------|
| Ball movement | 4 | Move right, move left, move diagonal, move multiple frames |
| Wall bounce | 3 | Hit top wall, hit bottom wall, approach wall without bounce |
| Paddle hit | 4 | Left paddle center, right paddle center, miss paddle above, hit paddle edge |
| Scoring | 3 | Left edge score (right gets point), right edge score (left gets point), paddle blocks score |
| Edge cases | 4 | Zero velocity, ball at corner, paddle at boundary, ball at exact paddle boundary |
| Invalid input | 2 | Missing required argument, non-numeric argument |

### Test Format

```json
{
  "id": "ball_move_01",
  "category": "ball_movement",
  "args": ["--ball-x", "100", "--ball-y", "200", "--ball-dx", "5", "--ball-dy", "0",
            "--paddle-left", "250", "--paddle-right", "300",
            "--score-left", "0", "--score-right", "0", "--frames", "1"],
  "expected": {
    "exit_code": 0,
    "stdout_keys": {
      "ball_x": 105, "ball_y": 200, "ball_dx": 5, "ball_dy": 0,
      "score_left": 0, "score_right": 0
    }
  }
}
```

`args` is a flat list — what `subprocess.run()` takes. `stdout_keys` lists only the fields to check. Extra fields in output are ignored. Invalid-input tests have `exit_code: 1` and no `stdout_keys`.

---

## 5. Implementation Plan

### What We Already Have

| File | Status |
|------|--------|
| `fixtures/pong/source.py` | Done — headless deterministic Pong (102 lines) |
| `fixtures/pong/tests.json` | Done — 20 test scenarios (20/20 pass) |
| `test_harness.py` | Done — `run_tests()` + `score()` (FF + BS) |

### Tier 1 — What We Need

| # | File | Does What |
|---|------|-----------|
| 1 | `prompts/summarizer.txt` | System prompt for the model under test. Tells it to analyze source code and produce the 8-field genome JSON. Includes the priority guide for graceful degradation: drop rules first, then rule_order, then arg sub-fields, then constants, then error_conditions. **Never drop invocation or output_contract.** Tone: pure technician, no roleplay. Return ONLY valid JSON, no markdown, no explanation. |
| 2 | `prompts/reconstructor.txt` | System prompt for GPT-4o (the fixed reconstructor). Tells it to rebuild Python code from the genome. Includes a **translation table**: `\|ball_dy\|` → `abs(ball_dy)`, `×` → `*`, `AND` → `and`. Includes **fallback rules** for each field if missing: order → infer from dependencies, constant → guess reasonable value, error_conditions → only validate required args. Tells it to use `argparse` or manual parsing. Output contract: JSON to stdout, exit 0/1. Return ONLY source code, no markdown fences. |
| 3 | `reference.py` | `reconstruct(genome_dict) → str`. Calls GPT-4o with the reconstructor prompt + the genome JSON. Strips markdown code fences. Retries up to 2x if build check fails. Temperature 0. |
| 4 | `spec_validator.py` | `validate_spec(spec_str, budget) → (is_valid, error_message, parsed_dict)`. Checks: valid JSON, all 8 required fields present, fields non-empty (no TBD/TODO/N/A placeholders), token count within budget + 20. |
| 5 | `environment.py` | `SummarizationEnv`. Orchestrator class. Constructor takes fixture_dir, model (AbstractModel), heat_level. `run()` method: loads source → calls model.summarize(source, budget) → validates genome (re-prompt once on failure) → calls reference.reconstruct(genome) → writes code to temp file → checks if code compiles → runs test_harness → returns result dict with FF, BS, token count, build status, heat, model, fixture. ~100 lines. |
| 6 | `run.py` | CLI entry point. `python run.py --model deepseek --heat 1 --fixture fixtures/pong`. Loads the model adapter, creates SummarizationEnv, runs it, saves result JSON to `results/<model>_heat<heat>.json`, prints FF/BS. ~40 lines. |
| 7 | `adapters/base.py` | `AbstractModel(ABC)`. One abstract method: `summarize(source_code: str, budget: int) -> dict`. |
| 8 | `adapters/deepseek.py` | DeepSeek adapter. Calls DeepSeek API (OpenAI-compatible, base_url=https://api.deepseek.com). Loads summarizer prompt. Sends source + budget. Returns parsed genome dict. ~30 lines. |
| 9 | `adapters/claude.py` | Claude adapter. Uses Anthropic SDK. Same pattern. ~30 lines. |
| 10 | `adapters/openai.py` | OpenAI adapter. Uses OpenAI SDK. Same pattern. ~25 lines. |
| 11 | `rank.py` | Reads all JSON files in `results/`. Prints leaderboard table sorted by FF desc, BS desc. ~25 lines. |

### Tier 2 — What We Need (After Tier 1 Works)

| # | File | Does What |
|---|------|-----------|
| 12 | `environment_multi.py` | `MultiGenEnv(SummarizationEnv)`. Subclass that overrides `run()` with a recursive loop. `run(generations=50)`: loads original source → for each generation, calls model.summarize(code, budget), calls reconstruct(genome), runs tests, records FF/BS/token_count/temperature, updates code to the rebuild, shrinks budget, ramps temperature. Supports multiple pressure axes via a `Pressure` protocol. Returns half-life, extinction, and full trajectory. ~100 lines. |
| 13 | `benchanything.json` | Mesocosm registration. Declares: benchmark name, version, track (agi-real-world-modeling), primary metric (functional_fidelity), secondary metric (behavioral_similarity), extended metrics (software_half_life), 7 heat levels (0-6, 0-3 for Tier 1, 4-6 for Tier 2), observation space (source_code + token_budget), action space (genome JSON), reward (FF). |

---

## 6. Prompt Design

### `prompts/summarizer.txt`

```
You are analyzing source code to produce a machine-readable specification.
Your output will be given to a code generator that rebuilds the program.
The generator sees ONLY your specification — never the original source.

Produce valid JSON with these fields:

  invocation       — exact CLI command template (e.g. "python pong.py --ball-x <int> …")
  output_contract  — success output format and error behavior
                     { format: "json", on_success: string, on_error: string }
  arguments[]      — for each CLI argument:
                     { name, type (integer|float|string|boolean), range [min,max],
                       required (true|false), default (value|null) }
  constants[]      — every hardcoded number the program depends on:
                     { symbol, value }
  rules[]          — one object per piece of logic:
                     { id, trigger (when it fires), effect (what changes) }
                     Write effects as pseudo-code. Use variable names from arguments.
                     Each rule must be independently meaningful — don't write
                     "same as rule X but for the other side."
  rule_order[]     — the order rules fire in (list of rule ids)
  error_conditions[] — when the program exits 1 and what triggers it:
                     { when, action }

PRIORITY GUIDE — if token budget is tight, drop fields in this order:
  1. Drop individual rules (keep most critical ones)
  2. Drop rule_order (generator will infer)
  3. Drop argument sub-fields (range, default) — keep name and type
  4. Drop individual constants (least critical ones first)
  5. Drop error_conditions
  6. NEVER drop invocation, output_contract, or the first constant

Return ONLY valid JSON. No explanation. No markdown fences.
```

### `prompts/reconstructor.txt`

```
You are rebuilding a program from a structured specification.
You have NO access to the original source code.

The specification has these possible fields:
  invocation, output_contract, arguments[], constants[], rules[], rule_order[], error_conditions[]

BUILDING RULES:
  Translate each rule's effect literally into Python code.
  A rule that says "ball_x += ball_dx" becomes: ball_x += ball_dx
  A rule that says "ball_dy = |ball_dy|" becomes: ball_dy = abs(ball_dy)
  A rule that says "exit 1" becomes: sys.exit(1)
  Use AND / OR as Python and / or.

HANDLING MISSING FIELDS:
  - If rule_order is missing: order rules by dependencies (write-after-read ordering)
  - If a constant is missing: GUESS a reasonable value (e.g. FIELD_WIDTH → 600)
  - If error_conditions are missing: only validate required args are present and numeric
  - If range is missing for an argument: use widest reasonable range
  - If arguments are incomplete: treat every listed argument as required

GENERAL RULES:
  - Use argparse or manual sys.argv parsing (your choice)
  - Print JSON to stdout on success, exit 0
  - Exit 1 (no stdout) on any error condition
  - Use CONSTANTS exactly as specified — do not change values
  - If a rule is ambiguous, pick the most reasonable interpretation

Return ONLY the source code. No explanation. No markdown fences.
No "```python" wrapping — just the raw code.
```

---

## 7. What Information Should and Should Not Survive Compression

### MUST Survive (Conserve Aggressively)

| Information | Why |
|---|---|
| Argument names and types | The test harness invokes with specific flag names. Wrong name = FF=0. |
| All numeric constants | Exact values. `PADDLE_LEFT_X=20` vs `30` changes collision behavior. |
| Output contract | "JSON to stdout, exit 0" is non-negotiable for the harness. |
| Rule effects | `ball_dx = abs(ball_dx)` must survive. If effects are lost, behavior is lost. |
| Exit conditions | The reconstructor needs to know when to exit 1 vs 0. |

### CAN Mutate Freely (No Need to Preserve)

| Information | Why Safe to Lose |
|---|---|
| Internal variable names | Tests only check stdout JSON keys, not internal Python variable names. |
| Code structure | Classes vs functions. One file vs modules. Reconstructor's choice. |
| Error message text | Harness checks exit code, not stderr. |
| Import style | `import json` vs `from json import dumps`. Identical. |
| Parser approach | `argparse` vs manual `sys.argv`. Both work. |

### GRADIENT: Partial Preservation Creates Evolution

| Information | How It Creates Diversity |
|---|---|
| Rule ordering | Move → bounce vs bounce → move. Different behaviors, both possibly correct. |
| Constant precision | Dropped constant → reconstructor guesses. Wrong guess = wrong behavior = lower FF. |
| Rule granularity | "wall_bounce" (1 rule) vs "wall_bounce_top" + "wall_bounce_bottom" (2 rules). Different token costs, different precision. |

The genome is a **lossy compression** of source code. Not lossless. Preserve functional identity. Allow implementation to drift.

---

## 8. How This Maps to Mesocosm

### The Env Interface

The Mesocosm platform runs an agent loop: `reset() → observation → [agent] → action → step(action) → reward → ...`.

**Our mapping:**

- **reset(seed):** Load Pong source code from `fixtures/pong/source.py`. Return it as observation with instructions to produce a genome JSON.
- **step(action):** Parse the agent's action as the genome JSON. Validate it. Call GPT-4o to reconstruct code. Write to temp file. Run test harness. Return FF as reward. `terminated=True` (single-step episode).
- **Scoring:** `episode_reward` with `mean` aggregation across episodes. Different seeds = different runs for statistical significance.

### Benchinanything.json Registration

```json
{
  "binding_vow": {
    "observation_space": { "type": "json", "description": "source_code + instruction" },
    "action_space": { "type": "json", "schema_ref": "<genome JSON schema>" },
    "reward": { "type": "scalar", "range": { "low": 0.0, "high": 1.0 } },
    "episode": { "max_steps": 1, "deterministic_reset": true }
  },
  "scoring": {
    "primary_metric": "functional_fidelity",
    "metrics": [{"name": "functional_fidelity", "type": "episode_reward", "aggregation": "mean"}]
  }
}
```

---

## 9. File Tree

```
mesocosm_hackathon/
├── fixtures/pong/
│   ├── source.py              ✅ Headless deterministic Pong
│   └── tests.json             ✅ 20 test scenarios
├── test_harness.py            ✅ run_tests() + score()
│
├── prompts/
│   ├── summarizer.txt         📋 New: model-under-test prompt
│   └── reconstructor.txt      📋 New: GPT-4o rebuild prompt
├── adapters/
│   ├── base.py                📋 New: AbstractModel ABC
│   ├── deepseek.py            📋 New: DeepSeek adapter
│   ├── claude.py              📋 New: Claude adapter
│   └── openai.py              📋 New: OpenAI adapter
├── reference.py               📋 New: GPT-4o reconstruct()
├── spec_validator.py          📋 New: genome validation
├── environment.py             📋 New: Tier 1 orchestrator
├── run.py                     📋 New: CLI entry point
├── rank.py                    📋 New: leaderboard
│
├── environment_multi.py       📋 New (stretch): Tier 2 loop
├── benchanything.json         📋 New: Mesocosm registration
│
└── requirements.txt           📋 New: openai, anthropic
```

✅ = Already done. 📋 = Needs implementation.

---

## 10. Implementation Order

| Phase | Step | Depends On |
|-------|------|------------|
| **0** | Pong source + tests + harness | Nothing (done) |
| **1** | `prompts/summarizer.txt` + `prompts/reconstructor.txt` | Nothing — pure text, no code dependencies |
| **2** | `adapters/base.py` + `adapters/deepseek.py` | Nothing — pure API integration |
| **3** | `reference.py` + `spec_validator.py` | Reconstructor prompt, OpenAI key |
| **4** | `environment.py` | Everything above |
| **5** | `run.py` | environment.py |
| **6** | `rank.py` + `benchanything.json` | Results from running |
| **7 (stretch)** | `environment_multi.py` | environment.py working |
| **8 (stretch)** | Multi-axis pressures | Tier 2 loop working |
