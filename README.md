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
events/           Sample events for local invocation (sam local invoke)
functions/        Lambda function packages (each directory is an independent function)
  receive_zalo_event/  Webhook intake API (verifies HMAC, publishes to SQS FIFO)
  process_order/       Background order processor (consumes SQS FIFO queue)
  refresh_token/       OAuth token rotation entry point (scheduled maintenance)
shared/           Shared code packaged into functions at build time (e.g. envelope.py)
tests/unit/       Unit tests
web/              Web front end (planned, empty)
Makefile          Custom build recipes for SAM packaging (Metadata: BuildMethod: makefile)
samconfig.toml    SAM CLI configuration for dev and prod environments
template.yaml     AWS SAM template defining CloudFormation resources
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

- **Runtime** dependencies are defined per Lambda function in `[dependency-groups]`
  within `pyproject.toml` (e.g., `[dependency-groups.process_order]`).
  `receive_zalo_event` uses zero third-party packages for cold start <50ms.
  Do not add `boto3`; the Lambda Python runtime already provides it.
- **Development** dependencies go in the `dev` group
  (`uv add --group dev <package>`).
- Packaging is automated by AWS SAM via the root `Makefile` (`Metadata: BuildMethod: makefile`).
  Running `sam build` generates isolated deployment packages for each Lambda function.

Workflow:

- Use [Conventional Commits](https://www.conventionalcommits.org/)
  (for example `feat: ...`, `fix: ...`, `chore: ...`).
- Work on short-lived branches and open pull requests into `main`. CI must
  pass before merging.

## Configuration and secrets

- Environment variables:
  - `SSM_PARAM_OA_SECRET_KEY`: SSM parameter name storing the Zalo OA secret key.
  - `QUEUE_URL`: Target SQS FIFO Queue URL for webhook events.
- Never commit secrets, credentials or private keys. The pre-commit hook runs
  `detect-private-key` as a safety net.
- `.env` and `.env.*` files are ignored by Git; only `.env.example` may be
  committed.

## Testing

- `tests/unit/`: unit tests, run with `uv run pytest`. Today this contains a
  smoke test that imports every package.
- `evals/`: Planned.

## Deployment

Automatic deployment is configured via GitHub Actions (`.github/workflows/deploy.yml`) on merge to `main`.

### AWS OIDC Setup (One-time)
1. Deploy the CloudFormation template in `docs/infrastructure/github-oidc-role.yaml` to your AWS account.
2. In GitHub repository **Settings > Secrets and variables > Actions**, add:
   - `AWS_ROLE_ARN` (Secret/Variable): ARN of the created deployment role (e.g. `arn:aws:iam::<ACCOUNT_ID>:role/OpenRestoGitHubActionsDeploymentRole`).
   - `AWS_REGION` (Variable): Deployment region (e.g. `ap-southeast-1`, defaults to `ap-southeast-1`).
   - `SAM_STACK_NAME` (Variable): CloudFormation stack name (e.g. `open-resto-prod`, defaults to `open-resto-prod`).
3. Ensure the SSM parameters exist in your target AWS region:
   - `/open-resto/zalo/app-id` (Type: `String`)
   - `/open-resto/zalo/oa-secret-key` (Type: `SecureString`)

## Documentation

- [docs/architecture.md](docs/architecture.md): system architecture (TBD)
- [docs/adr/](docs/adr/): Architecture Decision Records
  - [0001 - Record architecture decisions](docs/adr/0001-record-architecture-decisions.md)

## License

No license has been chosen yet. All rights are reserved by default.
