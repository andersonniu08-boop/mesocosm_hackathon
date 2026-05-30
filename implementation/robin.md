# Robin — Orchestration, Validation, CLI, Mesocosm & Demo

## What you own

Everything that glues Tim's testing and Anderson's LLMs into a shippable Mesocosm benchmark. You also own the spec validator, the reference reconstructor wrapper, and all output/deployment code.

## Files you create

```
spec_validator.py
reference.py
environment.py
run.py
rank.py
benchanything.json
demo/index.html           (optional, if time)
```

---

## Step 1 — spec_validator.py

One function. No classes.

```python
import json

REQUIRED_FIELDS = ["purpose", "interfaces", "behavior", "constraints", "dependencies"]
PLACEHOLDERS = ["TBD", "TODO", "N/A", "todo", "tbd", "n/a", "..."]

def validate_spec(spec_str: str, budget: int) -> tuple[bool, str, dict | None]:
    """
    Validate a model's JSON spec output.
    Returns (is_valid, error_message, parsed_spec_or_None).
    """
    # 1. Parse JSON
    try:
        spec = json.loads(spec_str)
    except json.JSONDecodeError as e:
        return (False, f"Invalid JSON: {e}", None)

    # 2. Check required fields
    missing = [f for f in REQUIRED_FIELDS if f not in spec]
    if missing:
        return (False, f"Missing fields: {missing}", None)

    # 3. Check non-empty
    for field in REQUIRED_FIELDS:
        value = spec[field]
        if value is None:
            return (False, f"Field '{field}' is null", None)
        if isinstance(value, str) and value.strip() == "":
            return (False, f"Field '{field}' is empty", None)
        if isinstance(value, str) and value.strip() in PLACEHOLDERS:
            return (False, f"Field '{field}' is a placeholder: '{value}'", None)
        if isinstance(value, (list, dict)) and len(value) == 0:
            return (False, f"Field '{field}' is empty list/object", None)

    # 4. Check token count
    token_count = len(spec_str.split())
    if token_count > budget + 20:
        return (False, f"Over budget: {token_count} tokens (limit: {budget})", None)

    return (True, "", spec)
```

~50 lines.

---

## Step 2 — reference.py

One function. Calls GPT-4o to rebuild code from a spec.

```python
import os, json
from openai import OpenAI

RECONSTRUCTOR_PROMPT = open("prompts/reconstructor.txt").read()
_client = None

def _get_client():
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    return _client

def reconstruct(spec: dict) -> str:
    """
    Call GPT-4o to rebuild a program from a specification.
    Returns the generated source code as a string.
    """
    client = _get_client()
    response = client.chat.completions.create(
        model="gpt-4o",
        temperature=0,
        messages=[
            {"role": "system", "content": RECONSTRUCTOR_PROMPT},
            {"role": "user", "content": json.dumps(spec, indent=2)}
        ]
    )
    code = response.choices[0].message.content.strip()

    # Strip markdown code fences
    if code.startswith("```"):
        lines = code.split("\n")
        lines = lines[1:]  # remove opening ```
        if lines[-1].strip() == "```":
            lines = lines[:-1]  # remove closing ```
        code = "\n".join(lines)

    return code
```

~40 lines.

---

## Step 3 — environment.py

The main orchestrator. Wires everything together.

```python
import json, os, tempfile
from adapters.base import AbstractModel
from spec_validator import validate_spec
from reference import reconstruct
from test_harness import run_tests, score

BUDGETS = {0: 99999, 1: 500, 2: 300, 3: 150}

