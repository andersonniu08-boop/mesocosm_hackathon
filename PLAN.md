# Software Evolution — Mesocosm Redesign Plan

---

## Phase 1: Repository Analysis

### swecc-core Architecture

The swecc-core monorepo contains the **BenchAnything / Mesocosm platform** — an LLM evaluation system for benchmarking models against environments. Key architecture:

| Component | Location | Role |
|---|---|---|
| `BaseEnv` | `bench_common/env_sdk/base.py` | Abstract class env authors subclass. Must implement `reset(seed, **params) -> dict` and `step(action) -> StepResult`. Optional: `close()`, `render()`, `parse_action()`. |
| `StepResult` | `bench_common/env_sdk/base.py` | Dataclass: `observation`, `reward`, `terminated`, `truncated`, `info`, `system_prompt`, `content_type`. |
| `serve()` | `bench_common/env_sdk/server.py` | One-line HTTP adapter: wraps any `BaseEnv` into the 5-endpoint protocol (`/health`, `/reset`, `/step`, `/close`, `/render`). |
| `DomainConfig` | `bench_common/env_sdk/registration.py` | Python-side of `benchanything.json`. Contains `id`, `name`, `binding_vow`, `endpoint`, `scoring`, `tags`. |
| `BindingVow` | `bench_common/core/binding_vow.py` | Typed contract: `observation_space` (SpaceSpec), `action_space` (SpaceSpec), `reward` (RewardSpec), `episode` (EpisodeSemantics), `techniques[]`. |
| `ScoringConfig` | `bench_common/core/scoring.py` | `primary_metric`, `metrics[]` (MetricDef with name, type, aggregation). Supported types: `episode_reward`, `terminal_field`. |
| `AgentLoop` | `bench_common/runtime/agent_loop.py` | Platform's execution engine. Calls `reset()` → loop: `LLM inference` → `step(action)` → check termination → `close()`. |
| `HttpEnvClient` | `bench_common/runtime/env_client.py` | Platform's async HTTP client speaking the 5-endpoint protocol. |
| `compute_scores()` | `bench_common/eval/metrics.py` | Aggregates episode results per MetricDef (mean, median, max, min, sum, pass_rate). |
| `Technique` | `bench_common/techniques/base.py` | Hook system for memory, tool-calling, multi-agent. Injects context before/after each step. |

**Critical constraint**: The env author writes `BaseEnv.reset()` and `BaseEnv.step()`. **The platform does everything else** — LLM inference, agent loop, scoring aggregation, leaderboard, run management. The env is NOT a simulation engine or pipeline orchestrator. It is a Gym-like environment exposed over HTTP.

**Episode lifecycle (platform view)**:
```
POST /reset {episode_id, seed}
  → env.reset(seed) → returns initial observation dict
LOOP:
  LLM inference (structured output per action_space schema)
  → POST /step {episode_id, action}
    → env.step(action) → StepResult(obs, reward, terminated, truncated, info)
    → if terminated or truncated: exit loop
POST /close {episode_id}
  → env.close()
SCORE: compute_scores(scoring_config, [episodes])
```

### arithmetic-env Architecture (Reference Implementation)

A 5-file repository. The canonical Mesocosm env pattern:

| File | Purpose |
|---|---|
| `benchanything.json` | Manifest at repo root: id, name, binding_vow (obs/action/reward space specs, episode semantics), scoring config, tags. The platform reads this from the repo root on submission. |
| `env.py` | `ArithmeticEnv(BaseEnv)`: `reset(seed)` generates 10 problems deterministically, `step(action)` checks `action["answer"]` against ground truth, advances to next problem. ~80 lines. |
| `adapter.py` | `serve(ArithmeticEnv, port=8765)` — 10-line HTTP wrapper. Platform calls this to reach the env. |
| `requirements.txt` | Extra pip deps beyond `swecc-mesocosm`. Arithmetic uses stdlib only — file is empty except comments. |
| `LOCAL_DEV.md` | Development walkthrough: setup, local testing with Ollama, platform submission, Docker workflow. |
| `showcase/` | Replay export examples for demo frontends. |

