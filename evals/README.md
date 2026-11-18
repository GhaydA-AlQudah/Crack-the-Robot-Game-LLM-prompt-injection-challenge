# Crack The Robot — Evaluation Suite

This folder contains an evaluation framework for testing the security
behavior of the three Crack The Robot levels.

## Dataset

The dataset contains 50 scenarios:

| Level | Scenarios |
|---|---:|
| Level 1 — Direct Tool Manipulation | 17 |
| Level 2 — Tool Result Contradiction / Logical Manipulation | 17 |
| Level 3 — Trusted Code Enforcement | 16 |
| Total | 50 |

Each scenario has:
- A unique ID.
- A target level.
- An attack category.
- An attack type.
- A difficulty label.
- One or more conversation turns.
- Expected security behavior.

All scenarios assume that the badge scanner and employee directory
are unavailable.

## Run the evaluation

Run from the project root:

```bash
python -m evals.runner