# Copyright (c) 2026-present, Yumeow. Licensed under the MIT License.
from __future__ import annotations

import tempfile
import re
from dataclasses import dataclass
from logging import getLogger
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, Callable, Iterable

import yaml

if TYPE_CHECKING:
    from ..runtime.workspace import Workspace

_logger = getLogger(f"sr_harness.{__name__}")


@dataclass(frozen=True)
class Skill:
    """Metadata describing a built-in, tool-generated, or user-defined runtime skill.

    Attributes:
        name: Unique skill identifier.
        description: Brief summary used for skill discovery.
        readonly: Whether modifying the skill's files at runtime is disallowed.
        skill_directory: Filesystem path to the directory containing ``SKILL.md``.
    """
    name: str
    description: str
    readonly: bool
    skill_directory: Path


class SkillManager:
    """Registry that discovers, searches, reads, and updates built-in, tool, and custom skills."""

    def __init__(
        self,
        built_in_directory: str | Path | None = None,
        custom_directory: str | Path | None = None,
        workspace: Workspace | None = None,
    ):
        """Initialize the skill manager with built-in and optional custom skill directories.

        Args:
            built_in_directory: Directory containing built-in packaged skills.
            custom_directory: Directory where user-created or agent-created skills are stored.
            workspace: Optional :class:`~sr_harness.runtime.Workspace` enforcing safe file access.
        """
        package_directory = Path(__file__).parent
        runtime_directory = Path(tempfile.mkdtemp(prefix="sr_agent_runtime_skills_"))
        self.skill_directories: dict[str, Path] = {
            "built-in": Path(built_in_directory or package_directory),
            "runtime": runtime_directory,
            "custom": (
                Path(custom_directory)
                if custom_directory is not None
                else runtime_directory / "custom"
            ),
        }
        self.workspace = workspace

    def register_tool_docs(self, tool_cls_list: Iterable[type]) -> None:
        """Generate read-only reference skills from the docstrings and source code of enabled tools.

        Args:
            tool_cls_list: Iterable of :class:`~sr_harness.tools.BaseTool` subclasses.
        """
        for tool_cls in tool_cls_list:
            doc = tool_cls.get_doc()
            if doc is None:
                continue
            if not isinstance(doc, dict):
                raise TypeError(f"{tool_cls.__name__}.get_doc() must return a dict or None.")
            if set(doc) != {"name", "description", "content"}:
                raise ValueError(
                    f"{tool_cls.__name__}.get_doc() must return exactly name, description, and content."
                )
            if not all(isinstance(doc[key], str) and doc[key].strip() for key in doc):
                raise ValueError(f"{tool_cls.__name__}.get_doc() values must be non-empty strings.")
            name = self._validate_name(doc["name"])
            if name in self.load_skills():
                raise ValueError(f"Skill {name!r} is already registered.")
            content = self._format_skill_file(
                name=name,
                description=doc["description"].strip(),
                readonly=True,
                body=doc["content"].strip(),
            )
            skill_dir = self.skill_directories["runtime"] / name
            skill_dir.mkdir(parents=True, exist_ok=False)
            (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

    def load_tool_skills(self) -> list[tuple[Skill, str]]:
        """Return all registered tool-documentation skills paired with their Python source code.

        Returns:
            list[tuple[Skill, str]]: List of ``(Skill, python_source)`` pairs.
        """
        loaded = []
        for skill in self.load_skills().values():
            path = skill.skill_directory / "tool.py"
            if path.is_file():
                opener = self._skill_opener(skill)
                with opener(path, "r", encoding="utf-8") as f:
                    loaded.append((skill, f.read()))
        return loaded

    def load_skills(self) -> dict[str, Skill]:
        """Scan all configured skill directories and return a mapping of available skills by name.

        Returns:
            dict[str, Skill]: Mapping from skill name to :class:`Skill` metadata.
        """
        skills: dict[str, Skill] = {}
        for scope, root in self.skill_directories.items():
            for skill_path in sorted(root.glob("*/SKILL.md")):
                opener = (
                    self.workspace.safe_open
                    if scope == "custom" and self.workspace is not None
                    else open
                )
                with opener(skill_path, "r", encoding="utf-8") as f:
                    text = f.read()
                metadata, _ = self._parse_skill_text(text, skill_path)
                name = str(metadata.get("name", "")).strip()
                description = str(metadata.get("description", "")).strip()
                if not name:
                    _logger.warning(f"Skill file '{skill_path}' is missing frontmatter field: name, skip it")
                    continue
                if not description:
                    _logger.warning(f"Skill file '{skill_path}' is missing frontmatter field: description, skip it")
                    continue
                if name != skill_path.parent.name:
                    _logger.warning(
                        f"Skill name {name!r} in {skill_path!r} does not match directory name "
                        f"{skill_path.parent.name!r}; use {name!r} as the skill name"
                    )
                if name in skills:
                    raise ValueError(f"Skill {name!r} is provided by more than one skill directory.")
                readonly = scope != "custom" or self._as_bool(metadata.get("readonly", False))
                skills[name] = Skill(name, description, readonly, skill_path.parent.absolute())
        return skills

    def get_skill(self, name: str) -> Skill:
        """Look up a single skill by name.

        Args:
            name: Registered skill name.

        Returns:
            Skill: Matching skill metadata object.

        Raises:
            KeyError: If no skill with ``name`` exists.
        """
        skills = self.load_skills()
        if name in skills:
            return skills[name]
        available = ", ".join(skills)
        raise ValueError(f"Skill '{name}' not found. Available skills: {available}")

    def search_skills(self, query: str, limit: int = 5) -> list[Skill]:
        """Search available skills by keyword overlap against skill names and descriptions.

        Args:
            query: Free-text search query.
            limit: Maximum number of matching skills to return.

        Returns:
            list[Skill]: Top matching skills ordered by relevance.
        """
        tokens = set(re.findall(r"[a-zA-Z][\w-]+|[\u4e00-\u9fff]{2,}", query.lower()))
        ranked = []
        for skill in self.load_skills().values():
            pattern = r"[a-zA-Z][\w-]+|[\u4e00-\u9fff]{2,}"
            name_tokens = set(re.findall(pattern, skill.name.lower().replace("-", " ")))
            desc_tokens = set(re.findall(pattern, skill.description.lower()))
            score = 3 * len(tokens & name_tokens) + len(tokens & desc_tokens)
            ranked.append((score, skill.name, skill))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        matches = [skill for score, _, skill in ranked if score > 0]
        return matches[:max(1, min(int(limit), 20))]

    def read_skill(self, name: str, file_path: str = "SKILL.md") -> str:
        """Read a markdown or supporting text file from a skill directory.

        Args:
            name: Registered skill name.
            file_path: Relative path inside the skill directory (defaults to ``"SKILL.md"``).

        Returns:
            str: UTF-8 text content of the requested skill file.
        """
        skill = self.get_skill(name)
        path = self._resolve_skill_file(skill, file_path)
        if not path.is_file():
            raise ValueError(f"Skill file not found: {file_path}")
        with self._skill_opener(skill)(path, "r", encoding="utf-8") as f:
            return f.read()

    def get_skill_tree(self, name: str) -> list[str]:
        """List all relative file paths inside a skill's directory.

        Args:
            name: Registered skill name.

        Returns:
            list[str]: Sorted list of relative file paths belonging to the skill.
        """
        skill_dir = self.get_skill(name).skill_directory
        return [
            path.relative_to(skill_dir).as_posix() + ("/" if path.is_dir() else "")
            for path in sorted(skill_dir.rglob("*"))
            if "__pycache__" not in path.parts
            and not (path.is_file() and path.suffix in {".pyc", ".pyo"})
        ]

    def set_skill(
        self,
        name: str,
        content: str,
        file_path: str = "SKILL.md",
        force: bool = False,
    ) -> Skill:
        """Create a new custom skill or update a file inside an editable custom skill.

        Args:
            name: Target skill name.
            content: UTF-8 text content to write.
            file_path: Relative file path inside the skill directory (defaults to ``"SKILL.md"``).
            force: Whether to allow overwriting an existing file.

        Returns:
            Skill: Updated :class:`Skill` metadata object.
        """
        name = self._validate_name(name)
        skills = self.load_skills()
        skill = skills.get(name)
        if skill is None:
            if file_path != "SKILL.md":
                raise ValueError("A new skill must be created by writing SKILL.md first.")
            skill_dir = self.skill_directories["custom"] / name
        else:
            if skill.readonly:
                raise ValueError(f"Skill '{name}' is read-only and cannot be overwritten.")
            skill_dir = skill.skill_directory

        target = self._resolve_path(skill_dir, file_path)
        workspace_relative = None
        if self.workspace is not None:
            try:
                workspace_relative = target.relative_to(self.workspace.path)
            except ValueError:
                pass
        if workspace_relative is not None:
            resolved = self.workspace.resolve(str(workspace_relative))
            target_exists = resolved is not None and resolved.exists()
        else:
            target_exists = target.exists()
        if target_exists and not force:
            raise ValueError(f"Skill file '{name}/{file_path}' already exists. Use force=True to replace it.")
        if file_path == "SKILL.md":
            metadata, _ = self._parse_skill_text(content, target)
            declared_name = str(metadata.get("name", "")).strip()
            description = str(metadata.get("description", "")).strip()
            if declared_name != name:
                raise ValueError(f"SKILL.md name {declared_name!r} must match {name!r}.")
            if not description:
                raise ValueError("SKILL.md frontmatter must contain a non-empty description.")

        if workspace_relative is not None:
            self.workspace.create_directory(
                str(workspace_relative.parent),
                parents=True,
                exist_ok=True,
            )
            with self.workspace.open_for_write(
                str(workspace_relative),
                "w" if force else "x",
                encoding="utf-8",
            ) as stream:
                stream.write(content)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        return self.get_skill(name)

    def _skill_opener(self, skill: Skill) -> Callable[..., IO]:
        custom_directory = self.skill_directories["custom"].absolute()
        if self.workspace is not None and skill.skill_directory.is_relative_to(custom_directory):
            return self.workspace.safe_open
        return open

    @staticmethod
    def _validate_name(name: str) -> str:
        name = name.strip()
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
            raise ValueError(f"Invalid skill name: {name!r}.")
        return name

    @classmethod
    def _resolve_skill_file(cls, skill: Skill, file_path: str) -> Path:
        return cls._resolve_path(skill.skill_directory, file_path)

    @staticmethod
    def _resolve_path(skill_dir: Path, file_path: str) -> Path:
        relative = Path(file_path or "SKILL.md")
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("file_path must be relative and stay inside the skill directory.")
        return skill_dir / relative

    @staticmethod
    def _parse_skill_text(text: str, path: Path) -> tuple[dict[str, Any], str]:
        normalized = text.strip()
        if not normalized.startswith("---\n"):
            raise ValueError(f"Skill file '{path}' must start with YAML frontmatter")
        try:
            _, frontmatter, _ = normalized.split("---\n", 2)
        except ValueError as exc:
            raise ValueError(f"Skill file '{path}' has invalid YAML frontmatter") from exc
        try:
            metadata = yaml.safe_load(frontmatter.strip()) or {}
        except yaml.YAMLError as exc:
            raise ValueError(f"Skill file '{path}' has invalid YAML frontmatter") from exc
        if not isinstance(metadata, dict):
            raise ValueError(
                f"Failed to parse frontmatter in skill file '{path}', expected a YAML mapping "
                f"but got {type(metadata).__name__}"
            )
        return metadata, normalized

    @staticmethod
    def _as_bool(value: Any) -> bool:
        return str(value).lower().strip() in {"true", "yes", "1", "on"}

    @staticmethod
    def _format_skill_file(*, name: str, description: str, readonly: bool, body: str) -> str:
        metadata = yaml.safe_dump(
            {"name": name, "description": description, "readonly": readonly},
            sort_keys=False,
            allow_unicode=True,
        )
        return f"---\n{metadata}---\n\n{body}\n"
