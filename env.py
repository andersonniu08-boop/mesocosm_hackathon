import json
from typing import Any

from bench_common.env_sdk.base import BaseEnv, StepResult


REQUIRED_TOP_FIELDS = [
    "invocation", "output_contract", "arguments",
    "constants", "rules", "rule_order", "error_conditions",
]

REQUIRED_ARG_KEYS = {"name", "type", "required"}
REQUIRED_CONST_KEYS = {"symbol", "value"}
REQUIRED_RULE_KEYS = {"id", "trigger", "effect"}
REQUIRED_ERROR_KEYS = {"when", "action"}

GOLD_PATH = "fixtures/pong/gold_genome.json"
SOURCE_PATH = "fixtures/pong/source.py"


def _all_keys_present(obj: dict, required: set) -> bool:
    return required.issubset(obj.keys())


def _score_genome(genome: dict) -> tuple[float, list[str]]:
    checks_total = 0
    checks_passed = 0
    details: list[str] = []

    for field in REQUIRED_TOP_FIELDS:
        checks_total += 1
        if field in genome and genome[field]:
            checks_passed += 1
        else:
            details.append(f"missing or empty: {field}")

    out = genome.get("output_contract", {})
    if isinstance(out, dict):
        checks_total += 1
        if out.get("format") and out.get("on_success") and out.get("on_error"):
            checks_passed += 1
        else:
            details.append("output_contract missing sub-fields")

    args = genome.get("arguments", [])
    if isinstance(args, list) and len(args) > 0:
        checks_total += 1
        checks_passed += 1
        for i, arg in enumerate(args):
            if isinstance(arg, dict):
                checks_total += 1
                if _all_keys_present(arg, REQUIRED_ARG_KEYS):
                    checks_passed += 1
                else:
                    details.append(f"argument[{i}] missing keys")
    else:
        checks_total += 1
        details.append("arguments empty or not a list")

    consts = genome.get("constants", [])
    if isinstance(consts, list) and len(consts) > 0:
        checks_total += 1
        checks_passed += 1
        for i, c in enumerate(consts):
            if isinstance(c, dict):
                checks_total += 1
                if _all_keys_present(c, REQUIRED_CONST_KEYS):
                    checks_passed += 1
                else:
                    details.append(f"constant[{i}] missing keys")
    else:
        checks_total += 1
        details.append("constants empty or not a list")

    rules = genome.get("rules", [])
    if isinstance(rules, list) and len(rules) > 0:
        checks_total += 1
        checks_passed += 1
        for i, r in enumerate(rules):
            if isinstance(r, dict):
                checks_total += 1
                if _all_keys_present(r, REQUIRED_RULE_KEYS):
                    checks_passed += 1
                else:
                    details.append(f"rule[{i}] missing keys")
    else:
        checks_total += 1
        details.append("rules empty or not a list")

    order = genome.get("rule_order", [])
    checks_total += 1
    if isinstance(order, list) and len(order) > 0:
        checks_passed += 1
    else:
        details.append("rule_order empty or not a list")

    errs = genome.get("error_conditions", [])
    if isinstance(errs, list) and len(errs) > 0:
        checks_total += 1
        checks_passed += 1
        for i, e in enumerate(errs):
            if isinstance(e, dict):
                checks_total += 1
                if _all_keys_present(e, REQUIRED_ERROR_KEYS):
                    checks_passed += 1
                else:
                    details.append(f"error_condition[{i}] missing keys")
    else:
        checks_total += 1
        details.append("error_conditions empty or not a list")

    score = checks_passed / checks_total if checks_total > 0 else 0.0
    return score, details


class PongSummarizationEnv(BaseEnv):
    def __init__(self) -> None:
        self._source_code = open(SOURCE_PATH).read()

    def reset(self, seed: int | None = None, **params: Any) -> dict[str, Any]:
        return {
            "instruction": (
                "Analyze the following Python source code for a headless Pong game. "
                "Produce a JSON specification (genome) describing every detail of the "
                "program: how to invoke it, its arguments, constants, game rules, rule "
                "ordering, and error conditions. The specification must be complete "
                "enough that a developer could rebuild the program from it alone."
            ),
            "source_code": self._source_code,
            "expected_format": {
                "invocation": "CLI invocation template string",
                "output_contract": {
                    "format": "json",
                    "on_success": "what happens on success",
                    "on_error": "what happens on error"
                },
                "arguments": [
                    {"name": "ball-x", "type": "integer", "range": [0, 600], "required": True, "default": None}
                ],
                "constants": [
                    {"symbol": "FIELD_WIDTH", "value": 600}
                ],
                "rules": [
                    {"id": "move_ball", "trigger": "when condition", "effect": "what changes"}
                ],
                "rule_order": ["move_ball", "wall_bounce_top"],
                "error_conditions": [
                    {"when": "condition", "action": "what to do"}
                ]
            },
        }

    def step(self, action: Any) -> StepResult:
        try:
            if isinstance(action, str):
                genome = json.loads(action)
            elif isinstance(action, dict):
                genome = action
            else:
                genome = json.loads(str(action))
        except (json.JSONDecodeError, TypeError, ValueError):
            return StepResult(
                observation={"error": "action must be valid JSON"},
                reward=0.0,
                terminated=True,
                truncated=False,
                info={"error": "invalid_json"},
            )

        score, details = _score_genome(genome)

        return StepResult(
            observation={
                "score": round(score, 4),
                "checks_passed": f"{details}",
                "genome_received": True,
            },
            reward=score,
            terminated=True,
            truncated=False,
            info={
                "genome_score": str(round(score, 4)),
                "issues": "; ".join(details) if details else "none",
            },
        )
