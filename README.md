# OpenResto

Order intake system for a family rice restaurant via Zalo, serverless on AWS.

[![CI](https://github.com/lpham0427/open-resto/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/lpham0427/open-resto/actions/workflows/ci.yml)
[![Python 3.14](https://img.shields.io/badge/python-3.14-blue.svg)](https://www.python.org/downloads/)

## Overview

- **Problem:** a small family rice restaurant receives customer orders
  through Zalo and needs a reliable way to take them in.
- **Intended users:** the restaurant staff who take and prepare orders, and
  the customers who place orders through Zalo.
- **Status:** Under development. Only the project scaffold exists today; no
  application features are implemented yet.

## Architecture

Planned: a single AWS SAM stack with Python AWS Lambda functions.
See [docs/architecture.md](docs/architecture.md) (TBD) and the
architecture decision records in [docs/adr/](docs/adr/).

## Repository layout

```text
.github/          CI workflow, Dependabot config and pull request template
db/migrations/    Database migrations (planned, empty)
docs/             Architecture notes and decision records
docs/adr/         Architecture Decision Records (Nygard format)
evals/            Evaluation suites and data (planned, empty)
src/              Lambda source code; each subdirectory is an importable package
src/api/          HTTP entry point (placeholder)
src/worker/       Queue consumer entry point (placeholder)
src/tokens/       Scheduled maintenance entry point (placeholder)
src/shared/       Code shared by all functions, such as settings (placeholder)
tests/unit/       Unit tests
web/              Web front end (planned, empty)
```

## Prerequisites

- [Git](https://git-scm.com/)
- [uv](https://docs.astral.sh/uv/) (installs the Python version pinned in
  `.python-version` automatically)
- [AWS CLI](https://aws.amazon.com/cli/) and
  [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html):
  only needed for deployment

Windows PowerShell notes:

- Install uv with
  `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
  or `winget install --id=astral-sh.uv -e`, then open a new terminal.
- Install the AWS tools with `winget install -e --id Amazon.AWSCLI` and
  `winget install -e --id Amazon.SAM-CLI`.
- All commands in this README work unchanged in PowerShell. Line endings are
  normalized to LF by `.gitattributes`.

## Getting started

```powershell
git clone https://github.com/lpham0427/open-resto.git
cd open-resto
uv sync
uv run pytest
uv run prek install
```

`uv sync` creates `.venv/` and installs the runtime and `dev` dependencies.
`uv run prek install` installs the Git pre-commit hook.

## Development

Common commands:

| Task       | Command                         |
| ---------- | ------------------------------- |
| Lint       | `uv run ruff check .`           |
| Fix lint   | `uv run ruff check --fix .`     |
| Format     | `uv run ruff format .`          |
| Type-check | `uv run ty check`               |
| Test       | `uv run pytest`                 |
| All hooks  | `uv run prek run --all-files`   |

Dependencies (`pyproject.toml` is the single source of truth, `uv.lock` is
committed):

- **Runtime** dependencies go in `[project].dependencies`
  (`uv add <package>`). They are shipped to AWS Lambda. Do not add `boto3`;
  the Lambda runtime provides it.
- **Development** dependencies go in the `dev` group
  (`uv add --group dev <package>`).
- `src/requirements.txt` is a generated build artifact (ignored by Git).
  Generate it right before `sam build`:

  ```powershell
  uv export --frozen --no-dev --no-hashes --no-emit-project -o src/requirements.txt
  ```

Workflow:

- Use [Conventional Commits](https://www.conventionalcommits.org/)
  (for example `feat: ...`, `fix: ...`, `chore: ...`).
- Work on short-lived branches and open pull requests into `main`. CI must
  pass before merging.

## Configuration and secrets

- Environment variables: TBD. Runtime settings will be read from environment
  variables in `src/shared/settings.py`.
- Never commit secrets, credentials or private keys. The pre-commit hook runs
  `detect-private-key` as a safety net.
- `.env` and `.env.*` files are ignored by Git; only `.env.example` may be
  committed.

## Testing

- `tests/unit/`: unit tests, run with `uv run pytest`. Today this contains a
  smoke test that imports every package.
- `evals/`: Planned.

## Deployment

Planned: deployment with AWS SAM via GitHub Actions on merge to `main`.
No deployment workflow exists yet.

## Documentation

- [docs/architecture.md](docs/architecture.md): system architecture (TBD)
- [docs/adr/](docs/adr/): Architecture Decision Records
  - [0001 - Record architecture decisions](docs/adr/0001-record-architecture-decisions.md)

## License

No license has been chosen yet. All rights are reserved by default.
