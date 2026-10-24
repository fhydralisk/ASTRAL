"""Single interactive run and observable hooks, without changing the search loop."""

from __future__ import annotations

import json
import ast
import logging
import os
import stat
import tempfile
import threading
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse

import numpy as np
from dotenv import dotenv_values, set_key, unset_key

from ..agents.data_preparation_agent import DataPreparationAgent
from ..agents.evaluator_construction_agent import EvaluatorConstructionAgent
from ..agents.sr_agent_interactive import SRAgentInteractive
from ..api import BaseAPI
from ..core import AgentContext, SearchRunState, json_value, load_context_data
from ..evaluator import GraphEvaluator, load_custom_evaluator
from ..evaluator.load_custom_evaluator import (
    BUILTIN_EVALUATOR_CLASS_NAMES,
    CUSTOM_TEMPLATE,
    create_builtin_evaluator,
    evaluator_catalog,
    evaluator_filename,
    evaluator_source,
)
from ..parser import BaseParser
from ..runtime import InteractionManager, ModelRouter, SRInteractionManager
from ..runtime.network import proxy_environment
from ..skills import SkillManager
from ..tools import BaseTool, ModelTestTool, ValidateEvaluatorTool
from ..runtime.workspace import Workspace
from .demo_data import build_demo


_logger = logging.getLogger(__name__)
RUNTIME_SETTING_NAMES = (
    "llm_provider",
    "llm_model",
    "strong_llm_provider",
    "strong_llm_model",
    "auto_routing",
    "tool_parser",
    "llm_max_tokens",
    "tools",
    "skills",
    "local_sample_size",
    "max_refinement_depth",
    "global_width",
    "max_restart_loop",
    "restart_top_k",
    "max_workers",
    "validation_fraction",
    "split_by",
    "split_ood_variable",
    "split_random_state",
    "ranking_metric",
    "larger_is_better",
    "force_initial_diagnostics",
    "pause_on_truncated_response",
    "tool_free_stop_review_rounds",
    "stop_guard_mode",
    "stop_guard_metric",
    "stop_guard_threshold",
    "stop_guard_split",
    "stop_guard_larger_is_better",
)

DATA_AGENT_SETTING_NAMES = (
    "llm_provider",
    "llm_model",
    "tool_parser",
    "llm_max_tokens",
    "tools",
    "skills",
    "proxy",
)

EVALUATOR_CONTEXT_SETTING_NAMES = (
    "validation_fraction",
    "split_random_state",
    "split_by",
    "split_ood_variable",
    "ranking_metric",
    "larger_is_better",
)


class SessionStartError(RuntimeError):
    """Exception raised when starting an interactive symbolic-regression run fails during preflight or launch."""

    def __init__(self, message: str, *, run_id: str, started: bool):
        """Initialize the session startup error with run context.

        Args:
            message: Human-readable explanation of the startup failure.
            run_id: Identifier of the run that failed to start.
            started: Whether the background search thread had already been spawned.
        """
        super().__init__(message)
        self.run_id = run_id
        self.started = started


HIDDEN_CAPABILITY_TOOLS = frozenset({"code_executor"})
EVALUATOR_DEFAULT_TOOLS = (
    "read_source",
    "workspace_shell",
    "workspace_code_executor",
    "validate_evaluator",
    "read_skill",
)
MESSAGE_ACCEPTING_INTERACTION_STATES = frozenset(
    {
        "running",
        "pausing",
        "interrupting",
        "paused",
    }
)

PROVIDER_API_KEY_VARIABLES = {
    "openrouter": "OPENROUTER_API_KEY",
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "siliconflow": "SILICONFLOW_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "lmstudio": "LMSTUDIO_API_KEY",
}


