from __future__ import annotations

import hashlib
import math
from typing import Any
from uuid import uuid4

from openai import pydantic_function_tool
from pydantic import BaseModel, Field, field_validator

from .errors import ToolValidationError
from .registry import FunctionToolSpec, function_tools

_DATASETS = {
    "cifar-10": {
        "id": "cifar10",
        "name": "CIFAR-10",
        "source": "torchvision",
        "license_id": "mit",
    },
    "sst-2": {
        "id": "sst2",
        "name": "SST-2",
        "source": "glue",
        "license_id": "apache-2.0",
    },
    "uci-adult": {
        "id": "uci-adult",
        "name": "UCI Adult",
        "source": "uci",
        "license_id": "uci" ,
    },
}

_DATASET_ALIASES = {
    "cifar10": "cifar-10",
    "sst2": "sst-2",
    "adult": "uci-adult",
}

_ALLOWED_LICENSES = {"mit", "apache-2.0", "uci"}
_ALLOWED_PACKAGES = {
    "numpy",
    "pandas",
    "scikit-learn",
    "torch",
    "torchvision",
    "transformers",
    "typer",
    "uvicorn",
}


class DatasetResolverArgs(BaseModel):
    query: str = Field(..., description="Dataset name or alias")

    @field_validator("query")
    @classmethod
    def _validate_query(cls, value: str) -> str:
        if not value or not value.strip():
            raise ToolValidationError("Dataset query cannot be blank")
        return value


class LicenseCheckerArgs(BaseModel):
    dataset_id: str

    @field_validator("dataset_id")
    @classmethod
    def _validate_dataset(cls, value: str) -> str:
        if not value or not value.strip():
            raise ToolValidationError("Dataset id cannot be blank")
        return value


class BudgetEstimatorArgs(BaseModel):
    epochs: int = Field(..., ge=1, le=500)
    dataset_size: int | None = Field(None, ge=1)
    batch_size: int | None = Field(None, ge=1)
    base_minutes: float = Field(5.0, ge=0.0)


class EnvLockBuilderArgs(BaseModel):
    python_version: str = Field(..., pattern=r"^3\.1[01]\.")
    packages: list[str]

    @field_validator("packages")
    @classmethod
    def _validate_packages(cls, values: list[str]) -> list[str]:
        if not values:
            raise ToolValidationError("At least one package pin is required")
        disallowed = [pkg for pkg in values if pkg.split("==")[0] not in _ALLOWED_PACKAGES]
        if disallowed:
            raise ToolValidationError(
                f"Packages not allow-listed for sandbox: {', '.join(disallowed)}"
            )
        if any("cuda" in pkg.lower() for pkg in values):
            raise ToolValidationError("CUDA/GPU packages are not allowed in CPU sandbox")
        return values


class SandboxSubmitArgs(BaseModel):
    design_id: str
    plan_version: str


class GapCalculatorArgs(BaseModel):
    claimed: float
    observed: float


def dataset_resolver(args: DatasetResolverArgs) -> dict[str, Any]:
    query = args.query.strip().lower()
    dataset_key = _DATASET_ALIASES.get(query, query)
    try:
        canonical = _DATASETS[dataset_key]
    except KeyError as exc:
        raise ToolValidationError(f"Dataset '{args.query}' is not allow-listed") from exc
    return canonical


def license_checker(args: LicenseCheckerArgs) -> dict[str, Any]:
    dataset = None
    for record in _DATASETS.values():
        if record["id"] == args.dataset_id:
            dataset = record
            break
    if dataset is None:
        raise ToolValidationError(f"Unknown dataset id '{args.dataset_id}'")
    license_id = dataset["license_id"]
    allowed = license_id in _ALLOWED_LICENSES
    if not allowed:
        raise ToolValidationError(
            f"License '{license_id}' for dataset '{dataset['id']}' is blocked by policy"
        )
    return {
        "dataset_id": dataset["id"],
        "license_id": license_id,
        "status": "allowed",
    }


def budget_estimator(args: BudgetEstimatorArgs) -> dict[str, Any]:
    dataset_size = args.dataset_size or 50000
    batch_size = args.batch_size or 64
    steps_per_epoch = math.ceil(dataset_size / batch_size)
    estimated_minutes = args.base_minutes + (steps_per_epoch * args.epochs * 0.005)
    return {"estimated_minutes": round(estimated_minutes, 2)}


def env_lock_builder(args: EnvLockBuilderArgs) -> dict[str, Any]:
    hash_source = f"{args.python_version}|{'|'.join(sorted(args.packages))}".encode("utf-8")
    content_hash = hashlib.sha256(hash_source).hexdigest()
    return {
        "python_version": args.python_version,
        "packages": args.packages,
        "content_hash": content_hash,
    }


def sandbox_submit(args: SandboxSubmitArgs) -> dict[str, Any]:
    run_id = f"run_{uuid4().hex[:12]}"
    return {"run_id": run_id, "plan_version": args.plan_version, "design_id": args.design_id}


def gap_calculator(args: GapCalculatorArgs) -> dict[str, Any]:
    if args.claimed == 0:
        raise ToolValidationError("Claimed metric must be non-zero to compute gap")
    delta = ((args.observed - args.claimed) / abs(args.claimed)) * 100
    return {"gap_percent": round(delta, 2)}


function_tools.register(
    FunctionToolSpec(
        name="dataset_resolver",
        description="Resolve dataset aliases to canonical records.",
        args_model=DatasetResolverArgs,
        handler=dataset_resolver,
        openai_tool=pydantic_function_tool(DatasetResolverArgs, name="dataset_resolver"),
    )
)
function_tools.register(
    FunctionToolSpec(
        name="license_checker",
        description="Verify dataset license is allow-listed.",
        args_model=LicenseCheckerArgs,
        handler=license_checker,
        openai_tool=pydantic_function_tool(LicenseCheckerArgs, name="license_checker"),
    )
)
function_tools.register(
    FunctionToolSpec(
        name="budget_estimator",
        description="Estimate runtime budget from plan parameters.",
        args_model=BudgetEstimatorArgs,
        handler=budget_estimator,
        openai_tool=pydantic_function_tool(BudgetEstimatorArgs, name="budget_estimator"),
    )
)
function_tools.register(
    FunctionToolSpec(
        name="env_lock_builder",
        description="Produce a deterministic environment lockfile hash.",
        args_model=EnvLockBuilderArgs,
        handler=env_lock_builder,
        openai_tool=pydantic_function_tool(EnvLockBuilderArgs, name="env_lock_builder"),
    )
)
function_tools.register(
    FunctionToolSpec(
        name="sandbox_submit",
        description="Submit a notebook design to the sandbox queue.",
        args_model=SandboxSubmitArgs,
        handler=sandbox_submit,
        openai_tool=pydantic_function_tool(SandboxSubmitArgs, name="sandbox_submit"),
    )
)
function_tools.register(
    FunctionToolSpec(
        name="gap_calculator",
        description="Compute reproduction gap as a percentage.",
        args_model=GapCalculatorArgs,
        handler=gap_calculator,
        openai_tool=pydantic_function_tool(GapCalculatorArgs, name="gap_calculator"),
    )
)
