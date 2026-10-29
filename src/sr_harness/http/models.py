"""Scientific command payloads, shared by OpenAPI and HTTP validation."""

from pydantic import BaseModel, ConfigDict, Field


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AgentSettings(Payload):
    llm_provider: str | None = None
    llm_model: str | None = None
    tool_parser: str | None = None
    llm_max_tokens: int | None = None
    tools: list[str] | None = None
    skills: list[str] | None = None
    proxy: str | None = None
    max_steps: int | None = None


class SearchSettings(AgentSettings):
    strong_llm_provider: str | None = None
    strong_llm_model: str | None = None
    auto_routing: bool | None = None
    local_sample_size: int | None = None
    max_refinement_depth: int | None = None
    global_width: int | None = None
    max_restart_loop: int | None = None
    restart_top_k: int | None = None
    max_workers: int | None = None
    validation_fraction: float | None = None
    split_by: str | None = None
    split_ood_variable: str | None = None
    split_random_state: int | None = None
    ranking_metric: str | None = None
    larger_is_better: bool | None = None
    force_initial_diagnostics: bool | None = None
    pause_on_truncated_response: bool | None = None
    tool_free_stop_review_rounds: int | None = None
    stop_guard_mode: str | None = None
    stop_guard_metric: str | None = None
    stop_guard_threshold: float | None = None
    stop_guard_split: str | None = None
    stop_guard_larger_is_better: bool | None = None


class SearchStart(SearchSettings):
    problem_description: str | None = None
    prompt: str | None = None
    system_prompt: str | None = None
    user_prompt: str | None = None
    target: str | None = None
    features: list[str] | None = None
    variable_descriptions: dict[str, str] | None = None
    idempotency_key: str | None = None


class AgentMessage(Payload):
    message: str = Field(min_length=1)


class EvaluatorConfiguration(Payload):
    selected: str | None = None
    source: str | None = None
    formula: str | None = None
    validation_fraction: float | None = None
    split_by: str | None = None
    split_ood_variable: str | None = None
    split_random_state: int | None = None
    ranking_metric: str | None = None
    larger_is_better: bool | None = None


class Heatmap(Payload):
    row: list[str] = Field(default_factory=list)
    column: list[str] = Field(default_factory=list)
    color: str = ""
    z: str = ""
    z_index: int = 0


class Descriptions(Payload):
    variable_descriptions: dict[str, str] = Field(default_factory=dict)


class DataSelection(Descriptions):
    target: str
    features: list[str]


class WorkspacePath(Payload):
    path: str = Field(min_length=1)


class WorkspaceLock(WorkspacePath):
    locked: bool


class WorkspaceMove(Payload):
    source: str = Field(min_length=1)
    destination: str = Field(min_length=1)


class DiscoveryTask(Payload):
    name: str = Field(min_length=1)


class Demo(Payload):
    kind: str = "polynomial"
