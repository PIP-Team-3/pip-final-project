"""
Model code generators.

Phase 1: SklearnLogisticGenerator (extracts current notebook.py logic)
Phase 2+: SklearnModelGenerator (multiple models), TorchCNNGenerator, TorchResNetGenerator
"""

from __future__ import annotations

import textwrap
from typing import List

from .base import CodeGenerator
from ...schemas.plan_v1_1 import PlanDocumentV11


class SklearnLogisticGenerator(CodeGenerator):
    """
    Generates LogisticRegression model with training and evaluation.

    Phase 1: This extracts the EXACT current logic from notebook.py (lines 142-179).
    No behavior change - ensures regression-free refactor.

    Future: This will be one of multiple sklearn model options.
    """

    def generate_imports(self, plan: PlanDocumentV11) -> List[str]:
        """Import statements for LogisticRegression."""
        return [
            "from sklearn.linear_model import LogisticRegression",
            "from sklearn.metrics import accuracy_score, precision_score, recall_score",
        ]

    def generate_code(self, plan: PlanDocumentV11) -> str:
        """
        Generate LogisticRegression training and evaluation code.

        - Builds model with max_iter based on plan.config.epochs
        - Trains on X_train, y_train
        - Evaluates on X_test, y_test
        - Computes accuracy, precision, recall
        - Writes metrics.json and logs events
        """
        # Extract metric info from plan
        metric_name = plan.metrics[0].name if plan.metrics else "metric"
        metric_goal = plan.metrics[0].goal if plan.metrics else None
        goal_expr = "None" if metric_goal is None else f"{float(metric_goal):.6f}"

        return textwrap.dedent(
            f"""
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

    def generate_requirements(self, plan: PlanDocumentV11) -> List[str]:
        """Pip requirements for LogisticRegression."""
        return ["scikit-learn==1.5.1"]
