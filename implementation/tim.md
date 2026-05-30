# Tim — Fixture, Test Harness & Scoring

## What you own

The ground truth. You build the Pong game, the test scenarios that define "correct behavior," and the harness that scores any program against those scenarios.

## Files you create

```
fixtures/pong/source.py
fixtures/pong/tests.json
test_harness.py
```

---

## Step 1 — fixtures/pong/source.py

Write a **headless, deterministic Pong game**. It runs one frame per CLI invocation, prints the resulting game state as JSON to stdout, and exits.

### Rules

- **No GUI.** No pygame. Pure Python math.
- **Deterministic.** Same args always give identical output. No random. No `time.time()`.
- **One frame.** The program computes one frame and exits. It does not loop.

### CLI interface

```
python pong.py \
  --ball-x 100 --ball-y 200 --ball-dx 5 --ball-dy 0 \
  --paddle-left 250 --paddle-right 300 \
  --score-left 0 --score-right 0 \
  --frames 1
```

### What it does

1. Parse CLI args. If any arg missing or non-numeric → exit 1.
2. Apply ball velocity for N frames: `ball_x += ball_dx * frames`, `ball_y += ball_dy * frames`
3. Check wall collision (top/bottom): if ball touches or crosses field boundary, flip `ball_dy` and clamp position
4. Check paddle collision: if ball reaches paddle X and ball Y is within paddle range (± paddle_length/2), flip `ball_dx`
5. Check scoring: if ball passes left edge past paddle → right scores. Ball resets to center. Same for right edge.
6. Print resulting state as JSON to stdout. Exit 0.

### Constants

```python
FIELD_WIDTH = 600
FIELD_HEIGHT = 400
PADDLE_LENGTH = 60
PADDLE_LEFT_X = 20
PADDLE_RIGHT_X = 580
BALL_SIZE = 6
```

Ball radius is 3px (BALL_SIZE/2). Paddles are vertical bars at x=20 and x=580. Field boundaries are 0 to FIELD_WIDTH, 0 to FIELD_HEIGHT.

### Implementation

One function: `step(state: dict) -> dict`. Takes all state, returns new state. `main()` parses args into a dict, calls `step()`, prints JSON.

~150 lines. Keep it dead simple.

---

## Step 2 — fixtures/pong/tests.json

20 test scenarios. A JSON array of objects.

### Format

```json
{
  "id": "ball_move_01",
  "category": "ball_movement",
  "args": [
    "--ball-x", "100", "--ball-y", "200",
    "--ball-dx", "5", "--ball-dy", "0",
    "--paddle-left", "250", "--paddle-right", "300",
    "--score-left", "0", "--score-right", "0",
    "--frames", "1"
  ],
  "expected": {
    "exit_code": 0,
    "stdout_keys": {
      "ball_x": 105, "ball_y": 200,
      "ball_dx": 5, "ball_dy": 0,
      "score_left": 0, "score_right": 0
    }
  }
}
```

**Rules:**
- `args` is a flat list (what `subprocess.run()` takes)
- `stdout_keys` lists only the fields to check. Extra fields in the output are fine and ignored.
- For invalid-input tests: `"exit_code": 1`, no `stdout_keys` needed (or empty object)

### 20 scenarios across 6 categories (3-4 each)

| Category | Scenarios | What to test |
|----------|-----------|-------------|
| **Ball movement** | 4 | Ball moves right. Moves up. Moves diagonally. Moves multiple frames (--frames 3). |
| **Wall bounce** | 3 | Ball hits top wall (dy flips positive). Ball hits bottom wall (dy flips negative). Ball near wall but not touching (no bounce). |
| **Paddle hit** | 4 | Ball hits left paddle center (dx flips). Hits right paddle at edge. Misses paddle by 1 pixel above. Misses paddle by 1 pixel below. |
| **Scoring** | 3 | Ball passes left edge past paddle (right scores +1, ball resets). Ball passes right edge past paddle (left scores +1). Ball at edge but paddle blocks it (no score). |
| **Edge cases** | 3 | Zero velocity (ball doesn't move). Paddle at field boundary. Ball exactly at corner. |
| **Invalid input** | 3 | Missing required arg. Non-numeric arg. Out-of-range value (ball_x = 9999). |

### How to generate them

Write a small script that calls your own `source.py` with different args and captures stdout. Don't hand-calculate expected values — use the original Pong as the oracle. The test scenarios ARE the recorded behavior of the original.

---

## Step 3 — test_harness.py

Two functions. No classes.

### `run_tests(program_path: str, tests: list) -> list`

For each test scenario:
- Call `subprocess.run(["python", program_path] + test["args"], capture_output=True, text=True, timeout=5)`
- If timeout → test failed
- If exit code ≠ expected → test failed
- Try to `json.loads(stdout)`. If parse fails → test failed
- Compare each key in `stdout_keys` against actual output. If any mismatch → test failed
- Return a result dict per test: `{"test_id": ..., "passed": bool, "actual_stdout": str, "expected_stdout": str}`

### `score(tests: list, results: list) -> tuple[float, float]`

```python
ff = passed_count / total_count

bs_sum = 0
for r in results:
    if r["passed"]:
        a = r["actual_stdout"]
        e = r["expected_stdout"]
        dist = levenshtein_distance(a, e)  # see below
        bs_sum += 1 - (dist / max(len(a), len(e)))
    # failed tests contribute 0 to BS average
bs = bs_sum / len(results) if results else 0

return (ff, bs)
```

For edit distance: you can pip install `python-Levenshtein` for speed, or write a simple Levenshtein function in 10 lines. Both are fine.

That's it. ~80 lines.

---

## How to verify your work

```python
import json
from test_harness import run_tests, score

tests = json.load(open("fixtures/pong/tests.json"))
results = run_tests("fixtures/pong/source.py", tests)
ff, bs = score(tests, results)
print(f"FF={ff:.2f} BS={bs:.2f}")
# Should print: FF=1.00 BS=1.00
```

If you don't get 1.00, your test scenarios don't match your Pong behavior. Fix either the tests or the game. Both coming from you, so make them match.

---

## What Anderson needs from you

- `test_harness.py` with `run_tests(path, tests)` and `score(tests, results)` as described
- `fixtures/pong/tests.json` in the format described

## What Robin needs from you

- Same as Anderson
- A quick explanation if anything unexpected about the test format
