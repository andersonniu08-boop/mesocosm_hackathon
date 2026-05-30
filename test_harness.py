import json
import subprocess
import sys


def levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        return levenshtein(b, a)
    if len(b) == 0:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            cost = 0 if ca == cb else 1
            curr.append(min(curr[j] + 1, prev[j + 1] + 1, prev[j] + cost))
        prev = curr
    return prev[-1]


def run_tests(program_path: str, tests: list[dict]) -> list[dict]:
    results = []
    for t in tests:
        cmd = [sys.executable, program_path] + t["args"]
        expected = t["expected"]
        expected_code = expected["exit_code"]
        expected_keys = expected.get("stdout_keys", {})

        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=5
            )
        except subprocess.TimeoutExpired:
            results.append({
                "test_id": t["id"],
                "category": t["category"],
                "passed": False,
                "error": "timeout",
                "actual_stdout": "",
                "expected_stdout": json.dumps(expected_keys),
            })
            continue

        actual_code = proc.returncode
        actual_stdout_raw = proc.stdout.strip()

        if actual_code != expected_code:
            results.append({
                "test_id": t["id"],
                "category": t["category"],
                "passed": False,
                "error": "exit_code_mismatch",
                "actual_stdout": actual_stdout_raw,
                "expected_stdout": json.dumps(expected_keys),
            })
            continue

        if expected_code != 0:
            results.append({
                "test_id": t["id"],
                "category": t["category"],
                "passed": True,
                "actual_stdout": "",
                "expected_stdout": "",
            })
            continue

        try:
            actual = json.loads(actual_stdout_raw)
        except json.JSONDecodeError:
            results.append({
                "test_id": t["id"],
                "category": t["category"],
                "passed": False,
                "error": "stdout_not_json",
                "actual_stdout": actual_stdout_raw,
                "expected_stdout": json.dumps(expected_keys),
            })
            continue

        keys_match = True
        mismatch = None
        for key, val in expected_keys.items():
            if actual.get(key) != val:
                keys_match = False
                mismatch = key
                break

        results.append({
            "test_id": t["id"],
            "category": t["category"],
            "passed": keys_match,
            "error": f"key_mismatch: {mismatch}" if not keys_match else None,
            "actual_stdout": json.dumps(actual),
            "expected_stdout": json.dumps(expected_keys),
        })

    return results


def score(tests: list[dict], results: list[dict]) -> tuple[float, float]:
    if not results:
        return (0.0, 0.0)

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    ff = passed / total

    bs_sum = 0.0
    for r in results:
        if r["passed"]:
            actual = r.get("actual_stdout", "")
            expected = r.get("expected_stdout", "")
            if actual and expected:
                dist = levenshtein(actual, expected)
                max_len = max(len(actual), len(expected))
                if max_len > 0:
                    bs_sum += 1.0 - (dist / max_len)
            else:
                bs_sum += 1.0
    bs = bs_sum / total if total > 0 else 0.0

    return (ff, bs)
