# Contributing

Thanks for your interest in contributing! Keep it simple and focused.

- Discuss: Open an Issue first if you plan a non-trivial change.
- Scope: One change per PR (code, tests, docs).
- Style: Run pre-commit hooks locally before pushing.
- Tests: Add/adjust tests near the code you change.
- Security: Never commit secrets. See SECURITY.md.

## Dev quickstart

- Install Python 3.11 and Docker.
- `pip install -e .` then `pytest -q`.
- `pip install pre-commit && pre-commit install && pre-commit run --all-files`.
- `docker compose up --build` to run the stack locally.

## License

By contributing you agree your contributions are licensed under the repository license (see LICENSE).