**Episode flow** (10-step episode):
```
reset(seed=42) → {"problem": "12 + 7", "problem_num": 1, "total_problems": 10}
step({"answer": 19}) → StepResult(obs={"problem": "8 * 3", ...}, reward=1.0, terminated=False)
... 8 more steps ...
step({"answer": 7}) → StepResult(obs={"result": "done", "score": "8/10"}, reward=1.0, terminated=True)
```

**Key patterns from arithmetic-env**:
1. Observations are plain dicts (JSON-serializable)
2. Actions use `schema_ref` so LLMs produce structured output
3. Reward is per-step (1.0 correct, 0.0 wrong) — episode-level score = mean reward
4. `deterministic_reset=true` with seed support for reproducibility
5. All `info` dict values MUST be strings (enforced by adapter server)
6. `max_steps` declared in binding vow matches env logic
7. `episode_reward` metric type with `mean` aggregation for scoring
8. The env is ~80 lines — trivial once you understand the pattern

### Environment Lifecycle

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  env.py      │────▶│  adapter.py  │────▶│  Platform    │
│  (BaseEnv)   │◀────│  (HTTP)      │◀────│  (AgentLoop) │
└──────────────┘     └──────────────┘     └──────────────┘
```

The env IS the deliverable. Not the dashboard. Not the runner. Not the leaderboard. The platform provides those.

---

## Phase 2: Compatibility Review

### What the current PLAN.md gets wrong

| # | Problem | Why it matters | Fix |
|---|---|---|---|
| **1** | **Multiple internal model calls.** The design calls GPT-4o inside `reference.py` as a "reconstructor." The env has `environment.py` orchestrating both a "summarizer" model call AND a "reconstructor" model call. | In Mesocosm, the env does NOT call models. The platform calls exactly ONE model per step. The env only implements `reset()` and `step()`. This is the single biggest architectural misunderstanding. | Remove `reference.py`, remove all internal model calls. The model under test is the sole agent. The env is a state machine that presents observations and evaluates actions. |
| **2** | **Model adapters (`adapters/deepseek.py`, `adapters/claude.py`, `adapters/openai.py`).** The plan builds its own model abstraction layer and API clients. | The platform handles all LLM inference via litellm. Env authors do NOT write model adapters. The platform submits any model (gemini, claude, deepseek, gpt) through a uniform interface. | Delete the entire `adapters/` directory. The platform does this. |
| **3** | **Custom orchestrator (`environment.py`, `run.py`, `rank.py`).** The plan builds its own benchmark harness with CLI entry points and result ranking. | The platform provides `mesocosm run create` and the leaderboard. Env authors do not build experiment runners. | Replace `environment.py` with a proper `env.py` that extends `BaseEnv`. Delete `run.py` and `rank.py`. |
| **4** | **Prompts directory (`prompts/summarizer.txt`, `prompts/reconstructor.txt`).** System prompts stored as files for the env to inject into model calls. | The platform manages prompts. The env's binding vow defines observation space descriptions that guide the agent. If needed, `system_prompt` can be set in the reset/step result. | Remove `prompts/` directory. Embed instructional context in observation fields and the binding vow description. |
| **5** | **`benchanything.json` as an afterthought.** Listed at step 13 in implementation order, after all the custom infrastructure is built. | `benchanything.json` is the FIRST thing that defines the env. It declares the contract (observation space, action space, reward, scoring). Everything else conforms to it. | Design `benchanything.json` FIRST, then implement `env.py` to fulfill that contract. |
| **6** | **Single-step episode (`max_steps: 1`).** The plan has the model produce a genome, the env reconstructs via GPT-4o, and the episode ends. | This throws away Mesocosm's multi-step capability. A 1-step episode where the env does all the work isn't measuring the model — it's measuring GPT-4o. | Use multi-step episodes where the model alternates between compression and reconstruction. Each step is a model action. |
| **7** | **`spec_validator.py` with re-prompt logic.** The plan validates genomes and re-prompts the model on failure. | The env cannot re-prompt the model. The env can only return observations and rewards. The model decides what to do next based on those. | Replace validation with reward shaping: invalid genomes get penalty reward and the same observation again, giving the model a chance to correct. |

### What the current plan gets right

| Element | Status | Notes |
|---|---|---|
| Pong fixture (`fixtures/pong/source.py`) | Good | Deterministic, headless, JSON I/O. Excellent source program candidate. |
| Test scenarios (`fixtures/pong/tests.json`) | Good | 20 well-categorized test cases. Can be used for functional fidelity scoring. |
| `test_harness.py` | Good | `run_tests()` and `score()` are clean. Can be imported by `env.py` for functional evaluation. |
| Genome schema design | Interesting | The 8-field structured JSON genome is a reasonable compression format. Can be simplified for MVP. |

### Removed vs Kept

| Removed | Kept (repurposed) |
|---|---|
| `adapters/` (entire directory) | `fixtures/pong/` — becomes one of the source programs |
| `environment.py` | `test_harness.py` — used inside `env.py` for functional scoring |
| `run.py` | Pong source code — observation content |
| `rank.py` | |
| `reference.py` | |
| `spec_validator.py` | |
| `prompts/` | |
| `environment_multi.py` | |

---

## Phase 3: Environment Design

### Core Concept

**The environment presents source code. The model compresses it to a genome. Then the model reconstructs from that genome. The cycle repeats for multiple generations. Fidelity degrades — measuring how well the model preserves information across repeated compression-decompression cycles.**

Each generation = 2 steps:
1. **Compress step**: Model sees source → produces genome
2. **Reconstruct step**: Model sees genome → produces reconstruction

The reconstruction becomes the source for the next generation. After N generations, the episode ends. Score = mean fidelity across generations.

### Observation Space

**Compress phase observation** (`phase: "compress"`):
```json
{
  "phase": "compress",
  "generation": 1,
  "max_generations": 5,
  "source_code": "def fibonacci(n):\n    if n <= 1:\n        return n\n    return fibonacci(n-1) + fibonacci(n-2)",
  "source_length": 89,
  "budget_chars": 60
}
```

**Reconstruct phase observation** (`phase: "reconstruct"`):
```json
{
  "phase": "reconstruct",
  "generation": 1,
  "max_generations": 5,
  "genome": "fib(n):0,1->n<2?n:f(n-1)+f(n-2)",
  "genome_length": 35,
  "original_source_length": 89
}
```

### Action Space

A single unified action schema (the model fills whichever field is relevant to the current phase):
```json
{
  "type": "object",
  "properties": {
    "genome": {
      "type": "string",
      "description": "Compressed representation of the source code."
    },
    "reconstruction": {
      "type": "string",
      "description": "Reconstructed source code from the genome."
    }
  },
  "anyOf": [
    {"required": ["genome"]},
    {"required": ["reconstruction"]}
  ]
}
```

`parse_action()` routes based on current phase: compress phase reads `genome`, reconstruct phase reads `reconstruction`.

### Reward Function

| Step type | Reward | Formula |
|---|---|---|
| **Compress** | Budget adherence | `1.0` if genome within budget, `0.0` if over |
| **Reconstruct** | Fidelity | `normalized_edit_similarity(source, reconstruction)` — range [0, 1] |

`normalized_edit_similarity(a, b) = 1 - levenshtein(a, b) / max(len(a), len(b))`

This produces a per-step reward of 0–1. Episode total_reward = sum of all step rewards. Since episodes have a fixed number of steps (2×max_generations), the mean reward is directly comparable across runs.

### Scoring Configuration

```json
{
  "scoring": {
    "primary_metric": "fidelity",
    "higher_is_better": true,
    "metrics": [
      {
        "name": "fidelity",
        "type": "episode_reward",
        "aggregation": "mean"
      }
    ]
  }
}
```

Because `episode_reward` with `mean` aggregation gives the average per-step reward across all episodes, which is equivalent to the mean fidelity across all generations.

### Episode Structure (State Machine)

```
STATE DIAGRAM:

