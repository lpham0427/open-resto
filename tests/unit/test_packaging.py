"""Unit tests for SAM custom build packaging and Makefile target parity."""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


class _CfnYamlLoader(yaml.SafeLoader):
    """YAML loader that ignores AWS CloudFormation intrinsic tags."""


def _ignore_cfn_tag(loader: yaml.SafeLoader, _tag_suffix: str, node: yaml.Node) -> Any:
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    return None


_CfnYamlLoader.add_multi_constructor("!", _ignore_cfn_tag)


def _load_sam_template() -> dict[str, Any]:
    template_path = REPO_ROOT / "template.yaml"
    with template_path.open("r", encoding="utf-8") as f:
        data = yaml.load(f, Loader=_CfnYamlLoader)  # noqa: S506
    assert isinstance(data, dict), "template.yaml must be a valid mapping"
    return data


def test_functions_use_makefile_build_method() -> None:
    """All Lambda functions must configure custom build with makefile."""
    template = _load_sam_template()
    resources = template.get("Resources", {})

    functions = {
        name: config
        for name, config in resources.items()
        if config.get("Type") == "AWS::Serverless::Function"
    }

    assert functions, "At least one AWS::Serverless::Function must be defined"

    makefile_path = REPO_ROOT / "Makefile"
    assert makefile_path.is_file(), "Makefile must exist at the repository root"
    makefile_content = makefile_path.read_text(encoding="utf-8")

    for func_name, func_config in functions.items():
        metadata = func_config.get("Metadata", {})
        assert metadata.get("BuildMethod") == "makefile", (
            f"Function {func_name} must specify Metadata.BuildMethod: makefile"
        )

        expected_target = f"build-{func_name}:"
        assert expected_target in makefile_content, (
            f"Makefile must define target '{expected_target}' for {func_name}"
        )


def test_function_handlers_are_resolvable() -> None:
    """Every function handler defined in template.yaml must point to a real callable."""
    template = _load_sam_template()
    resources = template.get("Resources", {})

    functions = {
        name: config
        for name, config in resources.items()
        if config.get("Type") == "AWS::Serverless::Function"
    }

    for func_name, func_config in functions.items():
        handler_path = func_config.get("Properties", {}).get("Handler", "")
        assert handler_path, f"Function {func_name} must declare a Handler"

        module_path, func_attr = handler_path.rsplit(".", 1)
        mod = importlib.import_module(module_path)
        handler_callable = getattr(mod, func_attr, None)
        assert callable(handler_callable), (
            f"Handler {handler_path} on {func_name} is not callable"
        )


def test_dependency_groups_configured_in_pyproject() -> None:
    """pyproject.toml must define isolated dependency groups."""
    pyproject_path = REPO_ROOT / "pyproject.toml"
    with pyproject_path.open("rb") as f:
        config = tomllib.load(f)

    groups = config.get("dependency-groups", {})
    assert "dev" in groups, "dev dependency group must exist"
    assert "process_order" in groups, "process_order dependency group must exist"
    assert "aws-lambda-powertools>=3.0.0" in groups["process_order"], (
        "process_order must include aws-lambda-powertools"
    )


def test_webhook_artifact_isolation(tmp_path: Path) -> None:
    """Webhook artifact must include receive_zalo_event and shared only."""
    src_webhook = REPO_ROOT / "functions" / "receive_zalo_event"
    src_shared = REPO_ROOT / "shared"

    staging_webhook = tmp_path / "receive_zalo_event"
    staging_shared = tmp_path / "shared"

    shutil.copytree(src_webhook, staging_webhook)
    shutil.copytree(src_shared, staging_shared)

    # Verify other packages are NOT included in the artifact
    assert not (tmp_path / "process_order").exists()
    assert not (tmp_path / "refresh_token").exists()

    # Verify that imports work from staging root in an isolated subprocess
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path)
    res = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import receive_zalo_event.app, receive_zalo_event.settings;"
                "import shared.envelope;"
                "assert callable(receive_zalo_event.app.lambda_handler);"
                "assert callable(receive_zalo_event.settings.get_oa_secret_key);"
                "assert hasattr(shared.envelope, 'ZaloWebhookEnvelope')"
            ),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"Import check failed: {res.stderr}"


def test_process_order_artifact_isolation(tmp_path: Path) -> None:
    """Artifact must include process_order and shared without webhook package."""
    src_process_order = REPO_ROOT / "functions" / "process_order"
    src_shared = REPO_ROOT / "shared"

    staging_process_order = tmp_path / "process_order"
    staging_shared = tmp_path / "shared"

    shutil.copytree(src_process_order, staging_process_order)
    shutil.copytree(src_shared, staging_shared)

    # Verify webhook package is NOT included in the artifact
    assert not (tmp_path / "receive_zalo_event").exists()

    # Verify that imports work from staging root in an isolated subprocess
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path)
    res = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import process_order.app, shared.envelope;"
                "assert callable(process_order.app.lambda_handler);"
                "assert hasattr(shared.envelope, 'ZaloWebhookEnvelope')"
            ),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"Import check failed: {res.stderr}"
