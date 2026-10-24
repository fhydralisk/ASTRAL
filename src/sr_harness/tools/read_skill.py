# Copyright (c) 2026-present, Yumeow. Licensed under the MIT License.
from typing import Any, Dict
from dataclasses import replace
from xml.sax.saxutils import escape
from ..skills import Skill, SkillManager
from ..core import AgentContext
from .base_tool import BaseTool, ToolMetadata


def _format_description(skills: Dict[str, Skill]) -> str:
    skill_blocks = []
    for skill in skills.values():
        skill_blocks.append(
            f"  <skill>\n"
            f"    <name>{escape(skill.name)}</name>\n"
            f"    <description>\n"
            f"      {escape(skill.description)}\n"
            f"    </description>\n"
            f"  </skill>"
        )
    return (
        "Read a skill's instructions (`SKILL.md`), inspect its files, or search available skills.\n\n"
        "Skills provide domain workflows, syntax references, and reusable tactics. Call this tool "
        "whenever your task matches one of the skill descriptions below.\n\n"
        "Available skills:\n\n"
        "<skills>\n" + "\n\n".join(skill_blocks) + "\n</skills>"
    )


@BaseTool.register("read_skill")
class ReadSkill(BaseTool):
    """Tool for reading skill instructions (``SKILL.md``), auxiliary skill files, or searching skills."""

    default_skill_manager = SkillManager()
    metadata = ToolMetadata(
        name="read_skill",
        description=_format_description(default_skill_manager.load_skills()),
    )

    def __init__(self, context: AgentContext | None = None) -> None:
        """Initialize the tool and filter advertised skills to those enabled in ``context.args``.

        Args:
            context: Runtime :class:`AgentContext` supplying ``skill_manager`` and ``enabled_skills``.
        """
        super().__init__(context=context)
        if hasattr(self.context.args, "skill_manager"):
            self.skill_manager = self.context.args.skill_manager
            if not isinstance(self.skill_manager, SkillManager):
                raise TypeError("context.args.skill_manager must be a SkillManager")
        else:
            self.skill_manager = self.default_skill_manager
        enabled = getattr(self.context.args, "enabled_skills", None)
        skills = self.skill_manager.load_skills()
        self.enabled_skills = set(enabled) if enabled is not None else set(skills)
        description = _format_description({
            name: skill for name, skill in skills.items() if name in self.enabled_skills
        })
        self.metadata = replace(type(self).metadata, description=description)

    def execute(
        self,
        name: str = "",
        file_path: str = "",
        show_tree: bool = False,
        query: str = "",
    ) -> Dict[str, Any]:
        """Read a skill's ``SKILL.md``, read a specific file inside a skill, or search skills by query.

        Args:
            name: Exact skill name to read. Leave empty when searching with ``query``.
            file_path: Optional path relative to the skill directory (e.g., ``"tool.py"`` or ``"references/guide.md"``). Reads ``SKILL.md`` when empty.
            show_tree: Whether to include a listing of all files in the skill directory.
            query: Keyword or task description used to rank matching skills when ``name`` is empty.

        Returns:
            Dict[str, Any]: XML-wrapped skill content, optional directory tree, or ranked skill matches.
        """
        if not name.strip():
            if not query.strip():
                raise ValueError("Provide either an exact skill name or a search query.")
            matches = [
                skill for skill in self.skill_manager.search_skills(query)
                if skill.name in self.enabled_skills
            ][:5]
            return {
                "content": "Recommended skills:\n" + "\n".join(
                    f"- {skill.name}: {skill.description}" for skill in matches
                ),
                "matches": [skill.name for skill in matches],
            }
        if name not in self.skill_manager.load_skills():
            self.skill_manager.get_skill(name)
        if name not in self.enabled_skills:
            raise ValueError(f"Skill '{name}' is not enabled for this Agent.")
        skill = self.skill_manager.get_skill(name)
        result: dict[str, Any] = {}
        if file_path.strip():
            relative_path = file_path.strip()
            file_content = self.skill_manager.read_skill(name, relative_path)
            result.update(file_path=relative_path, file_content=file_content)
            result["content"] = (
                f'<skill_content name="{escape(skill.name)}" file="{escape(relative_path)}">\n'
                f"{file_content}\n</skill_content>"
            )
        else:
            content = self.skill_manager.read_skill(name)
            result["content"] = f'<skill_content name="{escape(skill.name)}">\n{content}\n</skill_content>'
        if show_tree:
            result["tree"] = self.skill_manager.get_skill_tree(name)
        return result

    @classmethod
    def format_result_dict(cls, result: Dict[str, Any]) -> str:
        """Format the skill content and optional directory tree for the Agent.

        Args:
            result: Result dictionary returned by :meth:`execute`.

        Returns:
            str: Skill content followed by optional directory tree entries.
        """
        text = [result["content"]]
        if "tree" in result:
            text.extend(["", "Skill directory tree:", *[f"- {path}" for path in result["tree"]]])
        return "\n".join(text)
