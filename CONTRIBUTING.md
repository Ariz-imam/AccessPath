# Contributing to AccessPath

Thank you for helping improve AccessPath.

## Development setup

1. Use Python 3.10 or later.
2. Create a virtual environment.
3. Install development dependencies with `python -m pip install -r requirements-dev.txt`.
4. Run the test suite with `python -m pytest -q` before making changes.

## Change guidelines

- Keep routing constraints separate from route-cost preferences.
- Do not treat a shortest route as accessible unless every edge satisfies the selected profile's hard constraints.
- Keep manual maintenance state separate from report-derived restrictions.
- Add or update tests for routing, status transitions, validation, and failure scenarios.
- Clearly label illustrative campus measurements and heuristic costs. Do not invent accessibility certification.
- Do not add secrets, local SQLite files, virtual environments, or personal information to commits.

## Pull requests

Include a concise description of the problem, the approach, relevant test results, and any known limitations. For changes to route behavior, include the test cases that demonstrate both expected and failure behavior.
