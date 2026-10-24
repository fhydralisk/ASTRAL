# Copyright (c) 2026-present, Yumeow. Licensed under the MIT License.
from typing import Any, Dict, List, Tuple
from .base_tool import BaseTool, ToolMetadata


@BaseTool.register("edit_skill")
class EditSkill(BaseTool):
    """Tool for patching an existing editable ``SKILL.md`` file with exact SEARCH/REPLACE blocks."""
    metadata = ToolMetadata(name="edit_skill")
    SEARCH_MARKER = "<<<<<<< SEARCH"
    SEPARATOR_MARKER = "======="
    REPLACE_MARKER = ">>>>>>> REPLACE"

    def execute(self, name: str, patch: str) -> Dict[str, Any]:
        """Update an editable skill's ``SKILL.md`` using exact ``SEARCH/REPLACE`` blocks.

        Use this tool when concrete evidence from the current run refines or corrects an existing
        skill. Prefer small, generalizable edits; never hard-code dataset-specific constants or
        unverified guesses into a reusable skill.

        Args:
            name: Exact name of the editable skill to modify.
            patch: One or more ``<<<<<<< SEARCH ... ======= ... >>>>>>> REPLACE`` blocks where each SEARCH section matches ``SKILL.md`` exactly once.

        Returns:
            Dict[str, Any]: Counts of requested and applied replacements plus any match warnings.
        """
        name = name.strip()
        replacements = self._parse_patch(patch)
        assert hasattr(self.context.args, "skill_manager"), "skill_manager must be provided in context.args."
        manager = self.context.args.skill_manager
        if name not in manager.load_skills():
            raise ValueError(f"Skill '{name}' does not exist and cannot be edited.")
        elif manager.get_skill(name).readonly:
            raise ValueError(f"Skill '{name}' is read-only and cannot be edited.")
        else:
            old_content = manager.read_skill(name)
            new_content, exceptions = self._apply_replacements(old_content, replacements)
            manager.set_skill(name, new_content, force=True)
            return {
                "skill": name,
                "requested_replacements": len(replacements),
                "applied_replacements": len(replacements) - len(exceptions),
                "exceptions": exceptions,
            }

    @classmethod
    def format_result_dict(cls, result: Dict[str, Any]) -> str:
        """Format the skill patch summary and any replacement warnings for the Agent.

        Args:
            result: Result dictionary returned by :meth:`execute`.

        Returns:
            str: Summary of applied replacements and warnings.
        """
        text = (
            f"Edited skill {result['skill']!r}: "
            f"Detected {result['requested_replacements']} requested replacements, "
            f"applied {result['applied_replacements']} replacements."
        )
        if result["exceptions"]:
            text += "\nExceptions: " + "; ".join(result["exceptions"])
        return text

    def _parse_patch(self, patch: str) -> List[Tuple[str, str]]:
        lines = patch.splitlines(keepends=True)

        index = 0
        replacements = []
        while index < len(lines):
            if not lines[index].strip():
                index += 1
                continue
            if lines[index].strip() != self.SEARCH_MARKER:
                raise ValueError(
                    f"Expected {self.SEARCH_MARKER!r} at line {index + 1}, "
                    f"got {lines[index].strip()!r}."
                )

            index += 1
            old_lines = []
            while index < len(lines) and lines[index].strip() != self.SEPARATOR_MARKER:
                old_lines.append(lines[index])
                index += 1
            if index >= len(lines):
                raise ValueError(f"Missing {self.SEPARATOR_MARKER!r} marker in patch.")

            index += 1
            new_lines = []
            while index < len(lines) and lines[index].strip() != self.REPLACE_MARKER:
                new_lines.append(lines[index])
                index += 1
            if index >= len(lines):
                raise ValueError(f"Missing {self.REPLACE_MARKER!r} marker in patch.")

            index += 1
            old_text = "".join(old_lines)
            new_text = "".join(new_lines)
            if not old_text:
                raise ValueError("SEARCH block cannot be empty.")
            replacements.append((old_text, new_text))

        if not replacements:
            raise ValueError("Patch must contain at least one SEARCH/REPLACE block.")

        return replacements

    def _apply_replacements(self, content: str, replacements: List[Tuple[str, str]]) -> Tuple[str, List[str]]:
        exceptions = []
        for old_text, new_text in replacements:
            if (count := content.count(old_text)) == 0:
                exceptions.append(
                    f"SEARCH text {old_text!r} was not found in "
                    f"the skill file, skip this replacement."
                )
            elif count > 1:
                exceptions.append(
                    f"SEARCH text {old_text!r} matched more than "
                    f"once. Include more surrounding context."
                )
            else:
                content = content.replace(old_text, new_text, 1)
        return content, exceptions
