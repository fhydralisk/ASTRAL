"""Opt-in training statistics for prepared observational data."""
from __future__ import annotations

from typing import Any

import numpy as np

from ..core import AgentContext, load_context_data
from ..evaluator.observational_contract import audit_contract, read_contract
from .base_tool import BaseTool, ToolMetadata
from .statistics_analysis import StatisticsTool


@BaseTool.register("observational_statistics")
class ObservationalStatisticsTool(BaseTool):
    """Inspect frozen training observations, leaving generic statistics unchanged."""

    metadata = ToolMetadata(name="observational_statistics")

    def execute(
        self, variables: list[str] | None = None, n_bins: int = 10,
        near_zero_threshold: float = 1e-8,
    ) -> dict[str, Any]:
        """Summarize the explicitly requested frozen training data view.

        Requires discovery_contract.json and context.data on disk. This tool is
        intentionally different from statistics_analysis, which always inspects
        the current context. Scientific measurement stops may still be audited.

        Args:
            variables: Variables or diagnostic expressions using exposed inputs.
                Defaults to numeric arrays present in the current context.
            n_bins: Number of equal-width histogram bins (1-100).
            near_zero_threshold: Initial absolute threshold for near-zero counts.
        """
        workspace = self.context.workspace
        contract = read_contract(workspace)
        if contract is None:
            raise ValueError("observational_statistics requires an explicit frozen discovery contract")
        frozen = load_context_data(
            workspace.path / "context.data", workspace=workspace,
        )["data"]
        report = audit_contract(contract, frozen)
        if not report["valid"]:
            raise ValueError("Statistics require a valid frozen discovery contract: "
                             + "; ".join(report["errors"]))
        if not (split_name := contract.get("split")):
            raise ValueError("Statistics require a frozen train/validation split")
        train = np.flatnonzero(np.asarray(frozen[split_name]) == "train")
        n_rows = len(frozen[contract["target"]])
        data = {}
        for name in self.context.data:
            if name not in frozen:
                raise ValueError(f"Live array {name!r} is not in the frozen handoff; save and validate it first")
            values = np.asarray(frozen[name])
            if values.shape == (n_rows,):
                data[name] = values[train]
            elif name == contract.get("covariance") and values.shape == (n_rows, n_rows):
                data[name] = values[np.ix_(train, train)]
            else:
                raise ValueError(f"Cannot select training observations for unaligned array {name!r}")
        # A standalone view avoids altering the caller's data, evaluator or split
        # cache. No fit, scoring or active evaluator method is invoked here.
        view = AgentContext(data=data, target=self.context.target)
        result = StatisticsTool(context=view).execute(variables, n_bins, near_zero_threshold)
        return {**result, "partition": "train", "partition_source": "discovery_contract.json",
                "n_rows": int(train.size), "validation_included": False}

    @classmethod
    def format_result_dict(cls, result: dict[str, Any]) -> str:
        return (f"Analysis partition: train ({result['n_rows']} frozen rows from "
                "discovery_contract.json; validation excluded).\n"
                + StatisticsTool.format_result_dict(result))
