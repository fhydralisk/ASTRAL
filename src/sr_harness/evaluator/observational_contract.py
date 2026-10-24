"""Executable handoff checks, independent of any particular scientific law."""
from __future__ import annotations
import json
import numpy as np


def audit_contract(contract, data):
    """Check declared roles and aligned development metadata; never infer science cuts."""
    errors = []
    if not isinstance(contract, dict):
        return {"valid": False, "errors": ["contract must be an object"]}
    if contract.get("version") != 1:
        errors.append("contract version must be 1")
    task = contract.get("task_type")
    if task not in {"regression", "binned_distribution", "unbinned_distribution"}:
        errors.append("task_type must be regression, binned_distribution or unbinned_distribution")
    target = contract.get("target")
    features = contract.get("features")
    if not isinstance(target, str) or target not in data:
        errors.append("target must be an actual array name")
    if not isinstance(features, list) or not all(isinstance(x, str) for x in features):
        errors.append("features must be a list of actual array names")
        features = []
    if len(features) != len(set(features)):
        errors.append("duplicate features")
    if target in features:
        errors.append("target cannot also be a feature")
    roles = contract.get("roles", {})
    if not isinstance(roles, dict):
        roles = {}
        errors.append("roles must be an object")
    allowed = {"target", "predictor", "coordinate", "identifier", "group", "uncertainty", "split", "diagnostic", "definition_component"}
    for name, role in roles.items():
        if name not in data or not isinstance(role, str) or role not in allowed:
            errors.append(f"invalid role or missing array: {name}")
    for name in features:
        if name not in data or roles.get(name) not in {"predictor", "coordinate"}:
            errors.append(f"ineligible predictor: {name}")
    if isinstance(target, str) and roles.get(target) != "target":
        errors.append("target must have target role")
    required = [target, *features]
    for key in ("group", "split", "uncertainty", "source_id"):
        name = contract.get(key)
        if name is not None:
            if not isinstance(name, str) or name not in data:
                errors.append(f"{key} must name an existing array")
            else:
                required.append(name)
    if isinstance(target, str) and target in data:
        shape = np.asarray(data[target]).shape
        if len(shape) != 1 or not shape[0]:
            errors.append("handoff currently requires nonempty one-dimensional tables")
        for name in required:
            if isinstance(name, str) and name in data and np.asarray(data[name]).shape != shape:
                errors.append(f"unaligned array: {name}")
    for key in ("target", "uncertainty"):
        name = contract.get(key)
        if isinstance(name, str) and name in data:
            values = np.asarray(data[name])
            if values.dtype.kind not in "fiu" or not np.isfinite(values).all():
                errors.append(f"{key} must contain finite numeric values")
            elif key == "uncertainty" and np.any(values <= 0):
                errors.append("uncertainty must be strictly positive")
    split_name, group_name = contract.get("split"), contract.get("group")
    if isinstance(split_name, str) and split_name in data:
        split = np.asarray(data[split_name])
        if split.ndim == 1:
            labels = set(split.tolist())
            if labels != {"train", "validation"}:
                errors.append("development split must contain exactly train and validation; seal external data separately")
            if isinstance(group_name, str) and group_name in data:
                groups = np.asarray(data[group_name])
                if groups.shape == split.shape:
                    overlap = set(groups[split == "train"].tolist()) & set(groups[split == "validation"].tolist())
                    if overlap:
                        errors.append(f"group leakage: {len(overlap)} groups cross train/validation")
    if task in {"binned_distribution", "unbinned_distribution"}:
        if not contract.get("measure") or not contract.get("support"):
            errors.append("distribution tasks require measure and support (including selection/completeness limits)")
        if contract.get("objective") not in {"poisson_deviance", "negative_log_likelihood"}:
            errors.append("distribution task requires count/likelihood objective, not pointwise MSE")
    if not isinstance(contract.get("selection"), dict):
        errors.append("selection must record rules, counts and response-dependent cuts")
    return {"valid": not errors, "errors": errors,
            "scope": "Declared array/role/split consistency only; does not certify physical selection or evaluator semantics."}