class InteractiveSession:
    """Stateful controller for one interactive workbench conversation, coordinating data preparation, evaluator setup, and symbolic regression."""

    def __init__(
        self,
        log_dir,
        agent_options=None,
        initial_prompt="",
        env_path=None,
        workspace_files=None,
        run_dir=None,
        workspace_path=None,
        read_only=False,
    ):
        """Initialize an interactive workbench session and its workspace, environment, and interaction managers.

        Args:
            log_dir: Base directory for run logs when ``run_dir`` is not explicitly set.
            agent_options: Optional initial overrides for agent model and search settings.
            initial_prompt: Optional initial research problem description.
            env_path: Optional path to the conversation's private ``.env`` file.
            workspace_files: Optional host files or directories mounted read-only into the workspace.
            run_dir: Optional directory where per-run search logs are persisted.
            workspace_path: Optional explicit directory path for the conversation workspace.
            read_only: Whether to disable all mutating operations on this session.
        """
        self.sr_interaction_manager = SRInteractionManager()
        self.data_interaction_manager = InteractionManager()
        self.evaluator_interaction_manager = InteractionManager()
        self.lock = threading.RLock()
        self.model_test_lock = threading.Lock()
        self.evaluator_agent_lock = threading.Lock()
        self.run_id = uuid.uuid4().hex
        self.conversation_id = None
        self.run_dir = (
            Path(run_dir).expanduser().resolve()
            if run_dir is not None
            else Path(log_dir).expanduser().resolve() / self.run_id
        )
        self.read_only = bool(read_only)
        if self.read_only:
            if not self.run_dir.is_dir():
                raise FileNotFoundError(f"Read-only run directory does not exist: {self.run_dir}")
        else:
            self.run_dir.mkdir(parents=True, exist_ok=True)
        workspace_root = (
            Path(workspace_path)
            if workspace_path is not None
            else Path(tempfile.mkdtemp(prefix="sr_workspace_"))
        )
        self.workspace_manager = Workspace(workspace_root, read_only=self.read_only)
        for source in workspace_files or ():
            self.workspace_manager.mount(source)
        self.workspace = self.workspace_manager.path
        self.evaluator_workspace = self.workspace / "context.evaluator"
        self.context = AgentContext(workspace=self.workspace_manager)
        self.context.args.save_path = str(self.run_dir)
        self._capability_skill_manager = SkillManager(
            custom_directory=self.workspace / "skills",
            workspace=self.workspace_manager,
        )
        self.context.args.skill_manager = self._capability_skill_manager
        self.env_path = Path(env_path or self.run_dir / ".env").resolve()
        env_values = dotenv_values(self.env_path) if self.env_path.exists() else {}
        stored_environment = {
            str(name): str(value) for name, value in env_values.items() if value is not None
        }
        if no_proxy := os.environ.get("NO_PROXY") or os.environ.get("no_proxy"):
            stored_environment.setdefault("NO_PROXY", no_proxy)
        file_http_proxy = env_values.get("HTTP_PROXY") or env_values.get("http_proxy")
        file_https_proxy = env_values.get("HTTPS_PROXY") or env_values.get("https_proxy")
        configured_proxy = file_https_proxy or file_http_proxy or ""
        self.egress_proxy = os.environ.get("SRH_EGRESS_PROXY", "").strip()
        self.context.args.api_environment = proxy_environment(
            stored_environment,
            user_proxy=configured_proxy,
            egress_proxy=self.egress_proxy,
        )
        self.settings = {
            "llm_provider": "openrouter",
            "llm_model": "deepseek/deepseek-v4-flash-0731",
            "strong_llm_provider": None,
            "strong_llm_model": None,
            "auto_routing": True,
            "tool_parser": "openai",
            "llm_max_tokens": None,
            "tools": None,
            "skills": None,
            "max_refinement_depth": 50,
            "local_sample_size": 1,
            "global_width": 1,
            "max_restart_loop": 1,
            "restart_top_k": 1,
            "max_workers": 0,
            "validation_fraction": 0.2,
            "split_by": "random",
            "split_ood_variable": None,
            "split_random_state": 42,
            "ranking_metric": "mse",
            "larger_is_better": False,
            "force_initial_diagnostics": False,
            "pause_on_truncated_response": True,
            "tool_free_stop_review_rounds": 1,
            "stop_guard_mode": "none",
            "stop_guard_metric": None,
            "stop_guard_threshold": None,
            "stop_guard_split": "validation",
            "stop_guard_larger_is_better": True,
        }
        self.settings.update(agent_options or {})
        if self.settings["tools"] is None:
            self.settings["tools"] = self.capabilities()["default_tools"]
        for name in EVALUATOR_CONTEXT_SETTING_NAMES:
            setattr(self.context.args, name, self.settings[name])
        self.data_agent_settings = {
            "llm_provider": self.settings["llm_provider"],
            "llm_model": self.settings["llm_model"],
            "tool_parser": self.settings["tool_parser"],
            "llm_max_tokens": self.settings["llm_max_tokens"],
            "tools": list(DataPreparationAgent.DEFAULT_TOOLS),
            "skills": [
                name
                for name in self._capability_skill_manager.load_skills()
                if name not in DataPreparationAgent.DEFAULT_EXCLUDED_SKILLS
            ],
            "proxy": configured_proxy,
        }
        self.evaluator_agent_settings = {
            key: self.data_agent_settings[key]
            for key in ("llm_provider", "llm_model", "tool_parser", "llm_max_tokens", "proxy")
        }
        self.evaluator_agent_settings.update(
            {
                # This model reliably reaches native tool calls when constructing an
                # evaluator; the general SR agent keeps the user's configured model.
                "llm_provider": "openrouter",
                "llm_model": "qwen/qwen3.5-flash-02-23",
                "tools": list(EVALUATOR_DEFAULT_TOOLS),
                "skills": [
                    name
                    for name in self._capability_skill_manager.load_skills()
                    if name != "discover-symbolic-laws"
                ],
                "llm_max_tokens": (
                    max(8192, self.data_agent_settings["llm_max_tokens"])
                    if self.data_agent_settings["llm_max_tokens"] is not None else None
                ),
            }
        )
        self.pending_settings = None
        self.initial_prompt = initial_prompt
        self.prompt_overrides = {}
        self.variable_descriptions = {}
        self.state = "idle"
        self.result = None
        self.run_state = None
        self.thread = None
        self.data_thread = None
        self.data_state = "idle"
        self.data_result = None
        self.data_agent = None
        self.evaluator_agent = None
        self.evaluator_agent_thread = None
        self.evaluator_agent_state = "idle"
        self.evaluator_agent_result = None
        self.sr_agent = None
        self._restored_data_agent_buffer = None
        self._manifest_description_revision = None
        self.start_idempotency_key = None

    def interrupt_active_work(self) -> None:
        """Signal any running symbolic-regression, data-preparation, or evaluator-construction thread to stop promptly."""
        for manager in (
            self.sr_interaction_manager,
            self.data_interaction_manager,
            self.evaluator_interaction_manager,
        ):
            if manager.state in {"running", "pausing"}:
                manager.command("force_pause")

    def snapshot(self):
        """Build a JSON-serializable status snapshot of the session for WebUI polling.

        Returns:
            dict[str, Any]: Current states, settings, top-k candidates, and usage counters.
        """
        with self.lock:
            self._sync_manifest_descriptions()
            topk = (
                []
                if self.run_state is None
                else json_value(
                    [record.display_dict() for record in self.run_state.ranked_candidates()]
                )
            )
            return {
                "state": self.state,
                "settings": self.settings.copy(),
                "pending_settings": self.pending_settings,
                "topk_records": topk,
                "result": self.result,
                "run_id": self.run_id,
                "initial_prompt": self.initial_prompt,
                "context_ready": bool(self.context.data),
                "workspace": str(self.workspace),
                "data_state": self.data_state,
                "data_interaction_state": self.data_interaction_manager.state,
                "data_agent_settings": self.data_agent_settings.copy(),
                "evaluator_agent_settings": self.evaluator_agent_settings.copy(),
                "evaluator_agent_state": self.evaluator_agent_state,
                "evaluator_interaction_state": self.evaluator_interaction_manager.state,
                "evaluator_agent_result": json_value(self.evaluator_agent_result),
                "evaluator_id": self._evaluator_metadata()["selected"],
                "data_result": json_value(self.data_result),
                "data_context": json_value(self.context.schema()),
                **self.sr_interaction_manager.status(),
            }

    def idle_persistence_revision(self):
        """Return a revision tuple that remains constant while the session is completely idle.

        Allows the background persistence worker to skip redundant disk writes when
        no agent thread is active and no HTTP mutation has occurred.

        Returns:
            tuple | None: Revision tuple when idle, or ``None`` while any agent thread is running.
        """
        with self.lock:
            if any(thread is not None and thread.is_alive() for thread in (
                self.thread, self.data_thread, self.evaluator_agent_thread,
            )):
                return None
            metadata = [
                getattr(self, "_persistence_generation", 0), self.run_id,
                self.state, self.data_state, self.evaluator_agent_state,
                self.settings, self.pending_settings, self.data_agent_settings,
                self.evaluator_agent_settings, self.initial_prompt, self.prompt_overrides,
                self.variable_descriptions, self.workspace_manager.lock_rules,
                self.context.target, getattr(self.context.args, "data_revision", 0),
                id(self.result), id(self.data_result), id(self.evaluator_agent_result),
                id(self.run_state), self.run_state.node_count if self.run_state else 0,
                len(self.data_agent.buffer) if self.data_agent is not None else len(self._restored_data_agent_buffer or []),
                *[manager.status()["last_event_seq"] for manager in (
                    self.sr_interaction_manager, self.data_interaction_manager,
                    self.evaluator_interaction_manager,
                )],
            ]
            return json.dumps(json_value(metadata), sort_keys=True, ensure_ascii=False)

    def export_persistent_state(self) -> dict[str, Any]:
        """Serialize the session's durable settings, timelines, and search state for disk persistence.

        Returns:
            dict[str, Any]: JSON-serializable session snapshot.
        """
        with self.lock:
            data_agent_buffer = (
                list(self.data_agent.buffer)
                if self.data_agent is not None
                else self._restored_data_agent_buffer
            )
            return json_value(
                {
                    "version": 1,
                    "run_id": self.run_id,
                    "state": self.state,
                    "settings": self.settings,
                    "pending_settings": self.pending_settings,
                    "data_agent_settings": self.data_agent_settings,
                    "evaluator_agent_settings": self.evaluator_agent_settings,
                    "initial_prompt": self.initial_prompt,
                    "prompt_overrides": self.prompt_overrides,
                    "workspace_lock_rules": self.workspace_manager.lock_rules,
                    "variable_descriptions": self.variable_descriptions,
                    "result": self.result,
                    "data_state": self.data_state,
                    "data_result": self.data_result,
                    "data_agent_buffer": data_agent_buffer,
                    "evaluator_agent_state": self.evaluator_agent_state,
                    "evaluator_agent_result": self.evaluator_agent_result,
                    "context_target": self.context.target,
                    "evaluator": self._evaluator_metadata(),
                    "run_state": self.run_state.export_state()
                    if self.run_state is not None
                    else None,
                    "interactions": {
                        "search": self.sr_interaction_manager.export_state(),
                        "data": self.data_interaction_manager.export_state(),
                        "evaluator": self.evaluator_interaction_manager.export_state(),
                    },
                }
            )

    def restore_persistent_state(self, snapshot: dict[str, Any]) -> None:
        """Restore settings, variable descriptions, timelines, and search state from a saved snapshot.

        Any agent turn that was mid-flight when the server previously exited is
        marked as ``"interrupted"``.

        Args:
            snapshot: Session state dictionary previously produced by :meth:`export_persistent_state`.
        """
        expected_fields = {
            "version",
            "run_id",
            "state",
            "settings",
            "pending_settings",
            "data_agent_settings",
            "evaluator_agent_settings",
            "initial_prompt",
            "prompt_overrides",
            "workspace_lock_rules",
            "variable_descriptions",
            "result",
            "data_state",
            "data_result",
            "data_agent_buffer",
            "evaluator_agent_state",
            "evaluator_agent_result",
            "context_target",
            "evaluator",
            "run_state",
            "interactions",
        }
        if set(snapshot) != expected_fields:
            raise ValueError("Persisted InteractiveSession does not match the current schema")
        if snapshot["version"] != 1:
            raise ValueError("Unsupported InteractiveSession snapshot version")
        with self.lock:
            self.run_id = str(snapshot["run_id"])
            restored_settings = dict(snapshot["settings"])
            default_settings = self.settings.copy()
            legacy_stop_fields = {
                "tool_free_stop_review_rounds",
                "stop_guard_mode",
                "stop_guard_metric",
                "stop_guard_threshold",
                "stop_guard_split",
                "stop_guard_larger_is_better",
            }
            missing_settings = set(default_settings) - set(restored_settings)
            if (
                set(restored_settings) - set(default_settings)
                or not missing_settings <= legacy_stop_fields
            ):
                raise ValueError("Persisted settings do not match the current session schema")
            for name in missing_settings:
                restored_settings[name] = default_settings[name]
            self.settings = restored_settings
            self.pending_settings = snapshot["pending_settings"]
            restored_data_settings = dict(snapshot["data_agent_settings"])
            if set(restored_data_settings) != set(self.data_agent_settings):
                raise ValueError("Persisted data-agent settings do not match the current schema")
            self.data_agent_settings = restored_data_settings
            restored_evaluator_settings = dict(snapshot["evaluator_agent_settings"])
            if set(restored_evaluator_settings) != set(self.evaluator_agent_settings):
                raise ValueError(
                    "Persisted evaluator-agent settings do not match the current schema"
                )
            self.evaluator_agent_settings = restored_evaluator_settings
            self.initial_prompt = str(snapshot["initial_prompt"])
            self.prompt_overrides = dict(snapshot["prompt_overrides"])
            self.workspace_manager.load_lock_rules(dict(snapshot["workspace_lock_rules"]))
            if "system" in self.prompt_overrides:
                self.prompt_overrides["system"] = SRAgentInteractive.normalize_system_prompt(
                    self.prompt_overrides["system"]
                )
            self.variable_descriptions = dict(snapshot["variable_descriptions"])
            self.result = snapshot["result"]
            self.data_result = snapshot["data_result"]
            self.evaluator_agent_result = snapshot["evaluator_agent_result"]
            buffer = snapshot["data_agent_buffer"]
            if buffer is not None and not isinstance(buffer, list):
                raise TypeError("data_agent_buffer must be a list or None")
            self._restored_data_agent_buffer = list(buffer) if buffer is not None else None
            for name in EVALUATOR_CONTEXT_SETTING_NAMES:
                setattr(self.context.args, name, self.settings[name])

            data_directory = self.workspace / "context.data"
            if (data_directory / "manifest.json").is_file():
                self.context.commit_context_data(
                    load_context_data(data_directory, workspace=self.workspace_manager)
                )
                target = snapshot["context_target"]
                if target is not None and target not in self.context.data:
                    raise ValueError("Persisted context target is missing from context.data")
                self.context.target = target
                if self.variable_descriptions:
                    self.context.variable_descriptions.update(
                        {
                            name: description
                            for name, description in self.variable_descriptions.items()
                            if name in self.context.data
                        }
                    )

            evaluator = snapshot["evaluator"]
            if not isinstance(evaluator, dict):
                raise TypeError("evaluator snapshot must be a dictionary")
            selected = evaluator["selected"]
            if isinstance(selected, str) and selected.startswith("custom"):
                custom_file = evaluator["custom_file"]
                custom_source = evaluator["source"]
                self.context.evaluator = load_custom_evaluator(
                    file=Path(custom_file) if custom_file is not None else None,
                    source=custom_source,
                    workspace=self.workspace_manager,
                )
            elif selected in {"default", "graph"}:
                self.context.evaluator = create_builtin_evaluator(selected)
            else:
                raise ValueError(f"Unknown persisted evaluator: {selected!r}")
            self.context.invalidate_splits()

            run_state = snapshot["run_state"]
            if run_state is not None and not isinstance(run_state, dict):
                raise TypeError("run_state must be a dictionary or None")
            self.run_state = (
                SearchRunState.from_state(run_state, save_path=self.run_dir)
                if run_state is not None
                else None
            )
            interactions = snapshot["interactions"]
            search_interrupted = self.sr_interaction_manager.restore_state(interactions["search"])
            data_interrupted = self.data_interaction_manager.restore_state(interactions["data"])
            evaluator_interrupted = self.evaluator_interaction_manager.restore_state(
                interactions["evaluator"]
            )
            saved_state = str(snapshot["state"])
            if saved_state not in {
                "idle",
                "starting",
                "running",
                "completed",
                "early_stopped",
                "interrupted",
                "failed",
            }:
                raise ValueError(f"Unknown persisted session state: {saved_state!r}")
            if search_interrupted or saved_state in {"starting", "running"}:
                self.state = "idle"
                previous_result = self.result if isinstance(self.result, dict) else {}
                self.result = {
                    **previous_result,
                    "status": "interrupted",
                    "restored_after_restart": True,
                }
            else:
                self.state = saved_state
            saved_data_state = str(snapshot["data_state"])
            if saved_data_state not in {
                "idle",
                "running",
                "stopping",
                "stopped",
                "completed",
                "failed",
            }:
                raise ValueError(f"Unknown persisted data-agent state: {saved_data_state!r}")
            self.data_state = (
                "stopped"
                if data_interrupted or saved_data_state in {"running", "stopping"}
                else saved_data_state
            )
            saved_evaluator_state = str(snapshot["evaluator_agent_state"])
            if saved_evaluator_state not in {
                "idle",
                "running",
                "stopping",
                "stopped",
                "completed",
                "failed",
            }:
                raise ValueError(
                    f"Unknown persisted evaluator-agent state: {saved_evaluator_state!r}"
                )
            self.evaluator_agent_state = (
                "stopped"
                if evaluator_interrupted or saved_evaluator_state in {"running", "stopping"}
                else saved_evaluator_state
            )

    def _sync_manifest_descriptions(self, *, strict: bool = False) -> None:
        """Reflect externally edited manifest descriptions in the live context."""
        manifest_path = self.workspace / "context.data" / "manifest.json"
        if not self.context.data or not manifest_path.is_file():
            return
        stat = manifest_path.stat()
        revision = (stat.st_mtime_ns, stat.st_size)
        if revision == self._manifest_description_revision and not strict:
            return
        try:
            with self.workspace_manager.safe_open(manifest_path, "r", encoding="utf-8") as stream:
                manifest = json.load(stream)
            descriptions = {}
            for section in ("variables", "axes"):
                for name, spec in manifest[section].items():
                    description = spec["description"]
                    if not isinstance(description, str):
                        if strict:
                            raise ValueError(f"{section}.{name}.description must be a string")
                        return
                    description = description.strip()
                    if strict and not description:
                        raise ValueError(f"{section}.{name}.description must not be empty")
                    descriptions[name] = description
        except (KeyError, TypeError, json.JSONDecodeError, OSError) as exc:
            if strict:
                raise ValueError(f"Invalid context.data manifest descriptions: {exc}") from exc
            return
        changed = False
        for name in self.context.data:
            current = self.context.variable_descriptions.get(name, "")
            if name in descriptions and current != descriptions[name]:
                self.context.variable_descriptions[name] = descriptions[name]
                changed = True
        self._manifest_description_revision = revision
        if changed:
            self.variable_descriptions = dict(self.context.variable_descriptions)
            self.context.args.data_revision += 1

    def evaluator_configuration(self):
        """Return the active evaluator selection, catalog of built-in and custom evaluators, and editor source code.

        Returns:
            dict[str, Any]: Evaluator configuration payload for the Task Setup tab.
        """
        metadata = self._evaluator_metadata()
        return {
            "selected": metadata["selected"],
            "source": metadata["source"],
            "custom_template": CUSTOM_TEMPLATE,
            "evaluators": [*evaluator_catalog(), *self._custom_evaluator_catalog()],
            "custom_name": metadata["custom_name"],
            "custom_file": metadata["custom_file"],
        }

    def _custom_evaluator_catalog(self) -> list[dict[str, Any]]:
        """Return valid evaluator implementations saved in this workspace."""
        files = self._custom_evaluator_files()
        catalog = []
        for file in files:
            try:
                with self.workspace_manager.safe_open(file, "r", encoding="utf-8") as stream:
                    source = stream.read()
                evaluator = load_custom_evaluator(
                    source=source,
                    file=file,
                    workspace=self.workspace_manager,
                )
            except (OSError, UnicodeError, ValueError) as exc:
                try:
                    with self.workspace_manager.safe_open(
                        file,
                        "r",
                        encoding="utf-8",
                        errors="replace",
                    ) as stream:
                        source = stream.read()
                except OSError:
                    source = ""
                catalog.append(
                    {
                        "id": f"custom:{file.name}",
                        "label": file.stem,
                        "label_en": file.stem,
                        "source": source,
                        "abstract": False,
                        "custom": True,
                        "file": str(file),
                        "invalid": True,
                        "error": str(exc),
                    }
                )
                continue
            class_name = type(evaluator).__name__
            catalog.append(
                {
                    "id": f"custom:{file.name}",
                    "label": class_name,
                    "label_en": class_name,
                    "source": source,
                    "abstract": False,
                    "custom": True,
                    "file": str(file),
                    "invalid": False,
                    "error": None,
                }
            )
        return catalog

    def _custom_evaluator_files(self) -> list[Path]:
        """Return ordinary evaluator files without following workspace links."""
        directory = self.workspace_manager.resolve("context.evaluator")
        if directory is None or not directory.is_dir():
            return []
        with os.scandir(directory) as entries:
            candidates = [
                Path(entry.path)
                for entry in entries
                if entry.name.endswith(".py") and entry.is_file(follow_symlinks=False)
            ]
        files = []
        for path in candidates:
            try:
                with self.workspace_manager.safe_open(path, "rb") as stream:
                    if stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                        files.append(path)
            except OSError:
                continue
        return sorted(files, key=lambda path: path.name)

    def _evaluator_metadata(self) -> dict[str, Any]:
        evaluator = self.context.evaluator
        custom = getattr(type(evaluator), "CUSTOM_EVALUATOR", None)
        if isinstance(custom, dict) and isinstance(custom.get("source"), str):
            file = custom.get("file")
            return {
                "selected": f"custom:{Path(file).name}" if file is not None else "custom",
                "source": custom["source"],
                "custom_name": type(evaluator).__name__,
                "custom_file": str(file) if file is not None else None,
            }
        selected = "graph" if type(evaluator) is GraphEvaluator else "default"
        return {
            "selected": selected,
            "source": evaluator_source(selected),
            "custom_name": None,
            "custom_file": None,
        }

    def evaluator_editable(self) -> bool:
        """Return whether the active evaluator can currently be changed or edited.

        Returns:
            bool: ``True`` when the symbolic-regression search is idle or safely paused.
        """
        if self.state == "idle":
            return True
        control = self.sr_interaction_manager.status()
        return self.state in {"starting", "running"} and control["interaction_state"] == "paused"

    def configure_evaluator(self, payload):
        """Select a built-in evaluator or validate and save custom evaluator Python source in ``context.evaluator/``.

        Args:
            payload: Request dictionary containing ``selected`` and optional ``source``.

        Returns:
            dict[str, Any]: Updated evaluator configuration payload.
        """
        if not self.evaluator_editable():
            raise ValueError(
                "Pause the search and wait for a safe boundary before changing the evaluator"
            )
        evaluator_id = str(payload.get("selected", "")).strip()
        source = str(payload.get("source", ""))
        available = {
            item["id"]: item for item in [*evaluator_catalog(), *self._custom_evaluator_catalog()]
        }
        selected_item = available.get(evaluator_id)
        builtin_source = (
            evaluator_source(evaluator_id)
            if evaluator_id in {item["id"] for item in evaluator_catalog()}
            else None
        )
        if builtin_source is not None and source == builtin_source:
            evaluator = create_builtin_evaluator(evaluator_id)
            source = builtin_source
            custom_name = None
        elif (
            selected_item is not None
            and selected_item.get("custom")
            and source == selected_item["source"]
        ):
            evaluator = load_custom_evaluator(
                file=Path(selected_item["file"]),
                workspace=self.workspace_manager,
            )
            custom_name = type(evaluator).__name__
        else:
            try:
                declared_names = {
                    node.name
                    for node in ast.parse(source, mode="exec").body
                    if isinstance(node, ast.ClassDef)
                }
            except SyntaxError:
                declared_names = set()
            if conflicts := declared_names & BUILTIN_EVALUATOR_CLASS_NAMES:
                custom_name = sorted(conflicts)[0]
                raise ValueError(
                    f"Evaluator class name {custom_name!r} conflicts with a built-in evaluator. "
                    "Rename the class before saving."
                )
            evaluator = load_custom_evaluator(
                source=source,
                workspace=self.workspace_manager,
            )
            custom_name = type(evaluator).__name__
            if custom_name in BUILTIN_EVALUATOR_CLASS_NAMES:
                raise ValueError(
                    f"Evaluator class name {custom_name!r} conflicts with a built-in evaluator. "
                    "Rename the class before saving."
                )
            filename = evaluator_filename(custom_name)
            save_dir = self.evaluator_workspace
            save_dir_relative = str(save_dir.relative_to(self.workspace))
            self.workspace_manager.create_directory(
                save_dir_relative,
                parents=True,
                exist_ok=True,
            )
            destination = save_dir / filename
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{destination.stem}-", suffix=".py", dir=self.run_dir
            )
            os.close(descriptor)
            temporary = Path(temporary_name)
            try:
                temporary.write_text(source, encoding="utf-8")
                self.workspace_manager.replace_file(
                    temporary,
                    str(destination.relative_to(self.workspace)),
                )
            finally:
                temporary.unlink(missing_ok=True)
            evaluator = load_custom_evaluator(
                file=destination,
                workspace=self.workspace_manager,
            )
            evaluator_id = f"custom:{destination.name}"
        with self.lock:
            self.context.evaluator = evaluator
            self.context.invalidate_splits()
        return self.evaluator_configuration()

    def test_evaluator(self, payload):
        """Test a candidate evaluator configuration against the current best formula (or a baseline linear formula).

        Args:
            payload: Request dictionary specifying ``selected`` and optional ``source`` to test.

        Returns:
            dict[str, Any]: Test formula string and train/validation metric results.
        """
        evaluator_id = str(payload.get("selected", self._evaluator_metadata()["selected"])).strip()
        source = str(payload.get("source", ""))
        available = {
            item["id"]: item for item in [*evaluator_catalog(), *self._custom_evaluator_catalog()]
        }
        selected_item = available.get(evaluator_id)
        if (
            selected_item is not None
            and selected_item.get("custom")
            and source == selected_item["source"]
        ):
            evaluator = load_custom_evaluator(
                file=Path(selected_item["file"]),
                workspace=self.workspace_manager,
            )
        elif evaluator_id in {
            item["id"] for item in evaluator_catalog()
        } and source == evaluator_source(evaluator_id):
            evaluator = create_builtin_evaluator(evaluator_id)
        else:
            evaluator = load_custom_evaluator(
                source=source,
                workspace=self.workspace_manager,
            )
        if not self.context.data or not self.context.target or not self.context.feature_names():
            raise ValueError("Prepare data and select a target plus at least one feature first")
        test_context = AgentContext(
            args=self.context.args,
            data=self.context.data,
            target=self.context.target,
            variable_descriptions=self.context.variable_descriptions,
            variable_axes=self.context.variable_axes,
            variable_structures=self.context.variable_structures,
            num_nodes=self.context.num_nodes,
            evaluator=evaluator,
            workspace=self.context.workspace,
        )
        ranked = self.run_state.ranked_candidates() if self.run_state is not None else []
        best_formula = next((record.formula for record in ranked if record.formula), None)
        features = self.context.feature_names()
        baseline = " + ".join(
            ["param('intercept')"]
            + [f"param('coefficient_{index}') * {name}" for index, name in enumerate(features, 1)]
        )
        formula = str(payload.get("formula") or best_formula or baseline).strip()
        result = ValidateEvaluatorTool(context=test_context)(
            evaluator_file=None,
            f=formula,
            fit=True,
            show_diagnostics=False,
        )
        if not result.ok:
            raise ValueError(result.result_str)
        return {"formula": formula, "result": json_value(result.result)}

    def assist_evaluator(self, payload):
        """Run the Evaluator Construction Agent synchronously for one natural-language instruction.

        Args:
            payload: Request dictionary containing ``message`` and optional current editor ``source``.

        Returns:
            dict[str, Any]: Agent completion status, message, and any validated evaluator source.
        """
        if not self.evaluator_editable():
            raise ValueError(
                "Pause the search and wait for a safe boundary before using EvaluatorConstructionAgent"
            )
        instruction = str(payload.get("message", "")).strip()
        if not instruction:
            raise ValueError("Evaluator construction instruction must not be empty")
        instruction = (
            instruction
            + "\n\nKeep evaluator scripts inside context.evaluator/ and validate the final file. "
            "The directory may not exist yet; create it with a workspace tool only when you are "
            "ready to write the first evaluator script."
        )

        settings = self.evaluator_agent_settings.copy()
        enabled_tools = settings.get("tools") or []
        classes = {tool_cls.metadata.name: tool_cls for tool_cls in BaseTool.load_tool_classes()}
        tools = [classes[name](context=self.context) for name in enabled_tools]
        previous_skills = getattr(self.context.args, "enabled_skills", None)
        self.context.args.enabled_skills = settings.get("skills") or []
        try:
            with self.evaluator_agent_lock:
                agent = EvaluatorConstructionAgent(
                    llm_provider=settings["llm_provider"],
                    llm_model=settings["llm_model"],
                    context=self.context,
                    tools=tools,
                    tool_parser=settings["tool_parser"],
                    llm_max_tokens=settings["llm_max_tokens"],
                    interaction_manager=self.evaluator_interaction_manager,
                )
                with self.lock:
                    self.evaluator_agent = agent
                try:
                    result = agent.run(instruction)
                finally:
                    with self.lock:
                        if self.evaluator_agent is agent:
                            self.evaluator_agent = None
        finally:
            if previous_skills is None:
                delattr(self.context.args, "enabled_skills")
            else:
                self.context.args.enabled_skills = previous_skills
        files = sorted(self._custom_evaluator_files(), key=lambda path: path.lstat().st_mtime_ns)
        if not files:
            raise ValueError(
                "EvaluatorConstructionAgent did not create a Python file under context.evaluator/"
            )
        result_file = files[-1]
        with self.workspace_manager.safe_open(result_file, "r", encoding="utf-8") as stream:
            result_source = stream.read()
        return {
            **result,
            "source": result_source,
            "selected": f"custom:{result_file.name}",
            "custom_file": str(result_file),
            "provider": settings["llm_provider"],
            "model": settings["llm_model"],
        }

    def start_evaluator_assistance(self, payload):
        """Launch the Evaluator Construction Agent in a background thread for a user instruction.

        Args:
            payload: Request dictionary containing ``message`` and optional editor ``source``.

        Returns:
            dict[str, Any]: Updated session snapshot reflecting the running evaluator agent.
        """
        with self.lock:
            instruction = str(payload.get("message", "")).strip()
            if not instruction:
                raise ValueError("Evaluator construction instruction must not be empty")
            if self.evaluator_interaction_manager.state in MESSAGE_ACCEPTING_INTERACTION_STATES:
                self.evaluator_interaction_manager.command("message", instruction)
                self.evaluator_agent_state = "running"
                return self.snapshot()
            self.evaluator_interaction_manager.command("message", instruction)
            self.evaluator_agent_state = "running"
            self.evaluator_agent_result = None
            self.evaluator_agent_thread = threading.Thread(
                target=self._run_evaluator_assistance,
                args=(dict(payload),),
                daemon=True,
            )
            self.evaluator_agent_thread.start()
        return self.snapshot()

    def stop_evaluator_assistance(self):
        """Request a safe pause (first click) or immediate interruption (second click) of the Evaluator Construction Agent.

        Returns:
            dict[str, Any]: Updated session snapshot.
        """
        with self.lock:
            interaction_state = self.evaluator_interaction_manager.state
            if interaction_state not in {"running", "pausing"}:
                raise ValueError("EvaluatorConstructionAgent is not running")
            force = interaction_state == "pausing"
            control = self.evaluator_interaction_manager.command(
                "force_pause" if force else "pause"
            )
            self.evaluator_agent_state = "stopping"
        snapshot = self.snapshot()
        if control.get("cancellation_error"):
            snapshot["cancellation_error"] = control["cancellation_error"]
        return snapshot

    def _run_evaluator_assistance(self, payload) -> None:
        try:
            queued = self.evaluator_interaction_manager.start_agent_execution()
            if queued:
                payload["message"] = queued[-1].content
            result = self.assist_evaluator(payload)
            state = "completed"
        except InterruptedError as exc:
            result = {"status": "stopped", "message": str(exc)}
            state = "stopped"
        except Exception as exc:
            _logger.exception("Evaluator construction Agent failed")
            result = {"status": "failed", "error": str(exc)}
            state = "failed"
        with self.lock:
            self.evaluator_agent_result = result
            self.evaluator_agent_state = state
        self.evaluator_interaction_manager.publish_event(
            "execution_completed" if state == "completed" else "execution_failed",
            {**json_value(result), "status": state},
        )
        if self.evaluator_interaction_manager.state != "paused":
            self.evaluator_interaction_manager.finish_agent_execution()

    def configure_evaluator_agent(self, payload):
        """Validate and apply model, proxy, parser, and capability settings for the Evaluator Construction Agent.

        Args:
            payload: Settings dictionary submitted from the Evaluator Agent settings panel.

        Returns:
            dict[str, Any]: Updated session snapshot.
        """
        self._ensure_settings_editable()
        settings = self.validate_evaluator_agent_settings(payload)
        self.validate_capabilities(settings, agent="evaluator")
        with self.lock:
            if "proxy" in settings:
                self.set_proxy(settings["proxy"])
            self.evaluator_agent_settings = {**self.evaluator_agent_settings, **settings}
            if "proxy" in settings:
                self.data_agent_settings["proxy"] = settings["proxy"]
            if self.evaluator_agent is not None:
                self.evaluator_agent.queue_runtime_settings(settings)
        return self.snapshot()

    def test_evaluator_agent_model(self, payload):
        """Test connectivity and tool-calling support for the Evaluator Construction Agent's model settings.

        Args:
            payload: Candidate model settings to test.

        Returns:
            dict[str, Any]: Diagnostic result with ``ok``, ``accessible``, and ``tool_call_ok``.
        """
        updates = self.validate_evaluator_agent_settings(payload)
        self.validate_capabilities(updates, agent="evaluator")
        settings = {**self.evaluator_agent_settings, **updates}
        return self._test_model(settings, proxy=settings.get("proxy", ""))

    def capabilities(self, agent: str = "search"):
        """Return available tools, skills, and default selections for the specified agent scope.

        Args:
            agent: Agent scope identifier (``"search"``, ``"data"``, or ``"evaluator"``).

        Returns:
            dict[str, Any]: Catalog of tools, skills, and default enabled names.
        """
        if agent not in {"search", "data", "evaluator"}:
            raise ValueError(f"Unsupported agent capability scope: {agent}")
        tools = [
            {
                "name": tool_cls.metadata.name,
                "description": tool_cls.metadata.description,
            }
            for tool_cls in BaseTool.load_tool_classes()
            if tool_cls.metadata.name not in HIDDEN_CAPABILITY_TOOLS
        ]
        skills = [
            {"name": skill.name, "description": skill.description}
            for skill in self._capability_skill_manager.load_skills().values()
        ]
        tool_names = [tool["name"] for tool in tools]
        if agent == "data":
            default_tools = list(DataPreparationAgent.DEFAULT_TOOLS)
            default_skills = [
                skill["name"]
                for skill in skills
                if skill["name"] not in DataPreparationAgent.DEFAULT_EXCLUDED_SKILLS
            ]
        elif agent == "evaluator":
            default_tools = list(EVALUATOR_DEFAULT_TOOLS)
            default_skills = [
                skill["name"] for skill in skills if skill["name"] != "discover-symbolic-laws"
            ]
        else:
            default_tools = [
                name for name in SRAgentInteractive.DEFAULT_TOOLS if name in tool_names
            ]
            default_skills = [skill["name"] for skill in skills]
        return {
            "tools": tools,
            "skills": skills,
            "default_tools": default_tools,
            "default_skills": default_skills,
        }

    def validate_capabilities(self, settings, agent: str = "search"):
        """Validate and normalize user-selected ``tools`` and ``skills`` lists for ``agent``.

        Args:
            settings: Raw settings dictionary containing optional ``tools`` and ``skills`` keys.
            agent: Target agent scope (``"search"``, ``"data"``, or ``"evaluator"``).

        Returns:
            dict[str, list[str]]: Validated ``tools`` and ``skills`` name lists.
        """
        catalog = self.capabilities(agent)
        for key, catalog_key in (("tools", "tools"), ("skills", "skills")):
            if key not in settings:
                continue
            available = {item["name"] for item in catalog[catalog_key]}
            if unknown := set(settings[key]) - available:
                raise ValueError(f"Unknown {key}: {', '.join(sorted(unknown))}")
        if (
            agent == "data"
            and "tools" in settings
            and "validate_context_data" not in settings["tools"]
        ):
            raise ValueError("The data-preparation agent requires the validate_context_data tool")
        if (
            agent == "evaluator"
            and settings.get("skills")
            and "read_skill" not in settings.get("tools", self.evaluator_agent_settings["tools"])
        ):
            raise ValueError("Evaluator-agent skills require the read_skill tool")

    def provider_credential(self, provider: str):
        """Check whether an API key is configured for ``provider`` without exposing the secret key itself.

        Args:
            provider: Model provider name (e.g., ``"openrouter"``, ``"deepseek"``).

        Returns:
            dict[str, Any]: Dictionary with ``provider``, ``env_var``, ``configured``,
                and ``stored_in_env_file``.
        """
        provider = str(provider).strip().lower()
        try:
            variable = PROVIDER_API_KEY_VARIABLES[provider]
        except KeyError as exc:
            raise ValueError(f"Unsupported web model provider: {provider}") from exc
        file_value = self.context.args.api_environment.get(variable)
        configured = bool(file_value or os.environ.get(variable))
        return {
            "provider": provider,
            "env_var": variable,
            "configured": configured,
            "stored_in_env_file": bool(file_value),
        }

    def set_provider_credential(self, provider: str, api_key: str):
        """Save a provider API key to the conversation's private ``.env`` file and update the session environment.

        Args:
            provider: Model provider name.
            api_key: Non-empty secret API key string.

        Returns:
            dict[str, Any]: Updated credential status from :meth:`provider_credential`.
        """
        status = self.provider_credential(provider)
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("api_key must be a non-empty string")
        api_key = api_key.strip()
        if len(api_key) > 16_384 or any(character in api_key for character in "\r\n\0"):
            raise ValueError("api_key contains unsupported characters")
        with self.lock:
            self.env_path.parent.mkdir(parents=True, exist_ok=True)
            if not self.env_path.exists():
                self.env_path.touch(mode=0o600)
            set_key(
                self.env_path,
                status["env_var"],
                api_key,
                quote_mode="always",
            )
            self.context.args.api_environment[status["env_var"]] = api_key
        return self.provider_credential(provider)

    def set_proxy(self, proxy: str) -> None:
        """Save an outbound HTTP/SOCKS proxy URL to the conversation's private ``.env`` file.

        Args:
            proxy: Validated proxy URL, or an empty string to disable proxying.
        """
        proxy = self.validate_proxy(proxy)
        self.env_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.env_path.exists():
            self.env_path.touch(mode=0o600)
        if proxy:
            set_key(self.env_path, "HTTP_PROXY", proxy, quote_mode="always")
            set_key(self.env_path, "HTTPS_PROXY", proxy, quote_mode="always")
        else:
            unset_key(self.env_path, "HTTP_PROXY")
            unset_key(self.env_path, "HTTPS_PROXY")
        updated_environment = proxy_environment(
            self.context.args.api_environment,
            user_proxy=proxy,
            egress_proxy=self.egress_proxy,
        )
        self.context.args.api_environment.clear()
        self.context.args.api_environment.update(updated_environment)

    @staticmethod
    def validate_proxy(proxy: str) -> str:
        """Validate and normalize an optional HTTP, HTTPS, or SOCKS proxy URL.

        Args:
            proxy: Raw proxy URL string from the UI.

        Returns:
            str: Trimmed proxy URL, or ``""`` when empty.
        """
        if not isinstance(proxy, str):
            raise ValueError("proxy must be a string")
        proxy = proxy.strip()
        if not proxy:
            return ""
        if len(proxy) > 4096 or any(character in proxy for character in "\r\n\0"):
            raise ValueError("proxy contains unsupported characters")
        parsed = urlparse(proxy)
        if parsed.scheme not in {"http", "https", "socks5", "socks5h"} or not parsed.netloc:
            raise ValueError("proxy must be an HTTP, HTTPS, SOCKS5, or SOCKS5H URL")
        return proxy

    @staticmethod
    def validate_setting_dependencies(settings):
        """Verify cross-field constraints across validated runtime settings (such as OOD split variables and stop-guard thresholds).

        Args:
            settings: Dictionary of candidate runtime settings.
        """
        if (
            settings.get("stop_guard_mode") == "metric_threshold"
            and settings.get("stop_guard_threshold") is None
        ):
            raise ValueError(f"{settings['stop_guard_mode']} requires stop_guard_threshold")
        if not settings.get("force_initial_diagnostics"):
            return
        tools = settings.get("tools")
        required = {"statistics_analysis", "relationship_analysis", "read_skill"}
        if tools is not None and (missing := required - set(tools)):
            raise ValueError(
                "force_initial_diagnostics requires enabled tools: " + ", ".join(sorted(missing))
            )
        skills = settings.get("skills")
        if skills is not None and "discover-symbolic-laws" not in skills:
            raise ValueError("force_initial_diagnostics requires the discover-symbolic-laws skill")

    def start(self, payload):
        """Validate task configuration and start the interactive symbolic-regression search in a background thread.

        Args:
            payload: Startup payload containing variable selections, prompts, and optional setting overrides.

        Returns:
            dict[str, Any]: Session snapshot after starting the search.
        """
        with self.lock:
            idempotency_key = payload.get("idempotency_key")
            if idempotency_key is not None:
                if (
                    not isinstance(idempotency_key, str)
                    or not idempotency_key.strip()
                    or len(idempotency_key) > 200
                ):
                    raise ValueError(
                        "idempotency_key must be a non-empty string up to 200 characters"
                    )
                idempotency_key = idempotency_key.strip()
            if self.state != "idle":
                if idempotency_key is not None and idempotency_key == self.start_idempotency_key:
                    return self.snapshot()
                raise ValueError("This server already owns a run. Restart it to begin a new task.")
            if self.data_interaction_manager.state in {"running", "pausing", "interrupting"}:
                raise ValueError("Wait for the data-preparation agent to finish before starting")
            if "dataset" in payload:
                raise ValueError(
                    "The dataset start option is no longer supported; prepare context.data first"
                )
            manifest_path = self.workspace / "context.data" / "manifest.json"
            if not self.context.data or not manifest_path.is_file():
                raise ValueError("Create and load a valid context.data dataset before starting")
            options = self.validate_settings(payload, initial=True)
            self.validate_capabilities(options)
            updated_settings = {**self.settings, **options}
            self.validate_setting_dependencies(updated_settings)
            self.settings = updated_settings
            description = str(
                payload.get(
                    "problem_description",
                    payload.get("prompt", "Find an interpretable formula explaining the data."),
                )
            )
            self.prompt_overrides = {
                role: (
                    SRAgentInteractive.normalize_system_prompt(str(payload[key]))
                    if role == "system"
                    else str(payload[key])
                )
                for role, key in (("system", "system_prompt"), ("user", "user_prompt"))
                if key in payload
            }
            self.variable_descriptions = self.validate_variable_descriptions(payload)
            self._sync_manifest_descriptions(strict=True)
            target = str(payload.get("target") or self.context.target)
            features = payload.get("features") or list(self.context.feature_names())
            X, y = self._select_context_columns(target, features)
            descriptions = dict(self.context.variable_descriptions)
            descriptions.update(self.variable_descriptions)
            self.context.variable_descriptions = {
                name: descriptions.get(name, "") for name in self.context.data
            }
            self.variable_descriptions = dict(self.context.variable_descriptions)
            self.state = "starting"
            self.start_idempotency_key = idempotency_key
            try:
                response = self.snapshot()
                self.thread = threading.Thread(
                    target=self._run,
                    args=(X, y, description),
                    daemon=True,
                )
                self.thread.start()
            except Exception as exc:
                thread = self.thread
                started = bool(thread is not None and thread.ident is not None)
                failure_stage = "start_response" if started else "start_preflight"
                if started and thread.is_alive():
                    self.interrupt_active_work()
                    thread.join(timeout=2)
                self.result = {
                    "status": "failed",
                    "error": str(exc),
                    "failure_stage": failure_stage,
                }
                self.state = "failed" if started else "idle"
                conversation = self.conversation_id or self.workspace.name
                thread_alive = bool(thread and thread.is_alive())
                _logger.exception(
                    f"Failed to start conversation={conversation} run={self.run_id} "
                    f"thread_alive={thread_alive} stage={failure_stage}"
                )
                raise SessionStartError(
                    str(exc),
                    run_id=self.run_id,
                    started=started,
                ) from exc
        return response

    def prepare_data(self, instruction: str):
        """Start or continue the Data Preparation Agent in a background thread with ``instruction``.

        Args:
            instruction: Natural-language instruction for the Data Preparation Agent.

        Returns:
            dict[str, Any]: Updated session snapshot.
        """
        with self.lock:
            instruction = instruction.strip()
            if not instruction:
                raise ValueError("Data-preparation instruction must not be empty")
            if self.data_interaction_manager.state in MESSAGE_ACCEPTING_INTERACTION_STATES:
                self.data_interaction_manager.command("message", instruction)
                self.data_state = "running"
                return self.snapshot()
            if self.state == "starting":
                raise ValueError("Wait for symbolic regression to reach a controllable boundary")
            control_status = self.sr_interaction_manager.status()
            if self.state == "running" and not (control_status["interaction_state"] == "paused"):
                raise ValueError(
                    "Pause symbolic regression and wait for the safe-boundary acknowledgement "
                    "before changing its data"
                )
            settings = self.data_agent_settings.copy()
            if self.data_agent is None:
                self.data_agent = DataPreparationAgent(
                    llm_provider=settings["llm_provider"],
                    llm_model=settings["llm_model"],
                    context=self.context,
                    tools=settings["tools"],
                    tool_parser=settings["tool_parser"],
                    llm_max_tokens=settings["llm_max_tokens"],
                    skills=settings["skills"],
                    interaction_manager=self.data_interaction_manager,
                )
                if self._restored_data_agent_buffer:
                    self.data_agent.buffer = list(self._restored_data_agent_buffer)
                    self._restored_data_agent_buffer = None
            else:
                self.data_agent.llm_provider = settings["llm_provider"]
                self.data_agent.llm_model = settings["llm_model"]
                self.data_agent.tool_parser = settings["tool_parser"]
                self.data_agent.llm_max_tokens = settings["llm_max_tokens"]
                self.data_agent.skills = settings["skills"]
                self.data_agent.tool_cls_list = BaseTool.load_tool_classes(settings["tools"])
                self.data_agent.initialize_with_context(self.context)
            self.data_interaction_manager.command("message", instruction)
            self.data_state = "running"
            self.data_result = None
            self.data_thread = threading.Thread(
                target=self._prepare_data,
                args=(instruction,),
                daemon=True,
            )
            self.data_thread.start()
        return self.snapshot()

    def stop_data_preparation(self):
        """Request a safe pause or immediate interruption of the active Data Preparation Agent turn.

        Returns:
            dict[str, Any]: Updated session snapshot.
        """
        with self.lock:
            interaction_state = self.data_interaction_manager.state
            if interaction_state not in {"running", "pausing"}:
                raise ValueError("The data-preparation agent is not running")
            force = interaction_state == "pausing"
            self.data_state = "stopping"
            control = self.data_interaction_manager.command("force_pause" if force else "pause")
        snapshot = self.snapshot()
        if control.get("cancellation_error"):
            snapshot["cancellation_error"] = control["cancellation_error"]
        return snapshot

    def _prepare_data(self, instruction: str) -> None:
        data_directory = self.workspace / "context.data"

        def directory_revision():
            resolved_directory = self.workspace_manager.resolve("context.data")
            if resolved_directory is None or not resolved_directory.is_dir():
                return None
            revision = []
            for current, directory_names, file_names in os.walk(
                resolved_directory, followlinks=False
            ):
                current_path = Path(current)
                directory_names[:] = [
                    name for name in directory_names if not (current_path / name).is_symlink()
                ]
                for name in file_names:
                    path = current_path / name
                    metadata = path.lstat()
                    if stat.S_ISREG(metadata.st_mode):
                        revision.append(
                            (
                                str(path.relative_to(resolved_directory)),
                                metadata.st_size,
                                metadata.st_mtime_ns,
                            )
                        )
            return tuple(sorted(revision))

        previous_revision = directory_revision()
        try:
            queued = self.data_interaction_manager.start_agent_execution()
            result = self.data_agent.run(queued[-1].content if queued else instruction)
            if (
                directory_revision() != previous_revision
                and (data_directory / "manifest.json").is_file()
            ):
                self.context.commit_context_data(
                    load_context_data(
                        data_directory,
                        workspace=self.workspace_manager,
                    )
                )
                result = {**result, "context": self.context.schema()}
            state = "completed"
        except InterruptedError as exc:
            result = {
                "status": "stopped",
                "message": str(exc),
                "context": self.context.schema(),
            }
            state = "stopped"
            self.data_interaction_manager.publish_event("execution_failed", result)
        except Exception as exc:
            _logger.exception("Data preparation Agent failed")
            public_error = {"error": str(exc)}
            result = {**public_error, "context": self.context.schema()}
            state = "failed"
            self.data_interaction_manager.publish_event("execution_failed", public_error)
        with self.lock:
            self.data_result = json_value(result)
            self.data_state = state
        if self.data_interaction_manager.state != "paused":
            self.data_interaction_manager.finish_agent_execution()

    def preview_initial_prompts(self, payload):
        """Generate the default system and user prompts from the current variable configuration and problem description.

        Args:
            payload: Dictionary containing ``target``, ``features``, ``problem_description``,
                and ``variable_descriptions``.

        Returns:
            dict[str, str]: Generated ``problem_description``, ``system_prompt``, and ``user_prompt``.
        """
        description = str(
            payload.get(
                "problem_description",
                self.initial_prompt
                or "Find an interpretable formula explaining the selected target from the selected features.",
            )
        )
        if self.context.data:
            target = str(payload.get("target") or self.context.target or "")
            features = payload.get("features") or list(self.context.feature_names())
            X, y = self._select_context_columns(target, features)
        else:
            X, y = {"x": np.empty(1)}, {"y": np.empty(1)}
        settings = self.settings
        preview_agent = object.__new__(SRAgentInteractive)
        preview_agent.model_router = ModelRouter(
            enabled=bool(settings.get("auto_routing", False)),
            base_provider=settings["llm_provider"],
            base_model=settings["llm_model"],
            strong_provider=settings.get("strong_llm_provider"),
            strong_model=settings.get("strong_llm_model"),
        )
        preview_agent.max_refinement_depth = settings["max_refinement_depth"]
        preview_agent.use_workspace = True
        preview_agent.interaction_manager = InteractionManager()
        preview_agent.variable_descriptions = self.validate_variable_descriptions(payload)
        preview_agent.prompt_overrides = {}
        preview_agent.ranking_metric = settings.get("ranking_metric", "mse")
        preview_agent.larger_is_better = bool(settings.get("larger_is_better", False))
        preview_agent.run_state = SimpleNamespace(
            ranked_candidates=lambda: [], pareto_indices=lambda records: []
        )
        messages = preview_agent.create_initial_prompt_messages(description, X, y, [])
        return {
            "problem_description": description,
            "system_prompt": next(
                message["content"] for message in messages if message["role"] == "system"
            ),
            "user_prompt": next(
                message["content"] for message in messages if message["role"] == "user"
            ),
        }

    def _select_context_columns(
        self,
        target: str,
        features: Any,
    ) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
        if not target or not isinstance(features, list) or not features or target in features:
            raise ValueError("Select a target and at least one distinct feature")

        def array(name: str) -> np.ndarray | None:
            return self.context.data.get(name)

        selected = {name: array(name) for name in [*features, target]}
        missing = [name for name, value in selected.items() if value is None]
        if missing:
            raise ValueError(f"Selected variables or axes do not exist: {missing}")
        arrays = {name: np.asarray(value) for name, value in selected.items()}
        return (
            {name: arrays[name] for name in features},
            {target: arrays[target]},
        )

    @staticmethod
    def validate_variable_descriptions(payload):
        """Validate that ``variable_descriptions`` in ``payload`` maps variable names to strings.

        Args:
            payload: Request dictionary containing an optional ``variable_descriptions`` mapping.

        Returns:
            dict[str, str]: Mapping of variable names to non-empty trimmed description strings.
        """
        descriptions = payload.get("variable_descriptions", {})
        if not isinstance(descriptions, dict) or any(
            not isinstance(name, str) or not isinstance(value, str)
            for name, value in descriptions.items()
        ):
            raise ValueError("variable_descriptions must map column names to text")
        return {name: value.strip() for name, value in descriptions.items() if value.strip()}

    def create_demo(self, kind: str = "polynomial"):
        """Generate a built-in sample dataset in ``context.data/`` and load it into the shared context.

        Args:
            kind: Sample dataset kind (``"polynomial"``, ``"grouped_parameters"``,
                ``"driven_ode"``, or ``"kuramoto_ba"``).

        Returns:
            Path: Path to the created ``context.data/`` directory.

        Raises:
            FileExistsError: If ``context.data/`` already exists and is non-empty.
        """
        with self.lock:
            path = self.workspace / "context.data"
            if path.exists() or path.is_symlink():
                if path.is_symlink() or not path.is_dir() or any(path.iterdir()):
                    raise FileExistsError("context.data already exists and is not empty")
                self.workspace_manager.remove("context.data")
            arrays, manifest, target = build_demo(kind)
            self.workspace_manager.create_directory("context.data")
            try:
                for name, value in arrays.items():
                    with self.workspace_manager.open_for_write(
                        f"context.data/{name}.npy", "xb"
                    ) as stream:
                        np.save(stream, value)
                for name, spec in manifest["variables"].items():
                    spec["file"] = f"{name}.npy"
                with self.workspace_manager.open_for_write(
                    "context.data/manifest.json", "x", encoding="utf-8"
                ) as stream:
                    json.dump(manifest, stream, indent=2)
                loaded = load_context_data(path, workspace=self.workspace_manager)
                self.context.commit_context_data(loaded)
                self.context.target = target
            except Exception:
                self.workspace_manager.remove("context.data", recursive=True, missing_ok=True)
                raise
            return path

    def reload_context_data(self):
        """Validate and reload ``context.data/`` from the workspace into the shared :class:`~sr_harness.core.AgentContext`.

        Returns:
            dict[str, Any]: Summary of the reloaded dataset revision and variables.
        """
        with self.lock:
            if self.data_state in {"running", "stopping"}:
                raise ValueError(
                    "Wait for the data-preparation agent to finish before reloading context.data"
                )
            if self.state == "starting":
                raise ValueError("Wait for symbolic regression to reach a controllable boundary")
            control = self.sr_interaction_manager.status()
            if self.state == "running" and not (control["interaction_state"] == "paused"):
                raise ValueError(
                    "Pause symbolic regression and wait for the safe-boundary acknowledgement "
                    "before reloading context.data"
                )
            directory = self.workspace / "context.data"
            if not (directory / "manifest.json").is_file():
                raise ValueError("context.data/manifest.json does not exist")
            change = self.context.commit_context_data(
                load_context_data(
                    directory,
                    workspace=self.workspace_manager,
                )
            )
            self.variable_descriptions = dict(self.context.variable_descriptions)
            return {**change, "context": self.context.schema()}

    def _run(self, X, y, description):
        self.context.args.sr_active = True
        try:
            options = dict(self.settings)
            save_path = options.pop("save_path", str(self.run_dir))
            options.update(
                save_path=save_path,
                run_id=self.run_id,
                use_workspace=True,
            )
            manager = self.sr_interaction_manager
            agent = SRAgentInteractive(
                interaction_manager=manager,
                context=self.context,
                skill_manager=self._capability_skill_manager,
                **options,
            )
            agent.prompt_overrides = self.prompt_overrides.copy()
            agent.variable_descriptions = self.variable_descriptions.copy()
            agent.runtime_settings_supplier = self._take_pending_settings
            agent.runtime_settings_committer = self._commit_runtime_settings
            self.sr_agent = agent
            self.run_state = agent.run_state
            with self.lock:
                self.state = "running"
            agent.initial_messages = manager.start_agent_execution()
            result = agent.run(X, y, description)
        except KeyboardInterrupt as exc:
            result = getattr(exc, "partial_result", {}) | {"status": "interrupted"}
        except Exception as exc:
            _logger.exception("Symbolic-regression Agent failed")
            result = getattr(exc, "partial_result", {}) | {
                "status": "failed",
                "error": str(exc),
            }
        with self.lock:
            self.result = json_value(result)
            self.state = result.get("status", "completed")
            self.context.args.sr_active = False
        manager.publish_event(
            "execution_completed" if self.state != "failed" else "execution_failed",
            {
                "status": self.state,
                "result": self.result,
            },
        )
        if manager.state != "paused":
            manager.finish_agent_execution()

    def _take_pending_settings(self) -> dict[str, Any] | None:
        with self.lock:
            settings = self.pending_settings
            self.pending_settings = None
            return settings

    def _commit_runtime_settings(self, settings: dict[str, Any]) -> None:
        with self.lock:
            self.settings.update(settings)

    @staticmethod
    def validate_settings(payload, initial=False):
        """Validate and coerce a dictionary of symbolic-regression runtime settings.

        Args:
            payload: Raw settings dictionary from the client.
            initial: If ``True``, populate missing fields with default values.

        Returns:
            dict[str, Any]: Validated settings dictionary.
        """
        allowed = set(RUNTIME_SETTING_NAMES)
        bounded_integers = {
            "max_refinement_depth",
            "local_sample_size",
            "global_width",
            "max_restart_loop",
            "restart_top_k",
        }
        nonnegative_integers = {"max_workers"}
        result = {k: v for k, v in payload.items() if k in allowed}
        for k, v in result.items():
            if k in bounded_integers:
                if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 1000:
                    raise ValueError(f"{k} must be an integer between 1 and 1000")
            elif k == "llm_max_tokens":
                if v is not None and (isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 1_000_000):
                    raise ValueError("llm_max_tokens must be null (automatic) or an integer between 1 and 1000000")
            elif k in nonnegative_integers or k == "tool_free_stop_review_rounds":
                if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 1000:
                    raise ValueError(f"{k} must be an integer between 0 and 1000")
            elif k == "split_random_state":
                if isinstance(v, bool) or not isinstance(v, int):
                    raise ValueError("split_random_state must be an integer")
            elif k == "validation_fraction":
                if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v < 1:
                    raise ValueError("validation_fraction must be in [0, 1)")
            elif k in {
                "auto_routing",
                "larger_is_better",
                "force_initial_diagnostics",
                "pause_on_truncated_response",
                "stop_guard_larger_is_better",
            }:
                if not isinstance(v, bool):
                    raise ValueError(f"{k} must be a boolean")
            elif k in {"tools", "skills"}:
                if (
                    not isinstance(v, list)
                    or any(not isinstance(item, str) or not item.strip() for item in v)
                    or len(v) != len(set(v))
                ):
                    raise ValueError(f"{k} must be a list of unique non-empty names")
            elif k in {"strong_llm_provider", "strong_llm_model"}:
                if v is not None and (not isinstance(v, str) or not v.strip()):
                    raise ValueError(f"{k} must be null or a non-empty string")
            elif k == "split_ood_variable":
                if v is not None and (not isinstance(v, str) or not v.strip()):
                    raise ValueError(f"{k} must be null or a non-empty string")
            elif k == "stop_guard_metric":
                if v is not None and (not isinstance(v, str) or not v.strip()):
                    raise ValueError("stop_guard_metric must be null or a non-empty string")
            elif k == "stop_guard_threshold":
                if v is not None and (
                    isinstance(v, bool)
                    or not isinstance(v, (int, float))
                    or not np.isfinite(float(v))
                ):
                    raise ValueError("stop_guard_threshold must be null or a finite number")
            elif not isinstance(v, str) or not v.strip():
                raise ValueError(f"{k} must be non-empty")
        if "llm_provider" in result and result["llm_provider"] not in {
            "openrouter",
            "openai",
            "deepseek",
            "siliconflow",
            "gemini",
            "lmstudio",
        }:
            raise ValueError("Unsupported web model provider")
        if "tool_parser" in result and result["tool_parser"] not in {
            "openai",
            "text",
            "json",
            "xml",
        }:
            raise ValueError("Unsupported tool parser")
        if "split_by" in result and result["split_by"] not in {"random", "ood"}:
            raise ValueError("Unsupported validation split strategy")
        if "stop_guard_mode" in result and result["stop_guard_mode"] not in {
            "none",
            "best_in_topk",
            "metric_threshold",
            "budget_exhausted",
        }:
            raise ValueError("Unsupported stop guard mode")
        if "stop_guard_split" in result and result["stop_guard_split"] not in {
            "train",
            "validation",
        }:
            raise ValueError("Unsupported stop guard split")
        return result

    @staticmethod
    def validate_data_agent_settings(payload):
        """Validate and coerce model, proxy, parser, and capability settings for the Data Preparation Agent.

        Args:
            payload: Raw settings dictionary from the client.

        Returns:
            dict[str, Any]: Validated data-agent settings dictionary.
        """
        result = {key: value for key, value in payload.items() if key in DATA_AGENT_SETTING_NAMES}
        for key, value in result.items():
            if key == "llm_max_tokens":
                upper = 1_000_000
                if value is not None and (isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= upper):
                    raise ValueError(f"{key} must be null (automatic) or an integer between 1 and {upper}")
            elif key in {"tools", "skills"}:
                if (
                    not isinstance(value, list)
                    or any(not isinstance(item, str) or not item.strip() for item in value)
                    or len(value) != len(set(value))
                ):
                    raise ValueError(f"{key} must be a list of unique non-empty names")
            elif key == "proxy":
                result[key] = InteractiveSession.validate_proxy(value)
            elif not isinstance(value, str) or not value.strip():
                raise ValueError(f"{key} must be non-empty")
        if "llm_provider" in result and result["llm_provider"] not in PROVIDER_API_KEY_VARIABLES:
            raise ValueError("Unsupported web model provider")
        if "tool_parser" in result and result["tool_parser"] not in {
            "openai",
            "text",
            "json",
            "xml",
        }:
            raise ValueError("Unsupported tool parser")
        return result

    @staticmethod
    def validate_evaluator_agent_settings(payload):
        """Validate and coerce model, proxy, parser, and capability settings for the Evaluator Construction Agent.

        Args:
            payload: Raw settings dictionary from the client.

        Returns:
            dict[str, Any]: Validated evaluator-agent settings dictionary.
        """
        allowed = {
            "llm_provider",
            "llm_model",
            "tool_parser",
            "llm_max_tokens",
            "proxy",
            "tools",
            "skills",
        }
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"Unsupported evaluator-agent settings: {', '.join(sorted(unknown))}")
        return InteractiveSession.validate_data_agent_settings(payload)

    def configure_data_agent(self, payload):
        """Apply or queue updated settings for the Data Preparation Agent.

        Args:
            payload: Settings dictionary submitted from the Data Preparation settings panel.

        Returns:
            dict[str, Any]: Updated session snapshot.
        """
        self._ensure_settings_editable()
        with self.lock:
            settings = self.validate_data_agent_settings(payload)
            self.validate_capabilities(settings, agent="data")
            if "proxy" in settings:
                self.set_proxy(settings["proxy"])
            self.data_agent_settings = {**self.data_agent_settings, **settings}
            if "proxy" in settings:
                self.evaluator_agent_settings["proxy"] = settings["proxy"]
            if self.data_agent is not None:
                self.data_agent.queue_runtime_settings(settings)
        return self.snapshot()

    def test_data_agent_model(self, payload):
        """Test connectivity and tool-calling support for the Data Preparation Agent's model settings.

        Args:
            payload: Candidate data-agent settings to test.

        Returns:
            dict[str, Any]: Test result containing ``ok``, ``accessible``, and ``tool_call_ok``.
        """
        updates = self.validate_data_agent_settings(payload)
        self.validate_capabilities(updates, agent="data")
        settings = {**self.data_agent_settings, **updates}
        return self._test_model(settings, proxy=settings.get("proxy", ""))

    def test_model(self, payload):
        """Test connectivity and tool-calling support for the symbolic-regression agent's model settings.

        Args:
            payload: Candidate symbolic-regression model settings to test.

        Returns:
            dict[str, Any]: Test result containing ``ok``, ``accessible``, and ``tool_call_ok``.
        """
        updates = self.validate_settings(payload, initial=self.state == "idle")
        self.validate_capabilities(updates)
        settings = {**self.settings, **updates}
        self.validate_setting_dependencies(settings)
        return self._test_model(settings)

    def _test_model(self, settings, *, proxy=None):
        """Run the shared plain-response and tool-call model probes."""
        probe_tool = ModelTestTool(context=self.context)
        user_proxy = str(self.data_agent_settings.get("proxy", "")) if proxy is None else proxy
        environment = proxy_environment(
            self.context.args.api_environment,
            user_proxy=user_proxy,
            egress_proxy=self.egress_proxy,
        )
        with self.model_test_lock:
            tool_box = BaseParser.create(settings["tool_parser"], tool_list=[probe_tool])
            api = BaseAPI.create(
                settings["llm_provider"],
                model=settings["llm_model"],
                tool_box=tool_box,
                environment=environment,
            )
            plain_rows = list(
                api(
                    "Reply with exactly SRHARNESS_OK.",
                    n=1,
                    max_tokens=min(settings["llm_max_tokens"] or 64, 64),
                )
            )
            tool_rows = list(
                api(
                    "Call report_model_test with answer set to SRHARNESS_TOOL_OK. "
                    "Use the tool instead of answering in plain text.",
                    n=1,
                    max_tokens=min(settings["llm_max_tokens"] or 128, 128),
                )
            )
        plain_response = plain_rows[0].content if plain_rows else ""
        calls = [call for row in tool_rows for call in row.tool_calls]
        expected_call = next(
            (
                call
                for call in calls
                if call.name == "report_model_test"
                and call.params.get("answer") == "SRHARNESS_TOOL_OK"
            ),
            None,
        )
        accessible = bool(plain_rows)
        tool_call_supported = expected_call is not None
        return {
            "ok": accessible and tool_call_supported,
            "accessible": accessible,
            "plain_response": plain_response,
            "tool_call_supported": tool_call_supported,
            "called_tools": [call.name for call in calls],
        }

    def configure(self, payload):
        """Apply or queue updated runtime settings for the symbolic-regression agent.

        Args:
            payload: Settings dictionary submitted from the Run Settings panel.

        Returns:
            dict[str, Any]: Updated session snapshot.
        """
        self._ensure_settings_editable()
        with self.lock:
            settings = self.validate_settings(payload, initial=self.state == "idle")
            self.validate_capabilities(settings)
            if self.state == "idle":
                updated = {**self.settings, **settings}
                self.validate_setting_dependencies(updated)
                self.settings = updated
                for name in EVALUATOR_CONTEXT_SETTING_NAMES:
                    if name in settings:
                        setattr(self.context.args, name, settings[name])
                if set(settings) & {
                    "validation_fraction",
                    "split_random_state",
                    "split_by",
                    "split_ood_variable",
                }:
                    self.context.invalidate_splits()
            else:
                current = {**self.settings, **(self.pending_settings or {})}
                pending = {key: current.get(key) for key in RUNTIME_SETTING_NAMES}
                pending.update(settings)
                self.validate_setting_dependencies(pending)
                self.pending_settings = pending
        return self.snapshot()

    def _ensure_settings_editable(self) -> None:
        """Reject setting changes after the search has reached a terminal state."""
        with self.lock:
            if self.state not in {"idle", "starting", "running"}:
                raise ValueError("Run has finished")

    def resolve(self, path, *, access: str = "read"):
        """Resolve a workspace-relative path with the requested access permission.

        Args:
            path: Workspace-relative file or directory path.
            access: Requested operation mode (``"read"``, ``"write"``, ``"create"``, or ``"remove"``).

        Returns:
            Path: Validated filesystem path inside the workspace.

        Raises:
            ValueError: If the path is outside the workspace or disallowed by lock/mount rules.
        """
        candidate = self.workspace_manager.resolve(str(path), access=access)
        if candidate is None:
            raise ValueError("Path must stay inside the workspace")
        return candidate
