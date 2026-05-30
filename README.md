# Software Evolution

A Mesocosm evaluation environment that measures a model's ability to understand software precisely enough that another model can rebuild it from the description alone.

## What it is

A benchmark for AI code understanding fidelity. The model under test receives source code and produces a structured JSON specification. A fixed reference reconstructor (GPT-4o) rebuilds the program from that spec. The rebuild is tested against a private test suite. Score = fraction of tests passed.

## Two tiers

**Tier 1 — Code Understanding Benchmark (MUST SHIP)**

Single-cycle evaluation. Model sees code → produces spec → reconstructor rebuilds → test suite scores the result.

**Tier 2 — Multi-Generation Evolution (STRETCH)**

Wraps Tier 1 in a recursive loop. Each rebuild becomes the next generation's input. Models compete on Software Half-Life (generations until the software breaks).

## Structure

```
├── docs/             # Design documents, specs, brainstorming
├── implementation/   # Per-person build plans (tim.md, anderson.md, robin.md)
├── fixtures/         # Evaluation programs (Pong + test scenarios)
├── adapters/         # Model interfaces (DeepSeek, Claude, GPT)
├── prompts/          # Summarizer and reconstructor prompt files
├── environment.py    # Tier 1 orchestrator
├── test_harness.py   # Subprocess runner + FF/BS scoring
├── run.py            # CLI: python run.py --model deepseek --heat 1
├── rank.py           # Leaderboard from results/
└── benchanything.json # Mesocosm registration
```

## Scoring

- **Functional Fidelity (FF):** Fraction of private tests the rebuild passes
- **Behavioral Similarity (BS):** Output closeness on passing tests
- **Software Half-Life (Tier 2):** Generations until FF drops below 50%

## Mesocosm Track

AGI & Real-World Modeling. The benchmark measures informational precision of model understanding — the software equivalent of technical handoffs between teams.

---

*May 2026 Hackathon*
