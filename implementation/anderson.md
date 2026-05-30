# Anderson — LLM Pipeline & Tier 2

## What you own

Every call to an LLM API in the entire project. You build the prompts, the model adapters, the summarizer pipeline, the reconstructor pipeline, and the Tier 2 multi-generation engine.

## Files you create

```
prompts/summarizer.txt
prompts/reconstructor.txt
adapters/base.py
adapters/deepseek.py
adapters/claude.py
adapters/openai.py
environment_multi.py
```

---

## Step 1 — prompts/summarizer.txt

Create a plain text file:

```
Analyze the following source code. Produce a JSON specification with these fields:

- purpose: What does this program do? (2-3 sentences)
- interfaces: How is the program invoked? List CLI arguments, expected input format, output format, exit codes.
- behavior: How does the program compute its output from its inputs? Be precise.
- constraints: What limits, invariants, and error conditions must the program enforce?
- dependencies: What libraries or modules does the program require?

Be precise. A different developer will rebuild the program from your specification alone.
They will not see the original source code. Your specification is all they have.

Return ONLY valid JSON. No explanation outside the JSON.
```

---

## Step 2 — prompts/reconstructor.txt

Create a plain text file:

```
You are rebuilding a program from a specification. You do not have access to
the original source code.

Write complete, runnable Python code that implements the specification.
If the specification is ambiguous or incomplete, fill in the gaps with your
best reasonable guess to produce a working program.

The program will be tested via command line. It must print JSON to stdout
and exit 0 on success, exit 1 on error.

Return ONLY the source code. No explanation. No markdown.
```

---

## Step 3 — adapters/base.py

```python
from abc import ABC, abstractmethod

class AbstractModel(ABC):
    def __init__(self, model_name: str, api_key: str):
        self.model_name = model_name
        self.api_key = api_key

    @abstractmethod
    def summarize(self, source_code: str, budget: int, temperature: float = 0.1) -> dict:
        """Call the model API. Return parsed JSON spec as a dict."""
        ...
```

That's it. 10 lines. The interface every adapter implements.

---

## Step 4 — adapters/deepseek.py

```python
import json
from openai import OpenAI
from adapters.base import AbstractModel

SUMMARIZER_PROMPT = open("prompts/summarizer.txt").read()

class DeepSeekModel(AbstractModel):
    def __init__(self, api_key: str):
        super().__init__("deepseek-chat", api_key)
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )

    def summarize(self, source_code: str, budget: int, temperature: float = 0.1) -> dict:
        response = self.client.chat.completions.create(
            model=self.model_name,
            temperature=temperature,
            messages=[
                {"role": "system", "content": SUMMARIZER_PROMPT},
                {"role": "user", "content": f"Token budget: {budget}\n\nSource code:\n{source_code}"}
            ]
        )
        content = response.choices[0].message.content.strip()
        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
            if content.endswith("```"):
                content = content[:-3]
        return json.loads(content)
```

~30 lines. The other two adapters are the same pattern with different clients.

---

## Step 5 — adapters/claude.py

Same pattern. Use the Anthropic SDK (`anthropic`). The API call looks like:

```python
import anthropic
client = anthropic.Anthropic(api_key=api_key)
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=4000,
    temperature=temperature,
    system=SUMMARIZER_PROMPT,
    messages=[{"role": "user", "content": f"Token budget: {budget}\n\nSource code:\n{source_code}"}]
)
return json.loads(response.content[0].text)
```

~30 lines.

---

## Step 6 — adapters/openai.py

Same pattern. Uses `openai.OpenAI` with no custom base_url. Model: `gpt-4o`. ~25 lines.

---

## Step 7 — environment_multi.py (Tier 2)

Create AFTER Tier 1 is fully working and you've seen the single-cycle pipeline run.

```python
import json, os, tempfile
from environment import SummarizationEnv  # Robin's class
from reference import reconstruct          # Robin's function
from test_harness import run_tests, score   # Tim's module