class SummarizationEnv:
    def __init__(self, fixture_dir: str, model: AbstractModel, heat_level: int = 1):
        self.fixture_dir = fixture_dir
        self.model = model
        self.heat_level = heat_level
        self.budget = BUDGETS.get(heat_level, 500)

    def run(self) -> dict:
        # Load fixture
        source_path = f"{self.fixture_dir}/source.py"
        tests_path = f"{self.fixture_dir}/tests.json"
        source_code = open(source_path).read()
        tests = json.load(open(tests_path))

        # Summarize (up to 2 attempts)
        spec = None
        for attempt in range(2):
            raw = self._call_summarize(source_code)
            valid, err, parsed = validate_spec(raw, self.budget)
            if valid:
                spec = parsed
                break
            if attempt == 1:
                return self._failed_result("invalid_spec", err, tests)

        # Reconstruct
        code = reconstruct(spec)

        # Build check
        if not self._parses(code):
            return self._failed_result("build_failed", "Code does not compile", tests)

        # Test
        ff, bs = self._test_code(code, tests)

        return {
            "functional_fidelity": round(ff, 4),
            "behavioral_similarity": round(bs, 4),
            "tests_passed": int(ff * len(tests)),
            "tests_total": len(tests),
            "build_succeeded": True,
            "spec_token_count": len(json.dumps(spec).split()),
            "spec_is_valid": True,
            "heat_level": self.heat_level,
            "model": self.model.model_name,
            "fixture": os.path.basename(self.fixture_dir)
        }

    def _call_summarize(self, source_code: str) -> str:
        result = self.model.summarize(source_code, self.budget)
        return json.dumps(result) if isinstance(result, dict) else str(result)

    def _parses(self, code: str) -> bool:
        try:
            compile(code, "<reconstructed>", "exec")
            return True
        except SyntaxError:
            return False

    def _test_code(self, code: str, tests: list) -> tuple[float, float]:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            tmp_path = f.name
        try:
            results = run_tests(tmp_path, tests)
            return score(tests, results)
        finally:
            os.unlink(tmp_path)

    def _failed_result(self, reason: str, detail: str, tests: list) -> dict:
        return {
            "functional_fidelity": 0.0,
            "behavioral_similarity": 0.0,
            "tests_passed": 0,
            "tests_total": len(tests),
            "build_succeeded": False,
            "error": reason,
            "error_detail": detail,
            "heat_level": self.heat_level,
            "model": self.model.model_name,
            "fixture": os.path.basename(self.fixture_dir)
        }
```

~120 lines.

---

## Step 4 — run.py

CLI entry point.

```python
#!/usr/bin/env python3
import argparse, json, os
from environment import SummarizationEnv
from adapters.deepseek import DeepSeekModel
from adapters.claude import ClaudeModel
from adapters.openai import OpenAIModel

FACTORY = {
    "deepseek": lambda: DeepSeekModel(os.environ["DEEPSEEK_API_KEY"]),
    "claude":    lambda: ClaudeModel(os.environ["ANTHROPIC_API_KEY"]),
    "openai":    lambda: OpenAIModel(os.environ["OPENAI_API_KEY"]),
}

def main():
    p = argparse.ArgumentParser(description="Software Evolution Benchmark")
    p.add_argument("--model", required=True, choices=list(FACTORY.keys()))
    p.add_argument("--heat", type=int, default=1, choices=[0, 1, 2, 3])
    p.add_argument("--fixture", default="fixtures/pong")
    p.add_argument("--output-dir", default="results")
    args = p.parse_args()

    model = FACTORY[args.model]()
    env = SummarizationEnv(args.fixture, model, args.heat)
    result = env.run()

    os.makedirs(args.output_dir, exist_ok=True)
    out_path = f"{args.output_dir}/{args.model}_heat{args.heat}.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"Model:  {args.model}")
    print(f"Heat:   {args.heat}")
    print(f"FF:     {result['functional_fidelity']:.2f}")
    print(f"BS:     {result['behavioral_similarity']:.2f}")
    print(f"Output: {out_path}")

if __name__ == "__main__":
    main()
```

~40 lines.

---

## Step 5 — rank.py

Leaderboard printer.

```python
#!/usr/bin/env python3
import json, glob, sys

def main():
    results_dir = sys.argv[1] if len(sys.argv) > 1 else "results"
    results = []
    for path in glob.glob(f"{results_dir}/*.json"):
        data = json.load(open(path))
        results.append(data)

    if not results:
        print("No results found.")
        return

    # Sort by FF desc, BS desc
    results.sort(key=lambda r: (-r.get("functional_fidelity", 0),
                                -r.get("behavioral_similarity", 0)))

    print(f"{'Rank':<6}{'Model':<12}{'FF':<8}{'BS':<8}{'Passed':<10}{'Heat':<6}")
    print("-" * 50)
    for i, r in enumerate(results, 1):
        ff = r.get("functional_fidelity", 0)
        bs = r.get("behavioral_similarity", 0)
        passed = r.get("tests_passed", 0)
        total = r.get("tests_total", 0)
        heat = r.get("heat_level", "?")
        model = r.get("model", "?")
        print(f"{i:<6}{model:<12}{ff:<8.2f}{bs:<8.2f}{passed}/{total:<8}{heat:<6}")

