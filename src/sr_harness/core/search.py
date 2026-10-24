# Copyright (c) 2026-present, Yumeow. Licensed under the MIT License.
"""In-memory state for one symbolic-regression search run."""
from __future__ import annotations

import json
import math
import threading
import uuid
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import numpy as np

from .tool import ToolCall, ToolCallResult

ParentRelation = Literal["continuation", "restart_seed", "context_merge"]


def json_value(value: Any) -> Any:
    """Recursively convert runtime objects and NumPy scalars/arrays into standards-compliant JSON values.

    Replaces non-finite floats (``NaN``, ``±inf``) with ``None`` so the output
    can be serialized strictly by standard JSON encoders.

    Args:
        value: Arbitrary Python or NumPy value to sanitize.

    Returns:
        Any: JSON-serializable structure made of primitives, lists, and dicts.
    """
    if value is None or type(value) in (str, int, bool):
        return value
    if is_dataclass(value) and not isinstance(value, type):
        return json_value(asdict(value))
    if isinstance(value, np.ndarray):
        return json_value(value.tolist())
    if isinstance(value, np.generic):
        return json_value(value.item())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, ToolCall):
        return {
            "name": value.name,
            "params": json_value(value.params),
            "id": value.id,
            "raw": json_value(value.raw),
            "raw_str": value.raw_str,
        }
    if isinstance(value, ToolCallResult):
        return {
            "ok": value.ok,
            "result": json_value(value.result),
            "result_str": value.result_str,
            "meta_data": json_value(value.meta_data),
        }
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    try:
        json.dumps(value, allow_nan=False)
        return value
    except (TypeError, ValueError):
        return str(value)


@dataclass(frozen=True, slots=True)
class SearchCoordinate:
    """Four-dimensional ``(R, C, L, K)`` coordinate identifying a node in the symbolic-regression search tree.

    Attributes:
        R: One-based outer restart index.
        C: One-based parallel conversation-branch index.
        L: One-based iterative refinement-step index.
        K: One-based local response-sample index.
    """
    R: int
    C: int
    L: int
    K: int


@dataclass(frozen=True, slots=True)
class ParentLink:
    """Directed link connecting a search-tree node to one of its parent nodes.

    Attributes:
        parent_node_id: Unique node identifier of the parent search node.
        relation: Link strength—``"strong"`` for the primary conversation
            continuation or ``"weak"`` for sibling tool-output context.
    """
    parent_node_id: str
    relation: ParentRelation

    def to_dict(self) -> dict[str, str]:
        """Serialize the parent link to a JSON-compatible dictionary.

        Returns:
            dict[str, str]: Dictionary with ``parent_node_id`` and ``relation``.
        """
        return {"node_id": self.parent_node_id, "relation": self.relation}


@dataclass(slots=True)
class SearchNode:
    """Recorded state for a single ``(R, C, L, K)`` node in the search tree.

    Attributes:
        run_id: Unique identifier of the owning search run.
        node_id: Unique identifier of this search node.
        node_label: Short human-readable label (e.g., ``"R1-C1-L2-K1"``).
        coordinate: Structured :class:`SearchCoordinate` for this node.
        parents: Tuple of :class:`ParentLink` references to predecessor nodes.
        created_at: UTC ISO-8601 timestamp when the node was recorded.
        core: Lightweight summary (formula, metrics, tool names, content preview).
        detail: Full prompt messages, raw response, tool call outputs, and usage.
    """
    run_id: str
    node_id: str
    node_label: str
    coordinate: SearchCoordinate
    parents: tuple[ParentLink, ...]
    created_at: str
    core: dict[str, Any]
    detail: dict[str, Any]

    def to_dict(self, *, include_detail: bool = True) -> dict[str, Any]:
        """Serialize the search node to a dictionary for logging or WebUI streaming.

        Args:
            include_detail: If ``True``, include the full ``detail`` payload (prompts,
                raw responses, and full tool results); if ``False``, omit ``detail``
                for lightweight tree rendering.

        Returns:
            dict[str, Any]: JSON-serializable node dictionary.
        """
        record = {
            "run_id": self.run_id,
            "node_id": self.node_id,
            "node_label": self.node_label,
            "created_at": self.created_at,
            "coord": asdict(self.coordinate),
            "progress": (
                f"(R={self.coordinate.R}) x (C={self.coordinate.C}) x "
                f"(L={self.coordinate.L}) x (K={self.coordinate.K})"
            ),
            "parents": [parent.to_dict() for parent in self.parents],
            "core": json_value(self.core),
        }
        if include_detail:
            record["detail"] = json_value(self.detail)
        return record


