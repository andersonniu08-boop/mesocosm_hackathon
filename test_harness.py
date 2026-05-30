import json
import subprocess
import sys


def levenshtein(a, b):
    if len(a) < len(b):
        return levenshtein(b, a)
    if len(b) == 0:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            insert = prev[j + 1] + 1
            delete = curr[j] + 1
            sub = prev[j] + (0 if ca == cb else 1)
            curr.append(min(insert, delete, sub))
        prev = curr
    return prev[-1]


def run_tests(program_path, tests):
    results = []
    for test in tests:
        result = {"test_id": test["id"], "passed": False,
                  "actual_stdout": "", "expected_stdout": ""}

        try:
            proc = subprocess.run(
                [sys.executable, program_path] + test["args"],
                capture_output=True, text=True, timeout=5
            )
        except subprocess.TimeoutExpired:
            results.append(result)
            continue

        expected = test["expected"]
        result["actual_stdout"] = proc.stdout.strip()

        if proc.returncode != expected.get("exit_code", 0):
            results.append(result)
            continue

        stdout_keys = expected.get("stdout_keys")
        if stdout_keys is None:
            result["passed"] = True
            result["expected_stdout"] = ""
            results.append(result)
            continue

        try:
            actual = json.loads(proc.stdout)
        except json.JSONDecodeError:
            results.append(result)
            continue

        result["expected_stdout"] = json.dumps(stdout_keys, sort_keys=True)
        result["actual_stdout"] = json.dumps(actual, sort_keys=True)

        passed = True
        for key, value in stdout_keys.items():
            if key not in actual or actual[key] != value:
                passed = False
                break
        result["passed"] = passed
        results.append(result)

    return results


def score(tests, results):
    if not results:
        return (0.0, 0.0)

    passed_count = sum(1 for r in results if r["passed"])
    total_count = len(results)
    ff = passed_count / total_count

    bs_sum = 0.0
    for r in results:
        if r["passed"]:
            a = r["actual_stdout"]
            e = r["expected_stdout"]
            if not a and not e:
                bs_sum += 1.0
            else:
                dist = levenshtein(a, e)
                denom = max(len(a), len(e))
                bs_sum += 1.0 - (dist / denom)
    bs = bs_sum / total_count if total_count > 0 else 0.0

    return (ff, bs)
