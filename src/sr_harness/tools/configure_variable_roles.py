"""Inspect dataset variables and explicitly requested workbench role changes."""

from __future__ import annotations

from copy import copy
from typing import Any, Callable

from ..core import AgentContext, ToolMetadata, load_context_data
from .base_tool import BaseTool


def available_variable_context(context: AgentContext) -> AgentContext:
    """Read the full dataset, including variables omitted from the active selection."""
    workspace = context.workspace
    if workspace is None or not (workspace.path / "context.data/manifest.json").is_file():
        return AgentContext(
            args=copy(context.args), data=context.data, target=context.target,
            variable_descriptions=context.variable_descriptions,
            variable_axes=context.variable_axes,
            variable_structures=context.variable_structures,
            relation_names=context.relation_names, num_nodes=context.num_nodes,
            evaluator=context.evaluator, workspace=workspace,
        )
    loaded = load_context_data(workspace.path / "context.data", workspace=workspace)
    descriptions = loaded["variable_descriptions"] | context.variable_descriptions
    return AgentContext(
        args=copy(context.args), data=loaded["data"], target=context.target,
        variable_descriptions={name: descriptions[name] for name in loaded["data"]},
        variable_axes=loaded["variable_axes"],
        variable_structures=loaded["variable_structures"],
        relation_names=loaded["relation_names"], num_nodes=loaded["num_nodes"],
        evaluator=context.evaluator, workspace=workspace,
    )


@BaseTool.register("configure_variable_roles")
class VariableRolesTool(BaseTool):
    """Inspect variables; edit roles through the workbench only when explicitly requested."""

    metadata = ToolMetadata(name="configure_variable_roles")
    update_roles: Callable[..., dict[str, Any]] | None = None

    def execute(
        self,
        roles: dict[str, str] | None = None,
        user_request: str = "",
    ) -> dict[str, Any]:
        """List variable descriptions and roles, or apply an explicitly requested role change.

        Reading is always allowed. Only change roles when the user explicitly asks
        to select/configure variables; merely asking to build an evaluator is not
        authorization. Never select variables to improve a validation score.
        Unused variables remain in context.data on disk for later selection.

        Args:
            roles: Omit for read-only inspection. Otherwise map variable names to
                'feature', 'target', or 'unused'. Unmentioned roles are preserved;
                the resulting selection must have exactly one target. Axis
                coordinates are listed for reference, not assigned model roles.
            user_request: For edits, quote the user's explicit role-configuration
                request verbatim for the audit log; not needed for inspection.

        Returns:
            dict[str, Any]: Complete variable metadata, active selection, revision,
                and whether this call changed roles.
        """
        changed = False
        if roles is not None:
            if not isinstance(user_request, str) or not user_request.strip():
                raise ValueError("Role changes require the user's explicit request in user_request")
            if self.update_roles is None:
                raise ValueError("Variable roles can only be edited in the evaluator workbench")
            self.update_roles(roles=roles, user_request=user_request)
            changed = True
        available = available_variable_context(self.context)
        features = set(self.context.feature_names())
        variables = []
        for name, value in available.data.items():
            configurable = name in available.variable_axes
            role = "target" if name == self.context.target else "feature" if name in features else "unused"
            variables.append({
                "name": name, "description": available.variable_descriptions[name],
                "shape": list(value.shape), "dtype": str(value.dtype),
                "axes": list(available.variable_axes.get(name, ())),
                "kind": "variable" if configurable else "axis",
                "role": role, "configurable": configurable,
            })
        return {
            "changed": changed, "revision": self.context.args.data_revision,
            "target": self.context.target, "features": list(self.context.feature_names()),
            "variables": variables,
            **({"user_request": user_request} if changed else {}),
        }