@dataclass(slots=True)
class CandidateRecord:
    """Evaluated candidate formula together with its provenance node and split metrics.

    Attributes:
        formula: Canonical string representation of the fitted candidate expression.
        node_id: Identifier of the search node that produced this candidate.
        details: Evaluation payload containing ``data_split_results``, ``complexity``,
            and optional residual diagnostics.
    """
    formula: str
    node_id: str
    details: dict[str, Any] = field(default_factory=dict)

    def split_metrics(self, split: str) -> dict[str, Any]:
        """Return the metric dictionary for a specific dataset split (e.g., ``"train"`` or ``"validation"``).

        Args:
            split: Name of the data split to look up.

        Returns:
            dict[str, Any]: Metrics recorded for ``split``, or an empty dictionary if absent.
        """
        return (
            self.details.get("data_split_results", {})
            .get(split, {})
            .get("metrics", {})
        )

    def metric(self, name: str, split: str) -> Any:
        """Look up a single numeric metric value on the specified data split.

        Args:
            name: Metric key (such as ``"mse"``, ``"rmse"``, or ``"r2"``).
            split: Name of the data split (e.g., ``"validation"`` or ``"train"``).

        Returns:
            Any: Metric value if present on ``split`` (or at the top level of ``details``),
                otherwise ``None``.
        """
        return self.split_metrics(split).get(name)

    @property
    def complexity(self) -> Any:
        """Return the structural complexity score of the candidate formula.

        Returns:
            Any: Integer/float complexity value from ``details``, or ``None`` if unavailable.
        """
        return self.metric("complexity", "train")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the candidate record for ``result.json`` or state snapshots.

        Returns:
            dict[str, Any]: Dictionary containing ``formula``, ``node_id``, and ``details``.
        """
        return {
            "formula": self.formula,
            "node_id": self.node_id,
            "details": json_value(self.details),
        }

    def display_dict(self) -> dict[str, Any]:
        """Build a flattened dictionary with top-level ``mse``, ``r2``, and ``complexity`` for UI cards.

        Returns:
            dict[str, Any]: Flattened candidate dictionary ready for frontend rendering.
        """
        split = "validation" if self.split_metrics("validation") else "train"
        return self.to_dict() | {"split": split} | json_value(self.split_metrics(split))


@dataclass(slots=True)
class SearchResult:
    """Final summary of a completed, early-stopped, interrupted, or failed symbolic-regression run.

    Attributes:
        status: Terminal run status string.
        progress: Human-readable ``(R, C, L, K)`` progress summary.
        candidates: Ranked list of all unique :class:`CandidateRecord` instances.
        pareto_front: Indices into ``candidates`` forming the Pareto front.
        best_candidate: Index of the top-ranked candidate in ``candidates`` (usually ``0``),
            or ``None`` when no valid candidate was found.
    """
    status: Literal["completed", "early_stopped", "interrupted", "failed"]
    progress: str
    candidates: list[CandidateRecord]
    pareto_front: list[int]
    best_candidate: int | None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the search result for ``result.json`` and API responses.

        Returns:
            dict[str, Any]: JSON-serializable dictionary of run status, candidates,
                Pareto front indices, and best candidate index.
        """
        return {
            "status": self.status,
            "progress": self.progress,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "pareto_front": list(self.pareto_front),
            "best_candidate": self.best_candidate,
        }


