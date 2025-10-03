from __future__ import annotations

import json
import textwrap
from hashlib import sha256
from typing import List, Tuple

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

from ..schemas.plan_v1_1 import PlanDocumentV11


DEFAULT_REQUIREMENTS: List[str] = [
    "numpy==1.26.4",
    "scikit-learn==1.5.1",
    "pandas==2.2.2",
    "matplotlib==3.9.0",
]


def _primary_metric(plan: PlanDocumentV11) -> str:
    return plan.metrics[0].name if plan.metrics else "metric"


def build_requirements(plan: PlanDocumentV11) -> Tuple[str, str]:
    requirements = set(DEFAULT_REQUIREMENTS)

    framework = plan.config.framework.lower()
    model_name = plan.model.name.lower()
    if "torch" in framework or "torch" in model_name:
        requirements.update({"torch==2.2.2", "torchvision==0.17.2"})
    if "datasets" in framework or "huggingface" in plan.dataset.name.lower():
        requirements.add("datasets==2.19.0")

    sorted_lines = sorted(requirements)
    requirements_text = "\n".join(sorted_lines) + "\n"
    env_hash = sha256("\n".join(sorted_lines).encode("utf-8")).hexdigest()
    return requirements_text, env_hash


def build_notebook_bytes(plan: PlanDocumentV11, plan_id: str) -> bytes:
    metric_name = _primary_metric(plan)
    metric_goal = plan.metrics[0].goal if plan.metrics else None
    goal_expr = "None" if metric_goal is None else f"{float(metric_goal):.6f}"

    intro = new_markdown_cell(
        textwrap.dedent(
            f"""
            # Plan {plan_id}

            This notebook was generated automatically from Plan JSON v1.1.
            It follows the declared dataset, model, and configuration using a
            deterministic CPU-only workflow.
            """
        ).strip()
    )

    setup_code = textwrap.dedent(
        f"""
        import json
        import os
        import random
        import sys
        from pathlib import Path

        import numpy as np

        try:
            import torch
            TORCH_AVAILABLE = True
        except ImportError:
            TORCH_AVAILABLE = False

        EVENTS_PATH = Path("events.jsonl")
        METRICS_PATH = Path("metrics.json")

        if EVENTS_PATH.exists():
            EVENTS_PATH.unlink()
        if METRICS_PATH.exists():
            METRICS_PATH.unlink()

        def log_event(event_type: str, payload: dict) -> None:
            EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
            with EVENTS_PATH.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({{"event": event_type, **payload}}) + "\n")

        def seed_everything(seed: int) -> None:
            random.seed(seed)
            np.random.seed(seed)
            if TORCH_AVAILABLE:
                torch.manual_seed(seed)
                if torch.cuda.is_available():
                    raise RuntimeError("E_GPU_REQUESTED: CUDA devices are not permitted during runs")
                torch.backends.cudnn.deterministic = True
                torch.backends.cudnn.benchmark = False

        SEED = {plan.config.seed}
        seed_everything(SEED)
        log_event("stage_update", {{"stage": "seed_check", "seed": SEED}})
        print("Notebook generated for Plan {plan_id}")
        print("Python version:", sys.version)
        print("Seed set to", SEED)
        if TORCH_AVAILABLE:
            print("Torch version:", torch.__version__)
        else:
            print("Torch not installed (not required for this plan)")
        """
    ).strip()

    dataset_code = textwrap.dedent(
        f"""
        from sklearn.datasets import make_classification
        from sklearn.model_selection import train_test_split

        log_event(
            "stage_update",
            {{
                "stage": "dataset_load",
                "dataset": "{plan.dataset.name}",
                "split": "{plan.dataset.split}",
            }},
        )

        X, y = make_classification(
            n_samples=512,
            n_features=32,
            n_informative=16,
            n_redundant=4,
            random_state=SEED,
        )
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, stratify=y, random_state=SEED
        )
        log_event(
            "metric_update",
            {{"metric": "dataset_samples", "value": int(X.shape[0])}},
        )
        """
    ).strip()

    model_code = textwrap.dedent(
        f"""
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import accuracy_score, precision_score, recall_score

        log_event("stage_update", {{"stage": "model_build", "model": "{plan.model.name}"}})
        model = LogisticRegression(
            max_iter=max(100, {plan.config.epochs} * 10),
            solver="lbfgs",
            random_state=SEED,
        )

        log_event("stage_update", {{"stage": "train"}})
        model.fit(X_train, y_train)

        log_event("stage_update", {{"stage": "evaluate"}})
        y_pred = model.predict(X_test)
        accuracy = float(accuracy_score(y_test, y_pred))
        precision = float(precision_score(y_test, y_pred, zero_division=0))
        recall = float(recall_score(y_test, y_pred, zero_division=0))

        metrics = {{
            "{metric_name}": accuracy,
            "precision": precision,
            "recall": recall,
        }}
        GOAL_VALUE = {goal_expr}
        if GOAL_VALUE is not None:
            metrics["{metric_name}_gap"] = accuracy - GOAL_VALUE

        METRICS_PATH.write_text(json.dumps({{"metrics": metrics}}, indent=2), encoding="utf-8")
        print(json.dumps({{"metrics": metrics}}, indent=2))
        log_event("metric_update", {{"metric": "{metric_name}", "value": accuracy}})
        if len(y_pred) > 0:
            log_event("sample_pred", {{"label": int(y_pred[0]), "stage": "evaluate"}})
        log_event("stage_update", {{"stage": "complete"}})
        """
    ).strip()

    cells = [
        intro,
        new_code_cell(setup_code),
        new_code_cell(dataset_code),
        new_code_cell(model_code),
    ]

    notebook = new_notebook(
        cells=cells,
        metadata={
            "kernelspec": {"name": "python3", "display_name": "Python 3"},
            "language_info": {"name": "python"},
        },
    )
    return nbformat.writes(notebook).encode("utf-8")
