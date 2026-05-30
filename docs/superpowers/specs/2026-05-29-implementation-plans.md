# Implementation Plans

## TIM — Fixture, Harness & Scoring

### Files you create

```
fixtures/pong/source.py
fixtures/pong/tests.json
test_harness.py
```

### Step 1: fixtures/pong/source.py

Write a headless Pong game. Key rules:

- **CLI args only.** No GUI. No pygame import unless you use it for math (but better to avoid it entirely — pure Python math). All state comes from CLI flags.
- **Deterministic.** Same args always give same output. No random. No time-based physics.
- **One frame per invocation.** The whole program runs one frame and exits. It doesn't loop.

**The CLI interface:**

```
python pong.py \
  --ball-x 100 --ball-y 200 --ball-dx 5 --ball-dy 0 \
  --paddle-left 250 --paddle-right 300 \
  --score-left 0 --score-right 0 \
  --frames 1
```

**What it computes:**

1. Move the ball: `ball_x += ball_dx`, `ball_y += ball_dy`
2. Wall bounce: if `ball_y <= 0` or `ball_y >= FIELD_HEIGHT`, flip `ball_dy`
3. Paddle hit: if ball reaches paddle x-position AND ball_y is within paddle range (paddle ± PADDLE_LENGTH/2), flip `ball_dx`
4. Scoring: if ball passes left edge past paddle, right scores +1 and ball resets to center. Same for right edge.
5. Print resulting state as JSON to stdout, exit 0.
6. If any arg is missing or invalid (non-numeric, out of range), print nothing to stdout and exit 1.

**Constants to define:**

```python
FIELD_WIDTH = 600
FIELD_HEIGHT = 400
PADDLE_WIDTH = 10
PADDLE_LENGTH = 60
BALL_SIZE = 6
PADDLE_LEFT_X = 20
PADDLE_RIGHT_X = 580
```

**Keep it simple.** ~150-200 lines. One function: `step(state) → new_state`. The `main()` parses args, calls `step()`, prints JSON.

### Step 2: fixtures/pong/tests.json

20 test scenarios. Array of objects. Each object:

```json
{
  "id": "ball_move_01",
  "category": "ball_movement",
  "args": ["--ball-x", "100", "--ball-y", "200", "--ball-dx", "5", "--ball-dy", "0",
            "--paddle-left", "250", "--paddle-right", "300",
            "--score-left", "0", "--score-right", "0", "--frames", "1"],
  "expected": {
    "exit_code": 0,
    "stdout_keys": {"ball_x": 105, "ball_y": 200, "ball_dx": 5, "ball_dy": 0,
                    "score_left": 0, "score_right": 0}
  }
}
```

`args` is a list because that's what subprocess.run() takes. `stdout_keys` is a dict of field:expected_value — the harness checks only these fields, not the whole JSON. Fields not in `stdout_keys` are ignored (lets the output include extra fields without breaking tests).

**20 scenarios across 6 categories (3-4 each):**

| Category | Scenarios |
|----------|-----------|
| Ball movement | Move right, move left, move diagonal, move at boundary |
| Wall bounce | Hit top wall, hit bottom wall, approach wall but don't touch |
| Paddle hit | Left paddle hit, right paddle hit, miss paddle by 1 pixel, hit paddle edge |
| Scoring | Left scores, right scores, ball at edge (no score yet) |
| Edge case | Zero velocity, max speed, paddle at extreme top/bottom, ball exactly on paddle edge |
| Invalid input | Missing arg, non-numeric arg, negative ball-x, out-of-range paddle |

For each scenario: write a Python script that calls Pong with those args, captures the output, and puts it in the JSON. Don't compute these by hand — use your own Pong as the oracle.

### Step 3: test_harness.py

Two functions:

```python
def run_tests(program_path: str, tests: list[dict]) -> list[dict]:
    """Run all test scenarios against a program. Returns list of test results."""

def score(tests: list[dict], results: list[dict]) -> tuple[float, float]:
    """Compute FF and BS from test results. Returns (functional_fidelity, behavioral_similarity)."""
```