class SearchRunState:
    """Authoritative in-memory and on-disk state tracker for one symbolic-regression run.

    Records every ``(R, C, L, K)`` search node, deduplicates and ranks candidate
    formulas, computes the Pareto front, and optionally persists ``run.json``,
    ``nodes.jsonl``, and ``result.json`` under ``save_path``.
    """

    def __init__(
        self,
        save_path: str | Path | None,
        ranking_metric: str,
        larger_is_better: bool,
        agent_metadata: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> None:
        """Initialize the search run state and write ``run.json`` when ``save_path`` is provided.

        Args:
            save_path: Directory for persisting run logs, or ``None`` for in-memory only.
            ranking_metric: Metric name used to rank candidates (e.g., ``"mse"``).
            larger_is_better: Whether larger values of ``ranking_metric`` are preferred.
            agent_metadata: Optional startup configuration metadata written to ``run.json``.
            run_id: Optional explicit run identifier (generated automatically when omitted).
        """
        if run_id is not None and (not isinstance(run_id, str) or not run_id):
            raise ValueError("run_id must be None or a non-empty string")
        self.run_id = uuid.uuid4().hex if run_id is None else run_id
        self.ranking_metric = ranking_metric
        self.larger_is_better = larger_is_better
        self.nodes: dict[str, SearchNode] = {}
        self._candidates: list[CandidateRecord] = []
        self._lock = threading.RLock()
        self._save_path = Path(save_path) if save_path is not None else None
        self._nodes_path = self._save_path / "nodes.jsonl" if self._save_path else None
        self._result_path = self._save_path / "result.json" if self._save_path else None
        if self._save_path is not None:
            self._save_path.mkdir(parents=True, exist_ok=True)
            metadata = {
                "run_id": self.run_id,
                "created_at": self.now(),
                "agent": agent_metadata or {},
            }
            self._write_json(self._save_path / "run.json", metadata)

    @staticmethod
    def now() -> str:
        """Return the current UTC timestamp formatted as an ISO-8601 string.

        Returns:
            str: UTC timestamp ending with ``"Z"``.
        """
        return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")

    @staticmethod
    def node_label(R: int, C: int, L: int, K: int) -> str:
        """Format a compact display label for a search coordinate.

        Args:
            R: One-based restart index.
            C: One-based conversation-branch index.
            L: One-based refinement-step index.
            K: One-based local-sample index.

        Returns:
            str: Label formatted as ``"R{R}-C{C}-L{L}-K{K}"``.
        """
        return f"R{R}-C{C}-L{L}-K{K}"

    def node_id(self, R: int, C: int, L: int, K: int) -> str:
        """Build the globally unique node identifier for coordinate ``(R, C, L, K)`` in this run.

        Args:
            R: One-based restart index.
            C: One-based conversation-branch index.
            L: One-based refinement-step index.
            K: One-based local-sample index.

        Returns:
            str: Unique node identifier ``"{run_id}:R{R}-C{C}-L{L}-K{K}"``.
        """
        return f"{self.run_id}:{self.node_label(R=R, C=C, L=L, K=K)}"

    @staticmethod
    def parent_link(parent_node_id: str, relation: ParentRelation) -> ParentLink:
        """Create a validated :class:`ParentLink` connecting a child node to ``parent_node_id``.

        Args:
            parent_node_id: Unique identifier of the parent search node.
            relation: Link relation type (``"strong"`` or ``"weak"``).

        Returns:
            ParentLink: Constructed parent link instance.
        """
        return ParentLink(parent_node_id=parent_node_id, relation=relation)

    def register_iteration(
        self,
        response_list: list,
        results_list: list,
        parents: tuple[ParentLink, ...],
        prompt: list[dict[str, Any]],
        usage: dict[str, Any],
        R: int,
        L: int,
        C: int,
    ) -> None:
        """Record ``SearchNode`` entries for all ``K`` local samples in step ``(R, C, L)``.

        Args:
            response_list: Sampled model responses for the step.
            results_list: Tool execution results aligned with ``response_list``.
            parents: Tuple of :class:`ParentLink` objects inherited from previous steps.
            prompt: Prompt messages sent to the model for this step.
            usage: Token and cost accounting dictionary for the step.
            R: One-based restart index.
            L: One-based refinement-step index.
            C: One-based conversation-branch index.
        """
        with self._lock:
            for K, (response, results) in enumerate(zip(response_list, results_list), 1):
                content = response.content
                tool_calls = response.tool_calls
                message = response.message
                coordinate = SearchCoordinate(R=R, C=C, L=L, K=K)
                node = SearchNode(
                    run_id=self.run_id,
                    node_id=self.node_id(R=R, C=C, L=L, K=K),
                    node_label=self.node_label(R=R, C=C, L=L, K=K),
                    coordinate=coordinate,
                    parents=parents,
                    created_at=self.now(),
                    core=self._build_core(content, tool_calls, results, message),
                    detail={
                        "prompt": json_value(prompt),
                        "message": json_value(message),
                        "content": content,
                        "tool_calls": json_value(tool_calls),
                        "tool_results": json_value(results),
                        "usage": json_value(usage),
                    },
                )
                self.nodes[node.node_id] = node
                if self._nodes_path is not None:
                    with self._nodes_path.open("a", encoding="utf-8") as stream:
                        stream.write(
                            json.dumps(node.to_dict(), ensure_ascii=False, allow_nan=False) + "\n"
                        )

    def push_candidate(self, candidate: CandidateRecord) -> bool:
        """Insert a candidate formula or replace an existing record for the same formula if the new one ranks higher.

        Args:
            candidate: Newly evaluated :class:`CandidateRecord`.

        Returns:
            bool: ``True`` if the candidate was added or improved upon an existing entry;
                ``False`` if an equal or better record for the same formula already existed.
        """
        priority = self._candidate_priority(candidate)
        if priority is None:
            return False
        with self._lock:
            self._candidates.append(candidate)
        return True

    def update_diagnostics(self, formula: str, diagnostics: dict[str, Any]) -> None:
        """Attach residual diagnostic metadata to an existing candidate formula record.

        Args:
            formula: Canonical formula string identifying the candidate.
            diagnostics: Diagnostic dictionary to store under ``details["diagnostics"]``.
        """
        with self._lock:
            for candidate in self._candidates:
                if candidate.formula == formula:
                    candidate.details["eic_diagnostics"] = diagnostics

    def ranked_candidates(self) -> list[CandidateRecord]:
        """Return all recorded candidates sorted from best to worst under the active ranking metric.

        Returns:
            list[CandidateRecord]: Sorted list of candidate records.
        """
        with self._lock:
            ranked = [
                (priority, candidate)
                for candidate in self._candidates
                if (priority := self._candidate_priority(candidate)) is not None
            ]
            return [candidate for _, candidate in sorted(ranked, key=lambda item: item[0])]

    def pareto_indices(self, candidates: list[CandidateRecord] | None = None) -> list[int]:
        """Compute the indices of candidates that lie on the accuracy-complexity Pareto front.

        Args:
            candidates: Optional candidate list to inspect (defaults to :meth:`ranked_candidates`).

        Returns:
            list[int]: Zero-based indices into ``candidates`` ordered by non-decreasing complexity.
        """
        candidates = candidates if candidates is not None else self.ranked_candidates()
        indices = []
        current_complexity = float("inf")
        for index, candidate in enumerate(candidates):
            try:
                complexity = float(candidate.complexity)
            except (TypeError, ValueError):
                complexity = float("inf")
            if complexity < current_complexity:
                indices.append(index)
                current_complexity = complexity
        return indices

    def result(self, status: str, progress: str) -> SearchResult:
        """Build and optionally persist the :class:`SearchResult` snapshot for the current state.

        Args:
            status: Run completion status string.
            progress: Human-readable ``(R, C, L, K)`` progress string.

        Returns:
            SearchResult: Snapshot containing ranked candidates and Pareto front indices.
        """
        candidates = self.ranked_candidates()
        result = SearchResult(
            status=status,
            progress=progress,
            candidates=candidates,
            pareto_front=self.pareto_indices(candidates),
            best_candidate=0 if candidates else None,
        )
        if self._result_path is not None:
            self._write_json(self._result_path, result.to_dict())
        return result

    def records(self, *, include_detail: bool = False) -> list[dict[str, Any]]:
        """Return serialized search-tree node dictionaries in creation order.

        Args:
            include_detail: Whether to include full prompt/response/tool payloads.

        Returns:
            list[dict[str, Any]]: Serialized node records.
        """
        with self._lock:
            nodes = list(self.nodes.values())
        return [node.to_dict(include_detail=include_detail) for node in nodes]

    @property
    def node_count(self) -> int:
        """Return the total number of search nodes recorded so far.

        Returns:
            int: Number of nodes in the search tree.
        """
        with self._lock:
            return len(self.nodes)

    @property
    def latest_coordinate(self) -> SearchCoordinate | None:
        """Return the coordinate of the most recently recorded search node.

        Returns:
            SearchCoordinate | None: Latest coordinate, or ``None`` if no nodes exist yet.
        """
        with self._lock:
            if not self.nodes:
                return None
            node_id = next(reversed(self.nodes))
            return self.nodes[node_id].coordinate

    def export_state(self) -> dict[str, Any]:
        """Export a JSON-serializable snapshot of all nodes and candidates for session persistence.

        Returns:
            dict[str, Any]: State dictionary that can be passed to :meth:`from_state`.
        """
        with self._lock:
            return {
                "version": 1,
                "run_id": self.run_id,
                "ranking_metric": self.ranking_metric,
                "larger_is_better": self.larger_is_better,
                "nodes": [node.to_dict(include_detail=True) for node in self.nodes.values()],
                "candidates": [candidate.to_dict() for candidate in self._candidates],
            }

    @classmethod
    def from_state(cls, snapshot: dict[str, Any], save_path: str | Path | None = None) -> "SearchRunState":
        """Reconstruct a :class:`SearchRunState` instance from an :meth:`export_state` snapshot.

        Args:
            snapshot: Previously exported state dictionary.
            save_path: Optional directory for subsequent file persistence.

        Returns:
            SearchRunState: Restored search run state.
        """
        expected_fields = {
            "version", "run_id", "ranking_metric", "larger_is_better",
            "nodes", "candidates",
        }
        if set(snapshot) != expected_fields:
            raise ValueError("Persisted SearchRunState does not match the current schema")
        if snapshot["version"] != 1:
            raise ValueError("Unsupported SearchRunState snapshot version")
        state = cls.__new__(cls)
        state.run_id = str(snapshot["run_id"])
        state.ranking_metric = str(snapshot["ranking_metric"])
        state.larger_is_better = bool(snapshot["larger_is_better"])
        state.nodes = {}
        state._candidates = []
        state._lock = threading.RLock()
        state._save_path = Path(save_path) if save_path is not None else None
        state._nodes_path = state._save_path / "nodes.jsonl" if state._save_path else None
        state._result_path = state._save_path / "result.json" if state._save_path else None
        nodes = snapshot["nodes"]
        if not isinstance(nodes, list) or any(not isinstance(item, dict) for item in nodes):
            raise TypeError("Persisted search nodes must be a list of dictionaries")
        for item in nodes:
            coord = item["coord"]
            parents = tuple(
                ParentLink(
                    parent_node_id=str(parent["node_id"]),
                    relation=parent["relation"],
                )
                for parent in item["parents"]
            )
            node = SearchNode(
                run_id=str(item["run_id"]),
                node_id=str(item["node_id"]),
                node_label=str(item["node_label"]),
                coordinate=SearchCoordinate(
                    R=int(coord["R"]),
                    C=int(coord["C"]),
                    L=int(coord["L"]),
                    K=int(coord["K"]),
                ),
                parents=parents,
                created_at=str(item["created_at"]),
                core=dict(item["core"]),
                detail=dict(item["detail"]),
            )
            state.nodes[node.node_id] = node
        candidates = snapshot["candidates"]
        if not isinstance(candidates, list) or any(not isinstance(item, dict) for item in candidates):
            raise TypeError("Persisted candidates must be a list of dictionaries")
        state._candidates = [
            CandidateRecord(
                formula=str(item["formula"]),
                node_id=str(item["node_id"]),
                details=dict(item["details"]),
            )
            for item in candidates
        ]
        return state

    def node_record(self, node_id: str) -> dict[str, Any] | None:
        """Look up and serialize a single search node by its ``node_id`` (including full details).

        Args:
            node_id: Unique node identifier to look up.

        Returns:
            dict[str, Any] | None: Serialized node dictionary, or ``None`` if not found.
        """
        with self._lock:
            node = self.nodes.get(node_id)
        return node.to_dict() if node is not None else None

    def _candidate_priority(self, candidate: CandidateRecord) -> tuple[float, float] | None:
        validation = candidate.metric(self.ranking_metric, "validation")
        metric = validation if validation is not None else candidate.metric(
            self.ranking_metric, "train"
        )
        try:
            metric = float(metric)
            complexity = float(candidate.complexity)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(metric) or not math.isfinite(complexity):
            return None
        return (-metric if self.larger_is_better else metric, complexity)

    @staticmethod
    def _build_core(content, tool_calls, results, message) -> dict[str, Any]:
        best_record = None
        is_candidate = False
        for tool_call, call_result in zip(tool_calls, results):
            if not call_result.ok:
                continue
            split_results = call_result.result.get("data_split_results", {})
            split_name = "validation" if "validation" in split_results else "train"
            metrics = split_results.get(split_name, {}).get("metrics")
            if metrics is None:
                continue
            record = {
                "formula": call_result.result.get("formula"),
                "split": split_name,
                "rmse": metrics.get("rmse"),
                "mse": metrics.get("mse"),
                "mae": metrics.get("mae"),
                "r2": metrics.get("r2"),
            }
            if (
                best_record is None
                or SearchRunState._score_key(record)
                < SearchRunState._score_key(best_record)
            ):
                best_record = record
            is_candidate = is_candidate or bool(call_result.result.get("is_candidate"))
        return {
            "formula": best_record.pop("formula") if best_record else None,
            "score": best_record,
            "is_candidate": is_candidate,
            "tool_names": [tool_call.name for tool_call in tool_calls],
            "tool_count": len(tool_calls),
            "content_preview": SearchRunState._build_preview(content, tool_calls, message),
        }

    @staticmethod
    def _score_key(record: dict[str, Any]) -> float:
        try:
            score = float(record.get("mse"))
        except (TypeError, ValueError):
            return float("inf")
        return score if math.isfinite(score) else float("inf")

    @staticmethod
    def _build_preview(content, tool_calls, message, max_param_length: int = 240) -> str:
        parts = []
        if not isinstance(message, dict):
            reason = ""
        elif message.get("reasoning"):
            reason = str(message["reasoning"])
        elif isinstance(details := message.get("reasoning_details"), list):
            reason = "\n".join(
                str(item.get("text"))
                for item in details
                if isinstance(item, dict) and item.get("text")
            )
        else:
            reason = ""
        if reason:
            parts.append(f"Reason:\n{reason.strip()}")
        if content:
            parts.append(f"Content:\n{content.strip()}")
        if tool_calls:
            lines = []
            for index, tool_call in enumerate(tool_calls, 1):
                params = SearchRunState._truncate(tool_call.params or {}, max_param_length)
                lines.append(
                    f"{index:02d}. {tool_call.name}({json.dumps(params, ensure_ascii=False)})"
                )
            parts.append("Tool Calls:\n" + "\n".join(lines))
        return "\n\n".join(parts)

    @staticmethod
    def _truncate(value: Any, max_length: int) -> Any:
        if isinstance(value, str):
            return value if len(value) <= max_length else value[:max_length] + "...<truncated>"
        if isinstance(value, list):
            return [SearchRunState._truncate(item, max_length) for item in value]
        if isinstance(value, dict):
            return {
                key: SearchRunState._truncate(item, max_length)
                for key, item in value.items()
            }
        return value

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(json_value(value), ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
