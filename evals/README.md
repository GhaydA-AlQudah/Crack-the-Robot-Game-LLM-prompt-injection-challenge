# Prompt Injection Security Evaluation

This directory contains a real-model evaluation runner for the Crack the Robot application.

## What it measures

- Attack Success Rate (ASR)
- ASR by attack category
- False-refusal rate
- Tool-call rate
- Authorization-true rate
- Request latency and model-call latency
- Token usage and estimated API cost, when available

## Requirements

Activate the project's virtual environment and install the project's requirements.

The application must have a valid `LLM_API_KEY` configured in the local environment or `.env` file. Never commit API keys or real secrets.

## Run the evaluation

From the project root:

```powershell
python -m evals.runner
```

Results are saved as individual JSON files in `evals/results/`.

To print the latest saved report again:

```powershell
python -m evals.report
```

## Metrics

### Attack Success Rate

ASR is the percentage of evaluable attack trials that meet their declared attack-success criterion.

Inconclusive trials are excluded from the denominator and reported separately.

### ASR by category

The same calculation is performed separately for each attack category.

### False-refusal rate

This initial implementation uses configured refusal markers as a simple heuristic. It may misclassify legitimate explanatory responses. Review false-refusal cases manually before drawing conclusions.

### Tool-call rate

The percentage of completed trials in which the application recorded a tool call. A tool call is not automatically a security failure; its authorization and context must also be reviewed.

### Latency and cost

Request latency includes application overhead. Model latency measures the time spent inside the existing agent call.

Token-based cost is only calculated when token usage is available and verified model prices have been configured. Otherwise, cost is reported as unavailable.

## Limitations

- This is an initial evaluation suite, not a comprehensive security benchmark.
- Results depend on model version, prompts, generated session secrets, and runtime conditions.
- The current runner evaluates one message per new session.
- The scoring criteria cover only the specific outcomes declared by each scenario.
- Do not use real credentials or production secrets in test scenarios.
- Preserve raw results for auditability and manually review ambiguous outcomes before reporting results.
