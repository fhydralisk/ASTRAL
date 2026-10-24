"""Shared runtime context for agents, evaluators, and tools."""
from __future__ import annotations

import argparse
import threading
from typing import TYPE_CHECKING, Any
import numpy as np

if TYPE_CHECKING:
    from ..evaluator import DefaultEvaluator
    from ..runtime.workspace import Workspace

_DEFAULT_EVALUATOR = object()


class AgentContext:
    """Authoritative runtime context shared across agents, evaluators, and tools.

    Holds the active dataset arrays (``data``), variable and axis metadata,
    selected ``target`` and feature names, the active
    :class:`~sr_harness.evaluator.DefaultEvaluator`, the conversation
    :class:`~sr_harness.runtime.Workspace`, and cached training/validation views.

    Args:
        args: Runtime configuration namespace shared by agents, evaluators, and tools.
        data: Mapping of variable and axis names to NumPy arrays.
        target: Name of the active dependent variable, if selected.
        variable_descriptions: Human-readable descriptions keyed by variable or axis name.
        variable_axes: Mapping from each variable name to its tuple of axis names.
        variable_structures: Mapping from edge-aligned variable names to their relation name.
        relation_names: Set of variable names representing graph or hypergraph edge tables.
        num_nodes: Total node count when graph or hypergraph relations are present.
        evaluator: Evaluator instance used for splitting, parameter fitting, and scoring.
        workspace: Optional managed workspace accessible to workspace-aware tools.
    """

    def __init__(self, *, args: argparse.Namespace | None = None, data: dict[str, Any] | None = None, target: str | None = None, variable_descriptions: dict[str, str] | None = None, variable_axes: dict[str, tuple[str, ...]] | None = None, variable_structures: dict[str, str] | None = None, relation_names: set[str] | None = None, num_nodes: int | None = None, evaluator: DefaultEvaluator | object = _DEFAULT_EVALUATOR, workspace: Workspace | None = None) -> None:
        """Initialize an agent runtime context.

        Args:
            args: Runtime configuration namespace.
            data: Mapping of variable and axis names to NumPy arrays.
            target: Name of the active target variable.
            variable_descriptions: Descriptions keyed by variable or axis name.
            variable_axes: Axis tuples keyed by variable name.
            variable_structures: Relation variable names keyed by edge-aligned variable name.
            relation_names: Names of graph or hypergraph relation variables.
            num_nodes: Node count for relational datasets.
            evaluator: Active formula evaluator instance.
            workspace: Optional managed workspace instance.
        """
        if args is not None and not isinstance(args, argparse.Namespace):
            raise TypeError("args must be an argparse.Namespace")
        self.args = args if args is not None else argparse.Namespace()
        defaults = {
            "validation_fraction": 0.0,
            "split_by": "random",
            "split_random_state": 42,
            "split_ood_variable": None,
            "data_revision": 0,
        }
        for name, value in defaults.items():
            if not hasattr(self.args, name):
                setattr(self.args, name, value)
        self.workspace = workspace
        if any(not isinstance(name, str) or not name for name in (data or {})):
            raise TypeError("data keys must be non-empty strings")
        self.data = {name: np.asarray(value) for name, value in (data or {}).items()}
        self.target = target
        if variable_descriptions is None:
            self.variable_descriptions = {name: "" for name in self.data}
        else:
            self.variable_descriptions = dict(variable_descriptions)
        if variable_axes is None:
            self.variable_axes = {name: () for name in self.data}
        else:
            self.variable_axes = {name: tuple(axes) for name, axes in variable_axes.items()}
        self.variable_structures = dict(variable_structures or {})
        self.relation_names = set(relation_names or self.variable_structures.values())
        self.num_nodes = num_nodes
        from ..evaluator import DefaultEvaluator, GraphEvaluator
        if evaluator is _DEFAULT_EVALUATOR:
            evaluator = GraphEvaluator() if self.relation_names else DefaultEvaluator()
        if not isinstance(evaluator, DefaultEvaluator):
            raise TypeError("evaluator must be a DefaultEvaluator instance")
        self.evaluator: DefaultEvaluator = evaluator
        self._split_cache: dict[str, AgentContext] | None = None
        self._lock = threading.RLock()
        self._validate(allow_incomplete=not self.data or self.target is None)

    def _validate(self, *, allow_incomplete: bool = False) -> None:
        names = set(self.data)
        if not allow_incomplete and self.target not in names:
            raise ValueError("target must name an entry in data")
        if set(self.variable_descriptions) != names:
            raise ValueError("variable_descriptions keys must equal data keys")
        if any(not isinstance(value, str) for value in self.variable_descriptions.values()):
            raise TypeError("variable descriptions must be strings")
        if any(
            not isinstance(axis, str) or not axis
            for dimensions in self.variable_axes.values()
            for axis in dimensions
        ):
            raise TypeError("variable_axes values must contain non-empty axis names")
        non_axes = set(self.variable_axes)
        axes = {axis for dimensions in self.variable_axes.values() for axis in dimensions}
        if non_axes & axes or non_axes | axes != names:
            raise ValueError("variable_axes keys and values must partition data keys")
        for axis in axes:
            if self.data[axis].ndim != 1:
                raise ValueError(f"axis variable {axis!r} must be one-dimensional")
        if (self.num_nodes is None) != (not self.relation_names):
            raise ValueError("relation_names and num_nodes must appear together")
        if self.num_nodes is not None and (
            isinstance(self.num_nodes, bool)
            or not isinstance(self.num_nodes, int)
            or self.num_nodes < 1
        ):
            raise ValueError("num_nodes must be a positive integer")
        for relation_name in self.relation_names:
            if relation_name not in names:
                raise ValueError("relation_names must reference entries in data")
            relation = self.data[relation_name]
            if relation.ndim != 2 or relation.shape[1] not in {2, 3}:
                raise ValueError(f"relation variable {relation_name!r} must have shape (E, 2) or (H, 3)")
            if relation.dtype.kind not in "iu":
                raise ValueError(f"relation variable {relation_name!r} must contain integer endpoints")
            if np.any(relation < 0) or np.any(relation >= self.num_nodes):
                raise ValueError(f"relation variable {relation_name!r} endpoints must be in [0, {self.num_nodes})")
        for variable, structure in self.variable_structures.items():
            if variable not in names or structure not in names:
                raise ValueError("variable_structures must reference entries in data")
            if variable == structure:
                raise ValueError("a structured variable cannot reference itself")
            if structure not in self.relation_names:
                raise ValueError("variable_structures values must name relation variables")
            relation = self.data[structure]
            if relation.ndim != 2 or relation.shape[1] not in {2, 3}:
                raise ValueError(f"structure variable {structure!r} must have shape (E, 2) or (H, 3)")
            if self.data[variable].ndim == 0 or self.data[variable].shape[-1] != relation.shape[0]:
                raise ValueError(f"structured variable {variable!r} must end in the relation dimension")
            if relation.dtype.kind not in "iu":
                raise ValueError(f"structure variable {structure!r} must contain integer endpoints")
            if np.any(relation < 0) or np.any(relation >= self.num_nodes):
                raise ValueError(f"structure variable {structure!r} endpoints must be in [0, {self.num_nodes})")

    def invalidate_splits(self) -> None:
        """Clear cached training and validation context splits so they are recomputed on next access."""
        with self._lock:
            self._split_cache = None

    def _sync_builtin_evaluator(self) -> None:
        from ..evaluator import DefaultEvaluator, GraphEvaluator
        if type(self.evaluator) not in {DefaultEvaluator, GraphEvaluator}:
            return
        self.evaluator = GraphEvaluator() if self.relation_names else DefaultEvaluator()

    def _splits(self) -> dict[str, AgentContext]:
        with self._lock:
            if self.target is None:
                raise ValueError("target must be configured before splitting AgentContext")
            if self._split_cache is None:
                splits = self.evaluator.split(self)
                if set(splits) != {"train", "validation"}:
                    raise ValueError("DefaultEvaluator.split() must return train and validation contexts")
                if any(not isinstance(split, AgentContext) for split in splits.values()):
                    raise TypeError("DefaultEvaluator.split() values must be AgentContext instances")
                self._split_cache = splits
            return self._split_cache

    def with_data(self, data: dict[str, np.ndarray]) -> AgentContext:
        """Create a lightweight view over ``data`` that shares runtime arguments and metadata with this context.

        Args:
            data: Replacement mapping of variable and axis arrays.

        Returns:
            AgentContext: New context view bound to ``data``.
        """
        return AgentContext(
            args=self.args, data=data, target=self.target,
            variable_descriptions={name: self.variable_descriptions[name] for name in data},
            variable_axes={name: axes for name, axes in self.variable_axes.items() if name in data},
            variable_structures={name: structure for name, structure in self.variable_structures.items() if name in data and structure in data},
            relation_names=self.relation_names & set(data),
            num_nodes=self.num_nodes, evaluator=self.evaluator, workspace=self.workspace,
        )

    @property
    def train_split(self) -> AgentContext:
        """Return the cached training split context, calling ``evaluator.split(self)`` on first access.

        Returns:
            AgentContext: Context view containing the training split arrays.
        """
        return self._splits()["train"]

    @property
    def validation_split(self) -> AgentContext:
        """Return the cached validation split context, calling ``evaluator.split(self)`` on first access.

        Returns:
            AgentContext: Context view containing the validation split arrays.
        """
        return self._splits()["validation"]

    def axis_names(self) -> tuple[str, ...]:
        """Return all coordinate axis names referenced by variables in first-appearance order.

        Returns:
            tuple[str, ...]: Ordered axis names.
        """
        return tuple(dict.fromkeys(axis for axes in self.variable_axes.values() for axis in axes))

    def variable_names(self) -> tuple[str, ...]:
        """Return all non-axis variable names in manifest order.

        Returns:
            tuple[str, ...]: Ordered variable names.
        """
        return tuple(self.variable_axes)

    def feature_names(self) -> tuple[str, ...]:
        """Return selected input feature names (excluding axes and the active target).

        Returns:
            tuple[str, ...]: Active feature variable names.
        """
        return tuple(name for name in self.variable_axes if name != self.target)

    def commit_context_data(self, loaded: dict[str, Any]) -> dict[str, Any]:
        """Replace the live dataset with a validated ``load_context_data()`` bundle and increment ``data_revision``.

        Args:
            loaded: Validated dataset dictionary returned by :func:`load_context_data`.

        Returns:
            dict[str, Any]: Summary containing the new ``revision``, ``variables``,
                ``axes``, ``relation_names``, and ``num_nodes``.
        """
        values = {str(name): np.asarray(value) for name, value in loaded["data"].items()}
        self.data = values
        self.variable_descriptions = dict(loaded["variable_descriptions"])
        self.variable_axes = {
            name: tuple(axes) for name, axes in loaded["variable_axes"].items()
        }
        self.variable_structures = dict(loaded["variable_structures"])
        self.relation_names = set(loaded["relation_names"])
        self.num_nodes = loaded["num_nodes"]
        self._sync_builtin_evaluator()
        self.target = self.target if self.target in values else None
        self.invalidate_splits()
        self.args.data_revision += 1
        self._validate(allow_incomplete=True)
        return {"revision": self.args.data_revision, "variables": list(values)}

    def commit_data(self, data: dict[str, Any], *, target: str, features: list[str] | None = None, variable_descriptions: dict[str, str] | None = None) -> dict[str, Any]:
        """Commit aligned 1D/tabular arrays directly into the live context and increment ``data_revision``.

        Args:
            data: Mapping of column names to NumPy-compatible arrays.
            target: Name of the target variable to predict.
            features: Names of input feature variables to retain.
            variable_descriptions: Optional human-readable descriptions by column name.

        Returns:
            dict[str, Any]: Summary containing the new ``revision``, ``target``,
                ``features``, ``columns``, and ``rows``.
        """
        selected = list(dict.fromkeys([*(features or []), target]))
        if target not in data:
            raise ValueError(f"target column does not exist: {target}")
        arrays = {name: np.asarray(data[name]) for name in selected}
        with self._lock:
            self.data = arrays
            self.target = target
            self.variable_descriptions = {name: str((variable_descriptions or {}).get(name, "")) for name in arrays}
            self.variable_axes = {name: () for name in arrays}
            self.variable_structures = {}
            self.relation_names = set()
            self.num_nodes = None
            self._sync_builtin_evaluator()
            self.invalidate_splits()
            self.args.data_revision += 1
            self._validate()
        return {"revision": self.args.data_revision, "target": target, "features": list(self.feature_names()), "columns": list(arrays), "rows": len(arrays[target])}

    def add_features(self, features: dict[str, Any], *, descriptions: dict[str, str] | None = None) -> dict[str, Any]:
        """Append new sample-aligned feature arrays to the active dataset while keeping the current target.

        Args:
            features: Mapping of new feature names to aligned arrays.
            descriptions: Optional descriptions for the newly added features.

        Returns:
            dict[str, Any]: Updated commit summary after merging the new features.

        Raises:
            ValueError: If no target variable is currently configured or feature shapes do not align.
        """
        if self.target is None:
            raise ValueError("target must be configured before adding features")
        descriptions = self.variable_descriptions | {
            name: (descriptions or {}).get(name, "") for name in features
        }
        return self.commit_data(self.data | features, target=self.target, features=[*self.feature_names(), *features], variable_descriptions=descriptions)

    def update_selection(self, *, target: str, features: list[str], variable_descriptions: dict[str, str] | None = None) -> dict[str, Any]:
        """Update the active target, selected input features, and variable descriptions.

        Args:
            target: Name of the target variable.
            features: List of input feature variable names.
            variable_descriptions: Optional updated descriptions keyed by variable or axis name.

        Returns:
            dict[str, Any]: Summary with the incremented ``revision``, ``target``, and ``features``.
        """
        keep_variables = set(features) | {target}
        keep_axes = {axis for name, axes in self.variable_axes.items() if name in keep_variables for axis in axes}
        keep = keep_variables | keep_axes
        self.data = {name: value for name, value in self.data.items() if name in keep}
        self.target = target
        descriptions = self.variable_descriptions | dict(variable_descriptions or {})
        self.variable_descriptions = {name: descriptions.get(name, "") for name in self.data}
        self.variable_axes = {name: axes for name, axes in self.variable_axes.items() if name in keep_variables}
        self.variable_structures = {name: structure for name, structure in self.variable_structures.items() if name in self.data and structure in self.data}
        self.relation_names &= set(self.data)
        if not self.relation_names:
            self.num_nodes = None
        self._sync_builtin_evaluator()
        self.invalidate_splits()
        self.args.data_revision += 1
        self._validate()
        return {"revision": self.args.data_revision, "target": target, "features": list(self.feature_names()), "selection_changed": True}

    def schema(self) -> dict[str, Any]:
        """Return a JSON-serializable summary of variables, shapes, dtypes, axes, and roles in the context.

        Returns:
            dict[str, Any]: Schema dictionary suitable for WebUI previews and diagnostics.
        """
        axes = set(self.axis_names())
        return {
            "revision": self.args.data_revision, "num_nodes": self.num_nodes,
            "target": self.target, "features": list(self.feature_names()), "columns": list(self.data),
            "rows": len(self.data[self.target]) if self.target in self.data else 0,
            "variable_descriptions": dict(self.variable_descriptions),
            "variables": {name: {"shape": list(value.shape), "dtype": str(value.dtype), "axes": list(self.variable_axes.get(name, ())), "description": self.variable_descriptions[name], **({"kind": "relation"} if name in self.relation_names else {})} for name, value in self.data.items() if name not in axes},
            "axes": {name: {"size": len(self.data[name]), "dtype": str(self.data[name].dtype), "description": self.variable_descriptions[name]} for name in axes},
        }

    def __getstate__(self) -> dict[str, Any]:
        state = self.__dict__.copy()
        state.pop("_lock", None)
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.__dict__.update(state)
        self._lock = threading.RLock()