class MultiGenEnv(SummarizationEnv):
    """Wraps Tier 1 in a recursive loop. Reuses all Tier 1 components."""

    def run(self, generations: int = 50) -> dict:
        source_path = f"{self.fixture_dir}/source.py"
        code = open(source_path).read()
        tests = json.load(open(f"{self.fixture_dir}/tests.json"))
        budget = 500
        temp = 0.1
        trajectory = []

        for gen in range(generations):
            # 1. Summarize current code
            spec = self.model.summarize(code, int(budget), temperature=temp)

            # 2. Reconstruct from spec
            new_code = reconstruct(spec)

            # 3. Test the rebuild
            ff, bs = self._test_code(new_code, tests)

            # 4. Record
            trajectory.append({
                "gen": gen, "ff": round(ff, 4), "bs": round(bs, 4),
                "budget": int(budget), "temp": round(temp, 2),
                "collapsed": ff == 0
            })

            # 5. Update for next generation
            code = new_code
            budget *= 0.95
            temp = self._temp_schedule(gen)

            # 6. Check collapse recovery
            if ff == 0:
                code = open(source_path).read()  # fall back to original
                budget = 500  # reset budget

        half_life = self._compute_half_life(trajectory)
        return {"half_life": half_life, "trajectory": trajectory}

    def _test_code(self, code: str, tests: list) -> tuple[float, float]:
        """Write code to temp file and run tests against it."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            tmp_path = f.name
        try:
            results = run_tests(tmp_path, tests)
            return score(tests, results)
        finally:
            os.unlink(tmp_path)

    def _compute_half_life(self, trajectory: list) -> int:
        """First generation where 5-gen rolling average FF drops below 0.5."""
        for i in range(len(trajectory) - 4):
            window = trajectory[i:i+5]
            avg = sum(g["ff"] for g in window) / 5
            if avg < 0.5:
                return i + 2  # center of the 5-gen window
        return len(trajectory)  # never dropped below 0.5

    def _temp_schedule(self, gen: int) -> float:
        if gen < 4:   return 0.1
        if gen < 16:  return 0.3
        if gen < 36:  return 0.5
        return 0.7
```

~100 lines. Reuses Robin's `SummarizationEnv.__init__`, Robin's `reconstruct()`, Tim's `run_tests()` and `score()`. You subclass and add the loop.

---

## How to verify your work (before Tim and Robin deliver)

Create a test script:

```python
import json, os
from adapters.deepseek import DeepSeekModel

api_key = os.environ["DEEPSEEK_API_KEY"]
model = DeepSeekModel(api_key)

# Test: can you summarize a Python file?
dummy_code = """
import sys, json
def add(a, b):
    return a + b
if __name__ == "__main__":
    x = int(sys.argv[1])
    y = int(sys.argv[2])
    print(json.dumps({"result": add(x, y)}))
"""

spec = model.summarize(dummy_code, budget=500)
print(json.dumps(spec, indent=2))
# Should be valid JSON with keys: purpose, interfaces, behavior, constraints, dependencies
```

Then test with a real Pong (Tim will give you `fixtures/pong/source.py`):

```python
pong_code = open("fixtures/pong/source.py").read()
spec = model.summarize(pong_code, budget=500)
print(spec["purpose"])  # Should describe Pong
print(len(spec["interfaces"]))  # Should be ≥ 1
print(spec["dependencies"])  # Should list what Pong imports
```

Then verify the reconstructor works (uses GPT-4o — talk to Robin about the API key setup):

```python
from reference import reconstruct
code = reconstruct(spec)
print(code[:200])  # Should look like Python code
compile(code, "<test>", "exec")  # Should not raise SyntaxError
```

---

## What Tim needs from you

Nothing. You consume his `test_harness.py` and `tests.json`.

## What Robin needs from you

- `AbstractModel` base class (he imports it for type hints)
- Working model adapters (he passes them to `SummarizationEnv`)
- Confirmation that `model.summarize(source_code, budget, temperature)` returns a dict

The exact interface Robin depends on is:

```python
model.summarize(source_code: str, budget: int, temperature: float = 0.1) -> dict
```
