# How to Contribute

Thanks for your interest in contributing to `cisco-aidefense-sdk`! Here are a few
general guidelines on contributing and reporting bugs that we ask you to review.
Following these guidelines helps to communicate that you respect the time of the
contributors managing and developing this open source project. In return, they
should reciprocate that respect in addressing your issue, assessing changes, and
helping you finalize your pull requests. In that spirit of mutual respect, we
endeavor to review incoming issues and pull requests within 10 days, and will
close any lingering issues or pull requests after 60 days of inactivity.

Please note that all of your interactions in the project are subject to our
[Code of Conduct](/CODE_OF_CONDUCT.md). This includes creation of issues or pull
requests, commenting on issues or pull requests, and extends to all interactions
in any real-time space e.g., Slack, Discord, etc.

## Table of Contents

- [Reporting Issues](#reporting-issues)
- [Development Setup](#development-setup)
- [Code Style](#code-style)
- [Testing](#testing)
- [Sending Pull Requests](#sending-pull-requests)
- [Other Ways to Contribute](#other-ways-to-contribute)

## Reporting Issues

Before reporting a new issue, please ensure that the issue was not already
reported or fixed by searching through our
[issues list](https://github.com/cisco-ai-defense/ai-defense-python-sdk/issues).

When creating a new issue, please be sure to include a **title and clear
description**, as much relevant information as possible, and, if possible, a
test case.

**If you discover a security bug, please do not report it through GitHub.
Instead, please see security procedures in [SECURITY.md](/SECURITY.md).**

## Development Setup

### Prerequisites

- Python 3.9 or newer
- [Poetry](https://python-poetry.org/) for dependency management

### Getting Started

```bash
# Fork and clone the repository
git clone https://github.com/<your-username>/ai-defense-python-sdk.git
cd ai-defense-python-sdk

# Install dependencies (including dev dependencies)
poetry install

# Activate the virtual environment
poetry shell

# Install pre-commit hooks
pre-commit install
```

### Project Structure

```
aidefense/
├── runtime/           # Runtime inspection clients and agentsec SDK
│   ├── agentsec/      # Agent Runtime SDK (auto-patching, config, inspectors)
│   ├── chat_inspect.py
│   ├── http_inspect.py
│   └── mcp_inspect.py
├── management/        # Management API clients
├── mcpscan/           # MCP server scanning
├── modelscan/         # Model file scanning
├── config.py          # SDK-wide configuration
└── exceptions.py      # Custom exceptions
```

## Code Style

This project uses [Black](https://github.com/psf/black) for code formatting.
Pre-commit hooks are configured to enforce this automatically.

```bash
# Format code manually
poetry run black aidefense/ examples/

# Run type checking
poetry run mypy aidefense/
```

- Follow [PEP 8](https://peps.python.org/pep-0008/) conventions.
- Use type hints for all public function signatures.
- Write docstrings for public classes and methods.
- All source files must include the Apache 2.0 license header (enforced by pre-commit).

## Testing

```bash
# Run the full test suite
poetry run pytest

# Run tests with coverage
poetry run pytest --cov=aidefense --cov-report=term-missing

# Run a specific test file
poetry run pytest tests/test_chat_inspect.py

# Run tests matching a keyword
poetry run pytest -k "test_inspect_prompt"
```

- All new features and bug fixes must include corresponding tests.
- Tests live in the `tests/` directory and mirror the `aidefense/` package structure.
- We use [pytest](https://docs.pytest.org/) with `pytest-asyncio` for async tests.

## Sending Pull Requests

Before sending a new pull request, take a look at existing pull requests and
issues to see if the proposed change or fix has been discussed in the past, or
if the change was already implemented but not yet released.

1. Fork the repository and create your branch from `main`.
2. Make your changes, add tests, and ensure the full test suite passes.
3. Run the pre-commit hooks: `pre-commit run --all-files`.
4. Update documentation if your change affects the public API.
5. Write a clear PR description explaining the **what** and **why**.

We expect new pull requests to include tests for any affected behavior, and, as
we follow semantic versioning, we may reserve breaking changes until the next
major version release.

## Other Ways to Contribute

We welcome anyone that wants to contribute to `cisco-aidefense-sdk` to triage and
reply to open issues to help troubleshoot and fix existing bugs. Here is what
you can do:

- Help ensure that existing issues follow the recommendations from the
  _[Reporting Issues](#reporting-issues)_ section, providing feedback to the
  issue's author on what might be missing.
- Review existing pull requests, and test patches against real existing
  applications that use `cisco-aidefense-sdk`.
- Write a test, or add a missing test case to an existing test.
- Improve or add documentation, examples, or tutorials.

Thanks again for your interest in contributing to `cisco-aidefense-sdk`!

:heart:
