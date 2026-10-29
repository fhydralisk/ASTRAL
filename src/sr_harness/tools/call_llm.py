# Copyright (c) 2026-present, Yumeow. Licensed under the MIT License.
"""Auxiliary tool for querying an external LLM provider directly."""

from typing import Dict, Any, List
from ..service.environment import tool_environment
from .base_tool import BaseTool, ToolMetadata


# @BaseTool.register('call_llm') # 不注册这个工具，因为它用处不大
class LLMTool(BaseTool):
    """Tool for querying a configured LLM provider and returning its response text and usage."""
    metadata = ToolMetadata(name="call_llm")

    def execute(
        self,
        llm_provider: str,
        llm_model: str,
        messages: List[Dict[str, str]] | str,
    ) -> Dict[str, Any]:
        """Send a prompt or chat message list to an LLM provider and return the completion.

        Args:
            llm_provider: Provider identifier, e.g., ``"openai"``, ``"deepseek"``, or ``"gemini"``.
            llm_model: Model identifier, e.g., ``"gpt-4o-mini"`` or ``"deepseek-chat"``.
            messages: Prompt string or list of ``{"role": "user"|"assistant", "content": "..."}`` dicts.

        Returns:
            Dict[str, Any]: Dictionary containing ``content``, ``token_usage``, and ``money_usage``.
        """
        from ..api import BaseAPI

        api = BaseAPI.create(llm_provider, model=llm_model, environment=tool_environment(self))
        content = ""
        for response in (llm_result := api(messages, n=1)):
            content = response.content or ""
        return {
            "content": content,
            "token_usage": llm_result.token_usage,
            "money_usage": llm_result.money_usage,
        }
