"""Ephemeral credentials, isolated per agent and excluded from serialization."""


class StrictEnvironment(dict):
    strict = True


def agent_environment(context, role):
    args = getattr(context, "args", None)
    environments = getattr(args, "agent_environments", None)
    if environments is not None:
        return environments[role]
    return getattr(args, "api_environment", None)


def tool_environment(tool):
    """Keep nested model calls in the calling agent's credential scope."""
    return agent_environment(getattr(tool, "context", None), getattr(tool, "agent_role", "search"))
