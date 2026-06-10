# OWASP BenchmarkPython Selected Dataset

## Source

- Repository: https://github.com/OWASP-Benchmark/BenchmarkPython
- Project: OWASP Benchmark for Python
- Purpose: Evaluate the accuracy of Python software vulnerability detection tools.

## Usage in Task-Link

This selected subset is used to validate the M2 Code Review Agent.

The selected cases focus on:

- SQL Injection (CWE-89)
- Cross-Site Scripting (CWE-79)
- Path Traversal (CWE-22)
- Command Injection (CWE-78)
- Weak Hash / Weak Crypto (CWE-328)

## Selection Policy

The full repository was not copied into the Task-Link dataset.

Only selected `testcode/BenchmarkTestXXXXX.py` files and matching rows from `expectedresults-0.1.csv` were copied.

Both vulnerable and non-vulnerable cases were included to evaluate true positives, false positives, true negatives, and false negatives.

Each category has 5 vulnerable (true) and 5 non-vulnerable (false) cases = 10 per category = 50 total.

## Target Module

- M2 Code Review Agent

## Not Used For

This dataset is not the primary dataset for M3 test coverage, N+1 query, time complexity, or performance analysis.