**`run_tests(program_path, tests)`:**
- For each test scenario:
  - Call `python <program_path> <args>` via `subprocess.run()` with 5s timeout
  - Capture stdout, stderr, exit code
  - Parse stdout as JSON (handle parse failure — that's a test failure)
  - Compare exit code and stdout_keys against expected
  - Store pass/fail + actual output
- Return list of result dicts

**`score(tests, results)`:**
- FF = number of passed tests / total tests
- BS = for tests that passed, compute edit distance between actual stdout and expected stdout_keys rendered as JSON. BS = mean of (1 - edit_distance / max_len). For tests that failed, BS contribution = 0.
- Return (FF, BS) as floats

That's it. Three files. ~300 total lines of Python.

### How to verify your work

```python
from test_harness import run_tests, score

tests = json.load(open("fixtures/pong/tests.json"))
results = run_tests("fixtures/pong/source.py", tests)
ff, bs = score(tests, results)
print(f"FF={ff:.2f} BS={bs:.2f}")  # Should be FF=1.00 BS=1.00 on the original
```

---

## ANDERSON — LLM Pipeline

### Files you create

```
prompts/summarizer.txt
prompts/reconstructor.txt
adapters/base.py
adapters/deepseek.py
adapters/claude.py
adapters/openai.py
spec_validator.py
reference.py
```

### Step 1: prompts/summarizer.txt

A plain text file. The exact prompt from the design doc.

### Step 2: prompts/reconstructor.txt

A plain text file. The exact prompt from the design doc.

### Step 3: adapters/base.py

```python
from abc import ABC, abstractmethod

class AbstractModel(ABC):
    def __init__(self, model_name: str, api_key: str):
        self.model_name = model_name
        self.api_key = api_key

    @abstractmethod
    def summarize(self, source_code: str, budget: int) -> dict:
        """Call the model's API. Return parsed JSON spec as a dict."""
        ...
```

### Step 4: adapters/deepseek.py

- Inherits AbstractModel
- Calls DeepSeek API (openai-compatible endpoint)
- Takes source_code and budget
- Loads summarizer.txt prompt
- Constructs messages: system=prompt, user=f"Token budget: {budget}\n\nSource code:\n{source_code}"
- Returns `json.loads(response.choices[0].message.content)`
- Temperature = 0.1
- ~25 lines

### Step 5: adapters/claude.py

Same pattern. Uses Anthropic SDK or requests. ~25 lines.

### Step 6: adapters/openai.py

Same pattern. Uses OpenAI SDK. ~25 lines.

### Step 7: spec_validator.py

One function:

```python
def validate_spec(spec_str: str, budget: int) -> tuple[bool, str]:
    """Returns (is_valid, error_message)."""
```

Checks:
1. Parse as JSON. If not valid JSON, return (False, "invalid JSON")
2. All required fields present: purpose, interfaces, behavior, constraints, dependencies
3. No field is empty string or missing
4. No field contains only whitespace or placeholder text like "TBD", "TODO", "N/A" alone
5. Token count ≤ budget + 20 (allow small overage). Count tokens by splitting on whitespace (crude but adequate for a hackathon).

### Step 8: reference.py

One function:

```python
def reconstruct(spec: dict) -> str:
    """Calls GPT-4o with the reconstructor prompt + spec. Returns source code string."""
```

- Uses OpenAI client (same pattern as adapters)
- Loads reconstructor.txt
- Message: system=prompt, user=json.dumps(spec)
- Temperature = 0 (deterministic)
- Returns the content string directly (not JSON — the reconstructor returns raw code)
- Strip markdown code fences if present (```python ... ``` → just the code)

### How to verify your work

```python
from adapters.deepseek import DeepSeekModel
from reference import reconstruct
from spec_validator import validate_spec

model = DeepSeekModel("deepseek-chat", api_key)

# Test summarization
spec = model.summarize(open("fixtures/pong/source.py").read(), budget=500)
print(spec.keys())  # Should be: purpose, interfaces, behavior, constraints, dependencies

# Test validation
valid, err = validate_spec(json.dumps(spec), budget=500)
print(valid)  # Should be True

# Test reconstruction
code = reconstruct(spec)
print("import" in code)  # Should be True
print(compile(code, "<test>", "exec"))  # Should not crash
```

---

## ROBIN — Orchestration, CLI, Mesocosm, Tier 2

### Files you create

```
environment.py
run.py
rank.py
benchanything.json
environment_multi.py   (after Tier 1 works)
demo/index.html        (optional)
```

### Step 1: environment.py

```python
class SummarizationEnv:
    def __init__(self, fixture_dir: str, model: AbstractModel,
                 heat_level: int = 1):
        self.fixture_dir = fixture_dir
        self.model = model
        self.heat_level = heat_level
        self.budget = self._budget_for_heat(heat_level)

    def run(self) -> dict:
        """Run one evaluation cycle. Returns result dict."""
        # 1. Load source code from fixture_dir/source.py
        # 2. Call model.summarize(source_code, budget)
        # 3. Validate spec via spec_validator.validate_spec()
        #    - If invalid, re-prompt once
        #    - If still invalid, return {"ff": 0, "bs": 0, "error": "invalid_spec"}
        # 4. Call reference.reconstruct(spec)
        # 5. Write reconstructed code to temp file
        # 6. Check if code parses (compile()) — if not, return score=0
        # 7. Call test_harness.run_tests(temp_file, tests)
        # 8. Call test_harness.score(tests, results)
        # 9. Return {ff, bs, tests_passed, tests_total, ...}

    def _budget_for_heat(self, heat: int) -> int:
        return {0: 99999, 1: 500, 2: 300, 3: 150}[heat]
```

~100 lines. Glues together Tim's harness + Anderson's models.

### Step 2: run.py

```python
"""CLI entry point."""
import argparse, json, os
from environment import SummarizationEnv
from adapters.deepseek import DeepSeekModel
from adapters.claude import ClaudeModel
from adapters.openai import OpenAIModel

MODELS = {"deepseek": DeepSeekModel, "claude": ClaudeModel, "openai": OpenAIModel}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--heat", type=int, default=1)
    parser.add_argument("--fixture", default="fixtures/pong")
    parser.add_argument("--output", default="results")
    args = parser.parse_args()

    model = MODELS[args.model](api_key=os.environ[f"{args.model.upper()}_API_KEY"])
    env = SummarizationEnv(args.fixture, model, args.heat)
    result = env.run()

    os.makedirs(args.output, exist_ok=True)
    path = f"{args.output}/{args.model}_heat{args.heat}.json"
    json.dump(result, open(path, "w"), indent=2)
    print(f"FF={result['ff']:.2f} BS={result['bs']:.2f}")

if __name__ == "__main__":
    main()
```

~30 lines.

### Step 3: rank.py

Reads all JSON files in `results/`. Sorts by FF desc, BS desc for ties. Prints a formatted table.

~20 lines.

### Step 4: benchanything.json

The registration JSON from the design doc. ~25 lines.

### Step 5 (after integration): environment_multi.py

```python
from environment import SummarizationEnv

class MultiGenEnv(SummarizationEnv):
    def run(self, generations: int = 50) -> dict:
        """Run multi-generation evolution."""
        code = open(f"{self.fixture_dir}/source.py").read()
        budget = 500
        results = []

        for gen in range(generations):
            spec = self.model.summarize(code, budget)
            code = reference.reconstruct(spec)
            ff, bs = self._test_code(code)
            results.append({"gen": gen, "ff": ff, "bs": bs, "budget": budget})
            budget = int(budget * 0.95)

        hl = self._half_life(results)
        return {"half_life": hl, "trajectory": results}

    def _half_life(self, results):
        for i in range(len(results) - 4):
            avg = sum(r["ff"] for r in results[i:i+5]) / 5
            if avg < 0.5:
                return i + 2  # center of the 5-gen window
        return len(results)
```

~80 lines.

### Step 6 (optional): demo/index.html

Static HTML page. Loads results JSON files via fetch. Renders:
- Spec → Rebuild comparison (side-by-side code blocks)
- FF/BS score display
- Leaderboard table (if multiple results)
- Trajectory graph (if multi-gen results exist)

Single file. No build step. ~100 lines.

### How to verify your work EARLY (before Tim and Anderson deliver)

Create stub versions of their interfaces:

```python
# stub_harness.py
def run_tests(path, tests): return [{"passed": True}] * len(tests)
def score(tests, results): return (1.0, 1.0)

# stub_model.py  
class StubModel:
    def summarize(self, code, budget):
        return {"purpose": "A game", "interfaces": [], "behavior": "...",
                "constraints": "...", "dependencies": []}

# stub_reference.py
def reconstruct(spec): return "print('hello')"
```

Wire your environment.py to these stubs. Verify the flow: env.run() → calls summarize → calls validate → calls reconstruct → calls test → returns result dict. Once Tim and Anderson ship, swap stubs for real modules. Your code doesn't change — just the imports.

---

## Integration order

1. Tim finishes first (Pong). Anderson tests his pipeline against real Pong source.
2. Anderson finishes second (adapters). Robin swaps stubs for real imports.
3. Robin wires everything. Full end-to-end run with one model.
4. All three debug together (prompts, tests, edge cases).
5. Once one model works, Robin runs the other two. Leaderboard populates.
6. If time: Robin ships Tier 2. Tim writes more test scenarios. Anderson refines prompts.