if __name__ == "__main__":
    main()
```

~30 lines.

---

## Step 6 — benchanything.json

Mesocosm registration.

```json
{
    "name": "software-evolution",
    "version": "1.0.0",
    "type": "benchmark",
    "track": "agi-real-world-modeling",
    "description": "Measures a model's ability to produce a specification from source code such that a different model can rebuild working software from the spec alone.",
    "primary_metric": "functional_fidelity",
    "secondary_metric": "behavioral_similarity",
    "extended_metrics": ["software_half_life"],
    "heat_levels": [
        {"level": 0, "description": "No token budget", "tier": 1},
        {"level": 1, "description": "500 token budget", "tier": 1},
        {"level": 2, "description": "300 token budget", "tier": 1},
        {"level": 3, "description": "150 token budget", "tier": 1},
        {"level": 4, "description": "Multi-gen: 5% budget shrink/generation", "tier": 2},
        {"level": 5, "description": "Multi-gen: 8% budget shrink/generation", "tier": 2},
        {"level": 6, "description": "Multi-gen: 10% budget shrink/generation", "tier": 2}
    ],
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

---

## Step 7 — demo/index.html (OPTIONAL, hours 18+)

A single static HTML page. No frameworks. No build step.

What it shows:
- Run selector (pick a result JSON file)
- Side-by-side: spec content and scores
- Leaderboard table (loads all result JSONs from `results/` directory)
- If Tier 2 results exist: trajectory graph (simple canvas line chart of FF over generations)

Serve with `python -m http.server 8000` from the project root.

Build this ONLY after Tier 1 is solid and results are pre-computed.

---

## How to verify your work BEFORE Tim and Anderson deliver

Create stub files to test `environment.py` in isolation. Put these in a `stubs/` directory (delete them after integration):

```python
# stubs/test_harness.py
def run_tests(path, tests):
    return [{"test_id": t["id"], "passed": True,
             "actual_stdout": "{}", "expected_stdout": "{}"}
            for t in tests]
def score(tests, results):
    return (1.0, 1.0)

# stubs/reference.py
def reconstruct(spec):
    # Return a valid Python program matching the Pong interface
    return '''
import sys, json, argparse
parser = argparse.ArgumentParser()
parser.add_argument("--ball-x", type=int)
parser.add_argument("--ball-y", type=int)
parser.add_argument("--ball-dx", type=int)
parser.add_argument("--ball-dy", type=int)
parser.add_argument("--paddle-left", type=int)
parser.add_argument("--paddle-right", type=int)
parser.add_argument("--score-left", type=int)
parser.add_argument("--score-right", type=int)
parser.add_argument("--frames", type=int)
args = parser.parse_args()
print(json.dumps({"ball_x": args.ball_x, "ball_y": args.ball_y}))
'''
```

Then test your environment:

```python
import sys
sys.path.insert(0, "stubs")  # override real modules with stubs

from environment import SummarizationEnv

class StubModel:
    model_name = "stub"
    def summarize(self, code, budget):
        return {"purpose": "A game", "interfaces": [{}],
                "behavior": "Moves ball", "constraints": "None",
                "dependencies": ["json", "argparse"]}

env = SummarizationEnv("fixtures/pong", StubModel(), heat=1)
result = env.run()
print(result["functional_fidelity"])  # Should be 1.0 with stubs
```

Once Tim ships `test_harness.py` and Anderson ships model adapters, remove the `stubs/` directory and everything works with real components.

---

## What Tim needs from you

Nothing. You consume his `test_harness.py` and `tests.json`.

## What Anderson needs from you

- `reference.py` — the `reconstruct(spec) -> str` function (he calls it in Tier 2)
- `spec_validator.py` — the `validate_spec(spec_str, budget) -> (bool, str, dict)` function
- API key management strategy (env vars? config file?)