reset() → COMPRESS (generation 1)

COMPRESS:                  RECONSTRUCT:
┌─────────────────┐       ┌─────────────────────┐
│  obs: source     │       │  obs: genome          │
│  action: genome  │──────▶│  action: reconstruct   │
│                  │       │                        │
│  reward: budget  │       │  reward: fidelity      │
│  next: RECONSTRUCT│      │  next: COMPRESS or DONE │
└─────────────────┘       └─────────────────────┘
       ▲                           │
       │                           │
       └───────────────────────────┘
            (next generation)

DONE when generation > max_generations
```

### Source Program Library

For the MVP, use a library of small Python programs. Each program:
- 5–30 lines
- 50–500 characters
- Has a defined purpose (math, strings, algorithms)
- Is self-contained (single function or small class)

Categories:
- **Math**: fibonacci, factorial, gcd, is_prime, sum_of_squares
- **Strings**: reverse, is_palindrome, count_vowels, longest_word
- **Algorithms**: binary_search, bubble_sort, merge_sorted, find_max
- **Data**: flatten_list, unique_elements, count_frequency

The Pong fixture (102 lines) serves as a **hard** tier program.

### Compression Budget

Budget scales with source length:
```
budget = max(20, floor(source_length × 0.6))
```

This forces meaningful compression (at least 40% reduction) while keeping a floor so very short programs are still compressible.

---

## Phase 4: MVP Definition

### What we MUST build

| Component | Lines (est.) | Why |
|---|---|---|
| `env.py` — `SoftwareEvolutionEnv(BaseEnv)` | ~120 | The deliverable |
| `adapter.py` — HTTP wrapper | ~15 | Required by platform |
| `benchanything.json` — Full manifest | ~60 | Required for registration |
| `programs.py` — Source program library | ~200 | Content for the env |
| `fidelity.py` — Edit distance utility | ~25 | Scoring logic |
| `requirements.txt` | ~5 | Platform dependency list |
| `tests/test_env.py` — Smoke tests | ~80 | Reliability |
| `LOCAL_DEV.md` — Dev guide | ~40 | Onboarding |

**Total: ~545 lines of Python**

### What we CUT (and why)

| Component | Reason for removal |
|---|---|
| Dashboard / visualization | Platform provides leaderboard + replay viewer |
| Experiment manager / `run.py` | `mesocosm run create` handles this |
| Model adapters (`adapters/*`) | Platform handles all LLM inference via litellm |
| Custom orchestrator (`environment.py`) | Replaced by `BaseEnv` subclass (`env.py`) |
| Result ranking (`rank.py`) | Platform provides leaderboard |
| Internal reconstructor (`reference.py`) | Model under test does reconstruction, not a separate GPT-4o |
| Prompt files (`prompts/*`) | Observation descriptions in binding vow guide the agent |
| Spec validator with re-prompt | Replaced by reward shaping in step() |
| Database / persistence | Platform stores runs, episodes, traces |
| Web frontend | Platform has web UI at mesocosm.swecc.org |
| Multi-axis pressure system | Stretch goal only (budget shrinkage is in MVP) |

### MVP Feature Set

1. **3 generations × 2 steps = 6-step episodes** (keeps runs fast for hackathon)
2. **30 source programs** across 4 categories, 3 difficulty tiers
3. **Character budget** per generation (60% of source length)
4. **Normalized edit similarity** as fidelity metric (stdlib only, no deps)
5. **Deterministic reset** with seed for reproducibility
6. **Structured output** action schema for Gemini/Claude/GPT
7. **Early termination** if reconstruction fidelity = 0.0
8. **Info traces** with generation fidelity, compression ratios

### What makes this technically impressive

- **Software Half-Life**: How many generations until fidelity drops below 50%? A quotable, comparable metric.
- **Information Theory in Practice**: Measures how well different models preserve semantic content through repeated lossy compression — genuinely novel in LLM benchmarking.
- **Model differentiation surface**: Some models may be great compressors but weak reconstructors, others balanced. The two-phase design reveals architectural differences.
- **Compression budget metagame**: Models must strategize what information to preserve when under space constraints.

### Hackathon viability (2-4 devs, 24-48 hours)

| Phase | Hours | Output |
|---|---|---|
| Core env (`env.py` + `programs.py` + `fidelity.py`) | 8–10 | Working single-generation cycle |
| Platform integration (`benchanything.json` + `adapter.py` + local test) | 4–6 | Valid binding vow, `mesocosm run local` works |
| Model comparison (platform submit + 3+ model runs) | 4–6 | Score data showing differentiation |
| Polish (more programs, edge cases, docs) | 4–6 | Submission-ready env |

---

## Phase 5: Repository Plan

```
mesocosm_hackathon/
├── benchanything.json        # Manifest: binding vow, scoring, tags
├── env.py                     # SoftwareEvolutionEnv(BaseEnv)
├── adapter.py                 # serve(SoftwareEvolutionEnv, port=8765)
├── programs.py                # Source program library + seeded generator
├── fidelity.py                # normalized_edit_similarity(), token_overlap()
├── requirements.txt           # Extra pip deps (stdlib only expected)
├── LOCAL_DEV.md               # Dev workflow guide
├── .gitattributes             # Git config
├── .gitignore                 # Python gitignore
│
├── fixtures/                  # Content assets (used by env at runtime)
│   └── pong/                  # Pong: the hard-tier source program
│       ├── source.py          #   Headless deterministic Pong (102 lines)
│       └── tests.json         #   20 test scenarios for functional validation
│
├── test_harness.py            # run_tests() + score() — imported by env.py for functional fidelity (stretch)
│
├── showcase/                  # Demo replay exports
│   └── README.md
│
└── tests/
    ├── __init__.py
    └── test_env.py            # pytest: reset determinism, step cycle, termination, rewards
```

### File Responsibilities

| File | Responsibility |
|---|---|
| `benchanything.json` | Full manifest: domain id, name, description, binding_vow (obs/action space specs, reward spec, episode semantics), scoring config (primary metric + aggregation), tags |
| `env.py` | `SoftwareEvolutionEnv` class extending `BaseEnv`. State machine: `__init__`, `reset(seed)`, `step(action)`, `parse_action()`. Internal state: current phase, generation counter, stored source/genome, source library index |
| `adapter.py` | `if __name__ == "__main__": serve(SoftwareEvolutionEnv, port=8765)` |
| `programs.py` | `PROGRAMS: list[dict]` — each with `name`, `source`, `tier`, `category`. `get_program(seed, tier=None) -> dict` |
| `fidelity.py` | `normalized_edit_similarity(a: str, b: str) -> float` |
| `requirements.txt` | Lists extra packages beyond `swecc-mesocosm`. Expected: empty (`# stdlib only`) |
| `fixtures/pong/` | Pre-built fixture. `source.py` is one of the hard-tier programs. `tests.json` enables functional scoring (stretch). |
| `test_harness.py` | `run_tests(program_path, tests) -> results` and `score(tests, results) -> (ff, bs)`. Used inside env.py for functional fidelity scoring (stretch). |
| `tests/test_env.py` | pytest tests: `test_deterministic_reset`, `test_compress_then_reconstruct_cycle`, `test_termination_after_max_generations`, `test_reward_range`, `test_info_types_are_strings`, `test_early_termination_on_zero_fidelity` |
| `LOCAL_DEV.md` | Setup: `pip install swecc-mesocosm`, local dev with `mesocosm run local`, platform submit workflow, FAQ |

### Files that should NOT exist

- `adapters/` — platform handles model inference
- `environment.py` / `run.py` / `rank.py` — platform does orchestration
- `reference.py` — no internal model calls
- `spec_validator.py` — reward shaping handles validation
- `prompts/` — binding vow descriptions guide the agent
- `dashboard/` / `visualization/` — platform provides UI
- `docker-compose.yml` — platform sandboxes envs
- `pong-game/` — GUI game is unrelated to the benchmark (keep only headless fixture)
- `experiments/` — platform manages runs

---

## Phase 6: Implementation Roadmap

### Phase 1: Core Environment (8–10 hours)

**Objective**: Working `SoftwareEvolutionEnv` with single-generation verify

**Tasks**:
1. Write `fidelity.py` — `normalized_edit_similarity(a, b)` using Levenshtein distance (stdlib only)
2. Write `programs.py` — 30 programs across 4 categories, 3 tiers
3. Write `env.py`:
   - `__init__`: phase tracking, generation counter, source/genome storage
   - `reset(seed)`: pick program from library, return compress-phase observation
   - `parse_action(action)`: route to genome or reconstruction based on phase
   - `step(action)`: compress phase stores genome, checks budget, returns reconstruct obs. Reconstruct phase computes fidelity, advances generation, returns next obs or terminates
   - Terminal info: `generations_completed`, `final_fidelity`, `fidelity_history`, `compression_ratios`
4. Write `tests/test_env.py`: deterministic reset, cycle correctness, termination, reward bounds, info string types

**Dependencies**: Python 3.11+, pytest

**Verification**:
```bash
cd mesocosm_hackathon
python -m pytest tests/ -v
```

### Phase 2: Platform Integration (4–6 hours)

**Objective**: Valid benchanything.json, adapter, local test run

**Tasks**:
1. Write `benchanything.json`:
   - `id`: `"software-evolution"`
   - `adapter`: `"adapter.py"`
   - `binding_vow`: version `1.0.0`, tier `tier1`
   - `observation_space`: type `json`, with clear description
   - `action_space`: type `json`, with `schema_ref` for structured output
   - `reward`: type `scalar`, range `[0.0, 4.0]` (max 2 compress + 2 reconstruct steps per gen, 3 gens)
   - `episode`: `max_steps: 6`, `deterministic_reset: true`, `supports_seed: true`
   - `scoring`: `episode_reward` with `mean` aggregation
   - `tags`: `["software", "evolution", "compression", "information-theory", "tier1"]`
2. Write `adapter.py`
3. Install `swecc-mesocosm`, test with Ollama:
   ```bash
   mesocosm run local --manifest benchanything.json --episodes 5
   ```
4. Write `LOCAL_DEV.md`

**Dependencies**: Phase 1 complete, `pip install swecc-mesocosm`, Ollama with llama3.2

### Phase 3: Model Comparison (4–6 hours)

**Objective**: Platform submit, multi-model comparison data

**Tasks**:
1. Push repo to GitHub
2. `mesocosm auth login`
3. `mesocosm env submit --name "Software Evolution" --github-url https://github.com/andersonniu08-boop/mesocosm_hackathon`
4. Wait for `status=ready`, note `domain_id`
5. Run 3+ models at 50 episodes each:
   ```bash
   mesocosm run create --domain <domain_id> --vow-version 1.0.0 --model gemini/gemini-2.5-flash --episodes 50 --visibility gallery_public
   mesocosm run create --domain <domain_id> --vow-version 1.0.0 --model gemini/gemini-2.5-pro --episodes 50 --visibility gallery_public
   mesocosm run create --domain <domain_id> --vow-version 1.0.0 --model anthropic/claude-sonnet-4-20250514 --episodes 50 --visibility gallery_public
   ```
6. Export and compare: `mesocosm run export <run_id> -o showcase/replay.json`
7. Verify score differentiation between models

**Dependencies**: Phase 2 complete, swecc.org account

### Phase 4: Polish (4–6 hours)

**Objective**: Refine based on real model behavior

**Tasks**:
1. Tune compression budget scaling based on observed model behavior
2. Fix edge cases discovered in real runs
3. Add more source programs to library
4. Expand test coverage
5. Add Pong as hard-tier fixture (import `fixtures/pong/source.py` into program library)
6. Optional: functional fidelity using `test_harness.py` (run reconstructed code against tests)

**Dependencies**: Phase 3 results

### Phase 5: Stretch Goals

| Goal | Value | Effort |
|---|---|---|
| Functional fidelity scoring via test_harness | Higher-signal reward than string similarity | 4h |
| Adjustable generation count (3/5/10) via scenario_params | Deeper evolution chains | 2h |
| Multi-tier difficulty (easy/medium/hard) | Nuanced model comparison | 3h |
| Detailed `render()` for trace output | Better demo material | 2h |
| Mutation injection (controlled noise) | Tests robustness | 4h |
| `requirements.txt` dep on `swecc-mesocosm` for sandbox mode | Full platform compatibility | 1h |

---

## Phase 7: Final Recommendation

### 1. Is Software Evolution a strong Mesocosm environment?

**Yes, with the redesign.** The alternating compress-reconstruct chain is genuinely novel in the Mesocosm ecosystem. Current environments test reasoning (arithmetic), strategy (game-playing), or knowledge (trivia). This tests **information theory in practice** — how well LLMs preserve semantic content through repeated lossy compression cycles.

The "Software Half-Life" metric (generations until fidelity < 0.50) produces memorable, quotable numbers. Different models will exhibit different compression/degradation profiles, creating a rich comparison surface.

### 2. What is the biggest technical risk?

**Model compliance with the alternating phase protocol.** The model must understand it's in a multi-phase episode: sometimes compressing, sometimes reconstructing. If a model produces a reconstruction during a compress step (or vice versa), rewards collapse.

**Mitigations**:
- Clear `phase` field in every observation
- Explicit instruction text in observation
- Structured output schema forces correct field (`genome` vs `reconstruction`)
- `parse_action()` ignores wrong field based on current phase
- First few steps of each episode naturally teach the pattern

**Secondary risk**: String edit distance may not correlate with functional correctness. Two syntactically different programs can be functionally identical. Mitigation: stretch goal adds functional testing via `test_harness.py` and `fixtures/pong/tests.json`.

### 3. What should be removed from the current design?

| Remove | Reason |
|---|---|
| `adapters/deepseek.py`, `adapters/claude.py`, `adapters/openai.py`, `adapters/base.py` | Platform does model inference |
| `environment.py` (custom orchestrator) | Replaced by `BaseEnv` subclass |
| `run.py` (CLI entry point) | `mesocosm run create` replaces this |
| `rank.py` (leaderboard) | Platform provides leaderboard |
| `reference.py` (GPT-4o reconstructor) | Model under test does reconstruction |
| `spec_validator.py` (with re-prompt) | Reward shaping handles validation |
| `prompts/summarizer.txt`, `prompts/reconstructor.txt` | Binding vow descriptions guide the agent |
| `environment_multi.py` | Tier 2 loop integrated into single `env.py` |
| `pong-game/` (GUI game with sounds) | Unused by benchmark |

### 4. What should be added?

| Add | Reason |
|---|---|
| `BaseEnv` subclass with `reset()` + `step()` | The only contract that matters |
| `benchanything.json` with valid `BindingVow` | Required for platform registration |
| `adapter.py` with `serve()` | Required HTTP endpoint |
| `parse_action()` routing method | Handles alternating compress/reconstruct phases |
| Source program library (`programs.py`) | Content for the env |
| Edit distance utility (`fidelity.py`) | Scoring logic |
| pytest smoke tests | Required for reliability |
| `LOCAL_DEV.md` | Required for hackathon onboarding |

### 5. What to build for the hackathon

**The 545-line MVP (Phases 1–3).** Timeline:

- **Hour 0–10**: `env.py`, `programs.py`, `fidelity.py`, tests. Local smoke test with `mesocosm run local`.
- **Hour 10–14**: `benchanything.json`, `adapter.py`. Submit to platform. Verify env shows as `ready`.
- **Hour 14–20**: Run 3+ models at 50 episodes each. Collect score data. Export replays.
- **Hour 20–48**: Polish. More programs. Tune budgets. Stretch goals. Write `LOCAL_DEV.md`.

The entire deliverable fits in **5 production files** (benchanything.json, env.py, adapter.py, programs.py, fidelity.py) plus tests and docs. Zero infrastructure. Zero frontend. Zero custom model code. Pure Mesocosm environment.

The key insight from arithmetic-env: **an excellent Mesocosm environment should feel trivial once you understand the pattern.** The arithmetic environment is 80 lines. Software Evolution should be ~120 lines. The complexity is in the idea, not the implementation.

---

## Appendix A: Mesocosm Contract Checklist

Before submitting, verify:

- [ ] `benchanything.json` at repo root with all required keys (`id`, `adapter`, `name`, `binding_vow`, `scoring`)
- [ ] `binding_vow.version` is valid SemVer (`1.0.0`)
- [ ] `binding_vow.episode.max_steps` set correctly
- [ ] `binding_vow.episode.deterministic_reset` is `true`
- [ ] `binding_vow.episode.supports_seed` is `true`
- [ ] `action_space.type` is `"json"` with valid `schema_ref`
- [ ] `reward.type` is `"scalar"` or `"binary"` with valid range
- [ ] `scoring.primary_metric` exists in `scoring.metrics` list
- [ ] `scoring.metrics[*].type` is `"episode_reward"` or `"terminal_field"`
- [ ] `adapter` path resolves to `adapter.py` in repo root
- [ ] `env.py` subclasses `BaseEnv` from `bench_common.env_sdk`
- [ ] `reset(seed)` returns JSON-serializable dict
- [ ] `step(action)` returns `StepResult` with all required fields
- [ ] All `info` values are strings
- [ ] Rewards are finite floats
- [ ] `reset(seed)` is deterministic (same seed = same initial obs)
- [ ] `step()` terminates correctly after max steps
- [ ] `adapter.py` uses `serve(EnvClass, ...)`
- [ ] `requirements.txt` exists (even if empty)
- [ ] Tested with `mesocosm run local` using Ollama
- [ ] Tested with at least one cloud model via platform

## Appendix B: Quick Reference — Env Author SDK

```python
from bench_common.env_sdk.base import BaseEnv, StepResult

class MyEnv(BaseEnv):
    def reset(self, seed=None, **params):
        """Return initial observation dict."""
        ...

    def step(self, action):
        """Return StepResult(observation, reward, terminated, truncated, info)."""
        ...

    def parse_action(self, action):
        """Optional: remap action before step()."""
        return action

    def close(self):
        """Optional: cleanup."""
        ...

    def render(self, mode="text"):
        """Optional: human-readable snapshot."""
        return {}
```

```python
# adapter.py
from bench_common.env_sdk import serve
from env import MyEnv

if __name__ == "__main__":
    serve(MyEnv, port=8765)
```

## Appendix C: Key Differences From Old Plan

| Aspect | Old Plan | New Plan |
|---|---|---|
| Architecture | Multi-model pipeline with internal model calls | Single-agent, multi-step Mesocosm env |
| Model calls | Env calls DeepSeek (summarizer) + GPT-4o (reconstructor) | Platform calls ONE model per step |
| Code organization | `environment.py` orchestrator + adapters + run.py + rank.py | `env.py` (BaseEnv subclass) + `adapter.py` |
| Episode structure | 1-step: model produces genome, env handles everything else | 6-step: model alternates compress/reconstruct |
| Scoring | Custom FF + BS computation | Platform `ScoringConfig` with `episode_reward` aggregation |
| Model support | Custom adapters per model | All models via platform's litellm integration |
| Delivery | Custom benchmark harness | `mesocosm env submit` → platform-registered domain |