def read_contract(workspace):
    """Read an optional versioned contract through the workspace boundary."""
    if workspace is None or not (workspace.path / "discovery_contract.json").exists():
        return None
    with workspace.safe_open(workspace.path / "discovery_contract.json", "r") as stream:
        contract = json.load(stream)
    if not isinstance(contract, dict) or contract.get("version") != 1:
        raise ValueError("discovery_contract.json requires version 1")
    return contract


def candidate_role_errors(contract, variables, target):
    """Exclude undeclared inputs and bookkeeping coordinates from discovery ranking."""
    if contract is None:
        return []
    if contract.get("target") != target:
        return ["selected target differs from discovery contract; repair the handoff"]
    roles = contract.get("roles", {})
    allowed = {n for n in contract.get("features", []) if roles.get(n) in {"predictor", "coordinate"}}
    # A density is a function of the measured variate itself, not a predictor
    # of its value. Only an explicitly declared unbinned task permits this.
    if contract.get("task_type") == "unbinned_distribution":
        allowed.add(target)
    forbidden = set(variables) - allowed
    return [f"inputs outside declared scientific predictors: {sorted(forbidden)}"] if forbidden else []


def audit_evaluator_splits(contract, data, splits):
    """Compare actual split contents to frozen rows, in source order.

    Order is deliberately part of this contract, making alignment of separately
    loaded uncertainties/covariates testable. Identical predictor/target rows
    cannot prove identity without preserved source IDs; report this limitation.
    """
    errors = []
    name = contract.get("split")
    if name is None:
        return {"valid": True, "errors": [], "checked": False}
    if name not in data:
        return {"valid": False, "errors": ["missing declared split array"], "checked": False}
    partition = np.asarray(data[name])
    for label in ("train", "validation"):
        actual = splits[label].data
        for variable in [contract["target"], *contract["features"]]:
            expected = np.asarray(data[variable])[partition == label]
            if variable not in actual or not np.array_equal(actual[variable], expected):
                errors.append(f"{label}/{variable}: evaluator does not use the declared rows in source order")
    return {"valid": not errors, "errors": errors, "checked": True,
            "limitation": "Matches scientific array contents; duplicate identical rows require independent source-ID checks."}


def require_search_objective(contract, ranking_metric):
    """Prevent distribution tasks silently starting with regression ranking."""
    if contract and contract.get("task_type") in {"binned_distribution", "unbinned_distribution"}:
        objective = contract.get("objective")
        if objective not in {"poisson_deviance", "negative_log_likelihood"} or ranking_metric != objective:
            raise ValueError(
                "Distribution discovery requires an installed/tested likelihood evaluator "
                f"and ranking_metric={objective!r}; current ranking_metric={ranking_metric!r}. "
                "Return to evaluator construction; do not substitute pointwise regression."
            )


def require_active_handoff(context):
    """Fail before SR search if the installed evaluator ignores a frozen split."""
    contract = read_contract(context.workspace)
    require_search_ready(contract)
    if contract is None:
        return
    from ..core.context_data import load_context_data
    loaded = load_context_data(context.workspace.path / "context.data", workspace=context.workspace)
    report = audit_contract(contract, loaded["data"])
    if contract.get("target") != context.target:
        report["errors"].append("selected target differs from discovery contract")
        report["valid"] = False
    if report["valid"]:
        report = audit_evaluator_splits(contract, loaded["data"], context._splits())
    if not report["valid"]:
        raise ValueError("Scientific handoff failed before search: " + "; ".join(report["errors"]))


def require_search_ready(contract):
    """Keep an auxiliary/derived table from masquerading as the requested discovery."""
    if not contract:
        return
    status = contract.get('replication_status', 'ready')
    if status != 'ready':
        reasons = contract.get('blocked_reason', ['Required scientific measurements are unavailable'])
        if isinstance(reasons, list):
            reasons = '; '.join(str(x) for x in reasons)
        raise ValueError(f"Scientific search is not ready ({status}): {reasons}. "
                         "Resolve the measurement requirements or explicitly define a supported auxiliary task; do not substitute a different discovery target.")
