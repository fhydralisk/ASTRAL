from .models import (
    AgentMessage,
    AgentSettings,
    DataSelection,
    Demo,
    Descriptions,
    DiscoveryTask,
    EvaluatorConfiguration,
    Heatmap,
    SearchSettings,
    SearchStart,
    WorkspaceLock,
    WorkspaceMove,
    WorkspacePath,
)
from fastapi import Body, Header
from .app import SessionStatus, AsyncOperation, EventBatch


def mount(app, invoke):
    @app.get("/v1/sessions/{session_id}", operation_id="status", response_model=SessionStatus)
    async def status(session_id: str):
        return await invoke(session_id, "status", {}, None)

    @app.get("/v1/sessions/{session_id}/capabilities", operation_id="capabilities")
    async def capabilities(session_id: str, agent: str = "search"):
        return await invoke(session_id, "capabilities", {"agent": agent}, None)

    @app.post(
        "/v1/sessions/{session_id}/start",
        operation_id="start",
        status_code=202,
        response_model=AsyncOperation,
    )
    async def start(
        session_id: str,
        payload: SearchStart = Body(...),
        idempotency_key: str = Header(min_length=1, max_length=200),
    ):
        return await invoke(session_id, "start", {"payload": payload}, idempotency_key)

    @app.post(
        "/v1/sessions/{session_id}/data/agent",
        operation_id="prepare_data",
        status_code=202,
        response_model=AsyncOperation,
    )
    async def prepare_data(
        session_id: str,
        payload: AgentMessage = Body(...),
        idempotency_key: str = Header(min_length=1, max_length=200),
    ):
        return await invoke(session_id, "prepare_data", {"payload": payload}, idempotency_key)

    @app.get(
        "/v1/sessions/{session_id}/data/agent/events",
        operation_id="data_agent_events",
        response_model=EventBatch,
    )
    async def data_agent_events(session_id: str, after_seq: int = 0):
        return await invoke(session_id, "data_agent_events", {"after_seq": after_seq}, None)

    @app.post("/v1/sessions/{session_id}/data/agent/stop", operation_id="stop_data_preparation")
    async def stop_data_preparation(session_id: str):
        return await invoke(session_id, "stop_data_preparation", {}, None)

    @app.put("/v1/sessions/{session_id}/data/agent/settings", operation_id="configure_data_agent")
    async def configure_data_agent(session_id: str, payload: AgentSettings = Body(...)):
        return await invoke(session_id, "configure_data_agent", {"payload": payload}, None)

    @app.post("/v1/sessions/{session_id}/data/agent/test", operation_id="test_data_agent_model")
    async def test_data_agent_model(session_id: str, payload: AgentSettings = Body(...)):
        return await invoke(session_id, "test_data_agent_model", {"payload": payload}, None)

    @app.post("/v1/sessions/{session_id}/test", operation_id="test_model")
    async def test_model(session_id: str, payload: SearchSettings = Body(...)):
        return await invoke(session_id, "test_model", {"payload": payload}, None)

    @app.get("/v1/sessions/{session_id}/evaluator", operation_id="evaluator_configuration")
    async def evaluator_configuration(session_id: str, selected: str | None = None):
        return await invoke(session_id, "evaluator_configuration", {"selected": selected}, None)

    @app.put("/v1/sessions/{session_id}/evaluator", operation_id="configure_evaluator")
    async def configure_evaluator(session_id: str, payload: EvaluatorConfiguration = Body(...)):
        return await invoke(session_id, "configure_evaluator", {"payload": payload}, None)

    @app.post("/v1/sessions/{session_id}/evaluator/test", operation_id="test_evaluator")
    async def test_evaluator(session_id: str, payload: EvaluatorConfiguration = Body(...)):
        return await invoke(session_id, "test_evaluator", {"payload": payload}, None)

    @app.post(
        "/v1/sessions/{session_id}/evaluator/agent/start",
        operation_id="start_evaluator_assistance",
        status_code=202,
        response_model=AsyncOperation,
    )
    async def start_evaluator_assistance(
        session_id: str,
        payload: AgentMessage = Body(...),
        idempotency_key: str = Header(min_length=1, max_length=200),
    ):
        return await invoke(
            session_id, "start_evaluator_assistance", {"payload": payload}, idempotency_key
        )

    @app.get(
        "/v1/sessions/{session_id}/evaluator/agent/events",
        operation_id="evaluator_agent_events",
        response_model=EventBatch,
    )
    async def evaluator_agent_events(session_id: str, after_seq: int = 0):
        return await invoke(session_id, "evaluator_agent_events", {"after_seq": after_seq}, None)

    @app.post(
        "/v1/sessions/{session_id}/evaluator/agent/stop", operation_id="stop_evaluator_assistance"
    )
    async def stop_evaluator_assistance(session_id: str):
        return await invoke(session_id, "stop_evaluator_assistance", {}, None)

    @app.put(
        "/v1/sessions/{session_id}/evaluator/agent/settings",
        operation_id="configure_evaluator_agent",
    )
    async def configure_evaluator_agent(session_id: str, payload: AgentSettings = Body(...)):
        return await invoke(session_id, "configure_evaluator_agent", {"payload": payload}, None)

    @app.post(
        "/v1/sessions/{session_id}/evaluator/agent/test", operation_id="test_evaluator_agent_model"
    )
    async def test_evaluator_agent_model(session_id: str, payload: AgentSettings = Body(...)):
        return await invoke(session_id, "test_evaluator_agent_model", {"payload": payload}, None)

    @app.get("/v1/sessions/{session_id}/data/context", operation_id="data_context")
    async def data_context(session_id: str, rows: int = 300):
        return await invoke(session_id, "data_context", {"rows": rows}, None)

    @app.get("/v1/sessions/{session_id}/data/context/preview", operation_id="data_context_preview")
    async def data_context_preview(session_id: str, group: str, limit: int = 100):
        return await invoke(
            session_id, "data_context_preview", {"group": group, "limit": limit}, None
        )

    @app.get("/v1/sessions/{session_id}/data/context/plot", operation_id="data_context_plot")
    async def data_context_plot(
        session_id: str,
        x: str,
        y: str,
        hue: str | None = None,
        size: str | None = None,
        limit: int = 2000,
    ):
        return await invoke(
            session_id,
            "data_context_plot",
            {"x": x, "y": y, "hue": hue, "size": size, "limit": limit},
            None,
        )

    @app.post("/v1/sessions/{session_id}/data/context/heatmap", operation_id="data_context_heatmap")
    async def data_context_heatmap(session_id: str, payload: Heatmap = Body(...)):
        return await invoke(session_id, "data_context_heatmap", {"payload": payload}, None)

    @app.post("/v1/sessions/{session_id}/data/context/reload", operation_id="reload_data_context")
    async def reload_data_context(session_id: str):
        return await invoke(session_id, "reload_data_context", {}, None)

    @app.put("/v1/sessions/{session_id}/data/selection", operation_id="update_data_selection")
    async def update_data_selection(session_id: str, payload: DataSelection = Body(...)):
        return await invoke(session_id, "update_data_selection", {"payload": payload}, None)

    @app.put("/v1/sessions/{session_id}/data/descriptions", operation_id="update_data_descriptions")
    async def update_data_descriptions(session_id: str, payload: Descriptions = Body(...)):
        return await invoke(session_id, "update_data_descriptions", {"payload": payload}, None)

    @app.post("/v1/sessions/{session_id}/settings", operation_id="settings")
    async def settings(session_id: str, payload: SearchSettings = Body(...)):
        return await invoke(session_id, "settings", {"payload": payload}, None)

    @app.get("/v1/sessions/{session_id}/workspace", operation_id="files")
    async def files(session_id: str, path: str = "", recursive: bool = False):
        return await invoke(session_id, "files", {"path": path, "recursive": recursive}, None)

    @app.get("/v1/sessions/{session_id}/workspace/size", operation_id="workspace_item_size")
    async def workspace_item_size(session_id: str, path: str):
        return await invoke(session_id, "workspace_item_size", {"path": path}, None)

    @app.get("/v1/sessions/{session_id}/workspace/download", operation_id="download")
    async def download(session_id: str, path: str):
        return await invoke(session_id, "download", {"path": path}, None)

    @app.get("/v1/sessions/{session_id}/workspace/preview", operation_id="preview")
    async def preview(session_id: str, path: str):
        return await invoke(session_id, "preview", {"path": path}, None)

    @app.post("/v1/sessions/{session_id}/workspace/directory", operation_id="create_directory")
    async def create_directory(session_id: str, payload: WorkspacePath = Body(...)):
        return await invoke(session_id, "create_directory", {"payload": payload}, None)

    @app.put("/v1/sessions/{session_id}/workspace/lock", operation_id="set_workspace_item_lock")
    async def set_workspace_item_lock(session_id: str, payload: WorkspaceLock = Body(...)):
        return await invoke(session_id, "set_workspace_item_lock", {"payload": payload}, None)

    @app.patch("/v1/sessions/{session_id}/workspace", operation_id="move_workspace_item")
    async def move_workspace_item(session_id: str, payload: WorkspaceMove = Body(...)):
        return await invoke(session_id, "move_workspace_item", {"payload": payload}, None)

    @app.delete("/v1/sessions/{session_id}/workspace", operation_id="delete_workspace_item")
    async def delete_workspace_item(session_id: str, path: str):
        return await invoke(session_id, "delete_workspace_item", {"path": path}, None)

    @app.get("/v1/sessions/{session_id}/data/csv-files", operation_id="csv_files")
    async def csv_files(session_id: str):
        return await invoke(session_id, "csv_files", {}, None)

    @app.get("/v1/sessions/{session_id}/data/preview", operation_id="data_preview")
    async def data_preview(session_id: str, path: str, rows: int = 300):
        return await invoke(session_id, "data_preview", {"path": path, "rows": rows}, None)

    @app.get("/v1/sessions/{session_id}/data/discovery-tasks", operation_id="discovery_tasks")
    async def discovery_tasks(session_id: str):
        return await invoke(session_id, "discovery_tasks", {}, None)

    @app.post(
        "/v1/sessions/{session_id}/data/discovery-tasks/load", operation_id="load_discovery_task"
    )
    async def load_discovery_task(session_id: str, payload: DiscoveryTask = Body(...)):
        return await invoke(session_id, "load_discovery_task", {"payload": payload}, None)

    @app.post("/v1/sessions/{session_id}/data/demo", operation_id="create_demo")
    async def create_demo(session_id: str, payload: Demo | None = Body(default=None)):
        return await invoke(session_id, "create_demo", {"payload": payload}, None)

    @app.post("/v1/sessions/{session_id}/data/prompts", operation_id="initial_prompts")
    async def initial_prompts(session_id: str, payload: SearchStart = Body(...)):
        return await invoke(session_id, "initial_prompts", {"payload": payload}, None)
