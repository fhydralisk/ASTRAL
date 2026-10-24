# Copyright (c) 2024-present, Yumeow. Licensed under the MIT License.
import logging
from copy import deepcopy
from openai import AzureOpenAI, DefaultHttpxClient
from openai.types.responses import Response
from openai.types.chat import ChatCompletion
from collections import defaultdict
from typing import Any, Generator, List, Dict
from .base_api import BaseAPI, ProgressCallback
from ..core import APICallSample, ToolCall

_logger = logging.getLogger(f"sr_harness.{__name__}")


@BaseAPI.register("openai")
class OpenAIAPI(BaseAPI):
    """LLM provider adapter for OpenAI and Azure OpenAI models (supporting both Responses and Chat Completions APIs)."""

    def __init__(self, model: str = "gpt-5-mini", **kwargs: Any) -> None:
        """Initialize the OpenAI / Azure OpenAI adapter.

        Args:
            model: OpenAI deployment or model name (defaults to ``"gpt-5-mini"``).
            **kwargs: Additional arguments forwarded to :class:`BaseAPI`.
        """
        super().__init__(model=model, **kwargs)
        self.dummy_message = 'Please proofread the message above and say "I have received it."'

    def cancel(self) -> str:
        """Request cancellation and note that in-flight synchronous OpenAI SDK calls cannot be preempted mid-request.

        Returns:
            str: Human-readable notice describing cancellation behavior.
        """
        return (
            "OpenAIAPI does not support force-interrupting an active non-streaming request. "
            "The Agent will pause at its next safe boundary."
        )

    def format_response(
        self, message: Any, tool_calls: list[ToolCall], content: str | None = None
    ) -> APICallSample:
        """Convert an OpenAI Responses or Chat Completions message into an :class:`~sr_harness.core.APICallSample`.

        Args:
            message: Provider response item or message dictionary.
            tool_calls: Normalized tool calls extracted from the response.
            content: Optional explicit text content override.

        Returns:
            APICallSample: Normalized assistant response sample.
        """
        if hasattr(message, "to_dict"):
            message = message.to_dict()
        elif hasattr(message, "model_dump"):
            message = message.model_dump()
        elif not isinstance(message, dict):
            raise TypeError(f"Unsupported OpenAI message type: {type(message).__name__}")
        return self._build_response(message, tool_calls, content)

    @property
    def model_list(self) -> list[str]:
        """Return the OpenAI / Azure OpenAI model identifiers supported by this adapter.

        Returns:
            list[str]: Supported model names.
        """
        return ["gpt-4o-mini", "gpt-5-mini"]

    def _request_samples(
        self,
        messages: List[Dict[str, str]],
        n=1,
        max_tokens=None,
        temperature=1.0,
        top_p=1.0,
        use_chat_completions=False,
        callback: ProgressCallback | None = None,
    ) -> Generator[APICallSample, None, dict[str, Any]]:
        """
        Keyword Args:
            model (str): The model name to use. Default is 'gpt-4o-mini'.
            max_tokens (int): The maximum number of tokens to generate. Default is 1024.
            temperature (float): Sampling temperature. Default is 1.0.
            top_p (float): Nucleus sampling probability. Default is 1.0.
            n (int): Number of completions to generate. Default is 1.
        """
        if self.model == "gpt-4o-mini" and not use_chat_completions:
            use_chat_completions = True
            _logger.warning(
                "Turn to use create_chat_completions for gpt-4o-mini model to save token cost."
            )

        if use_chat_completions:
            results = yield from self.create_chat_completions(
                messages,
                n=n,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                callback=callback,
            )
            return results
        else:
            results = yield from self.create_responses(
                messages,
                n=n,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                callback=callback,
            )
            return results

    def build_native_tool_description(self, use_chat_completions: bool = False) -> List[Dict]:
        """Format enabled tools into the schema structure expected by OpenAI's Responses or Chat Completions API.

        Args:
            use_chat_completions: If ``True``, return Chat Completions ``{"type": "function", "function": ...}``
                entries; if ``False``, return flattened Responses API tool definitions.

        Returns:
            List[Dict]: List of OpenAI tool schema dictionaries.
        """
        tools = self.tool_box.format_tools()
        if not isinstance(tools, list):
            raise TypeError("Native tool parser must return JSON tool descriptions")
        if use_chat_completions:
            return tools
        return [
            {
                "type": "function",
                "name": tool["function"]["name"],
                "description": tool["function"].get("description", ""),
                "parameters": tool["function"].get(
                    "parameters", {"type": "object", "properties": {}}
                ),
            }
            for tool in tools
        ]

    def create_responses(
        self,
        messages: List[Dict[str, str]],
        n: int = 1,
        max_tokens: int | None = None,
        temperature: float = 1.0,
        top_p: float = 1.0,
        callback: ProgressCallback | None = None,
    ) -> Generator[APICallSample, None, dict[str, Any]]:
        """Sample completions using the OpenAI ``responses.create`` API (used for reasoning models such as ``gpt-5-mini``).

        Args:
            messages: Conversation messages in OpenAI format.
            n: Number of independent samples to request.
            max_tokens: Optional maximum output token limit.
            temperature: Sampling temperature.
            top_p: Nucleus sampling probability threshold.
            callback: Optional progress callback.

        Yields:
            APICallSample: Normalized response samples as they complete.

        Returns:
            dict[str, Any]: Aggregated token usage, cost, and status summary.
        """
        ## Ensure this is a generator
        yield from []
        client = AzureOpenAI(
            api_version=self.get_env("OPENAI_API_VERSION", required=True),
            azure_endpoint=(endpoint := self.get_env("OPENAI_ENDPOINT", required=True)),
            api_key=self.get_env("OPENAI_API_KEY", required=True),
            http_client=DefaultHttpxClient(
                proxy=self.proxy_url(endpoint),
                trust_env=False,
            ),
        )
        payload = {
            "input": deepcopy(messages),  # 因为后面可能要 pop, 所以 deepcopy 一下
            "reasoning": {"summary": "auto"},
            "model": self.model,
            "top_p": top_p,
            **({"max_output_tokens": max_tokens} if max_tokens is not None else {}),
            "temperature": temperature,
            # "prompt_cache_retention": "24h"  # 官网上说有这个参数可以延长 cache 保存时间，但实际用起来会报错
            # "n": n,  # OpenAI Response API 不支持 parameter n
        }
        if self.tool_box is None:
            pass
        elif not self.tool_box.native_tool_calls:
            description = (
                "Use the following tools when a tool call is needed. "
                "Return tool calls in the specified format.\n\n"
                f"{self.tool_box.format_tools()}"
            )
            if payload["input"][0]["role"] in {"system", "developer"}:
                first = payload["input"][0]
                payload["input"][0] = {
                    **first,
                    "content": f"{first['content']}\n\n{description}",
                }
            else:
                payload["input"].insert(0, {"role": "system", "content": description})
        else:
            payload["tools"] = self.build_native_tool_description()
            payload["tool_choice"] = "auto"
        if payload["input"][0]["role"] == "system":
            ## instruction 无法在多轮对话中保留，不好用
            # payload['instructions'] = payload['input'].pop(0)['content']
            ## 改用据说效果与 instruction 等价的 developer 角色
            payload["input"][0]["role"] = "developer"

        if n == 1:
            self.report_progress(callback, {"type": "start", "sample": 1})
            try:
                response = client.responses.create(**payload)
                response_dict = response.to_dict()
                usage = self.parse_usage(response)
                message_object = response.choices[0].message
                message = (
                    message_object.to_dict()
                    if hasattr(message_object, "to_dict")
                    else message_object.model_dump()
                )
                content = response.output_text
                tool_call = self.parse_tool_calls(message, content)
                sample_response = self.format_response(message, tool_call, content)
                if callback is not None:
                    self.report_progress(callback, {
                        "type": "complete",
                        "sample": 1,
                        "content": sample_response.content,
                        "reasoning": sample_response.reasoning,
                        "tool_calls": [call.raw for call in sample_response.tool_calls],
                    })
                yield sample_response
                results = {
                    "ok": True,
                    "error": None,
                    "token_usage": usage.get("token", {}),
                    "money_usage": usage.get("price", {}),
                    "extra": {"responses": [response_dict]},
                }
            except InterruptedError:
                raise
            except Exception as e:
                public_error = self.error_message(e)
                self.report_progress(callback, {
                    "type": "failed",
                    "sample": 1,
                    "error": public_error,
                })
                return {
                    "ok": False,
                    "error": public_error,
                    "token_usage": {},
                    "money_usage": {},
                    "extra": {},
                }
            return results
        else:
            self.report_progress(callback, {"type": "start", "sample": 1})
            try:
                responses = []
                details = []
                ## 构造 payload 将除最后一条 message 之外的所有前置信息输入模型
                assert payload["input"][-1]["role"] == "user", (
                    "When n > 1, the last message must be from user."
                )
                last_message = payload["input"].pop(-1)
                payload["input"].append({"role": "user", "content": self.dummy_message})
                response = client.responses.create(**payload)
                usage = self.parse_usage(response)
                responses.append(response)
                ## 构造 child payload 多次输入最后一条 message 以获得多条回复并尽量增加 cached input token 的命中率
                child_payload = deepcopy(payload)
                child_payload["previous_response_id"] = response.id
                child_payload["input"] = [last_message]
                for idx in range(1, n + 1):
                    child_response = client.responses.create(**child_payload)
                    responses.append(child_response)
                    child_response_dict = child_response.to_dict()
                    message = child_response.choices[0].message.to_dict()
                    content = message["content"]
                    tool_call = self.parse_tool_calls(message, content)
                    sample_response = self.format_response(message, tool_call, content)
                    if callback is not None:
                        self.report_progress(callback, {
                            "type": "complete",
                            "sample": idx,
                            "content": sample_response.content,
                            "reasoning": sample_response.reasoning,
                            "tool_calls": [call.raw for call in sample_response.tool_calls],
                        })
                        if idx < n:
                            self.report_progress(callback, {
                                "type": "start",
                                "sample": idx + 1,
                            })
                    yield sample_response
                    new_usage = self.parse_usage(child_response)
                    for k, v in new_usage["token"].items():
                        usage["token"][k] = usage["token"].get(k, 0) + v
                    for k, v in new_usage["price"].items():
                        usage["price"][k] = usage["price"].get(k, 0) + v
                    details.append(
                        {
                            "content": content,
                            "tool_call": tool_call,
                            "token_usage": dict(new_usage.get("token", {})),
                            "price_usage": dict(new_usage.get("price", {})),
                            "response": child_response_dict,
                        }
                    )
                results = {
                    "ok": True,
                    "error": None,
                    "token_usage": usage.get("token", {}),
                    "money_usage": usage.get("price", {}),
                    "extra": {"responses": [resp.to_dict() for resp in responses]},
                }
            except InterruptedError:
                raise
            except Exception as e:
                public_error = self.error_message(e)
                self.report_progress(callback, {
                    "type": "failed",
                    "sample": min(len(details) + 1, n),
                    "error": public_error,
                })
                return {
                    "ok": False,
                    "error": public_error,
                    "token_usage": {},
                    "money_usage": {},
                    "extra": {},
                }
            return results

    def create_chat_completions(
        self,
        messages: List[Dict[str, str]],
        n: int = 1,
        max_tokens: int | None = None,
        temperature: float = 1.0,
        top_p: float = 1.0,
        callback: ProgressCallback | None = None,
    ) -> Generator[APICallSample, None, dict[str, Any]]:
        """Sample completions using the standard OpenAI ``chat.completions.create`` API.

        Args:
            messages: Conversation messages in OpenAI format.
            n: Number of independent samples to request.
            max_tokens: Optional maximum output token limit.
            temperature: Sampling temperature.
            top_p: Nucleus sampling probability threshold.
            callback: Optional progress callback.

        Yields:
            APICallSample: Normalized response samples as they complete.

        Returns:
            dict[str, Any]: Aggregated token usage, cost, and status summary.
        """
        ## Ensure this is a generator
        yield from []
        client = AzureOpenAI(
            api_version=self.get_env("OPENAI_API_VERSION", required=True),
            azure_endpoint=(endpoint := self.get_env("OPENAI_OLDTIME_ENDPOINT", required=True)),
            api_key=self.get_env("OPENAI_API_KEY", required=True),
            http_client=DefaultHttpxClient(
                proxy=self.proxy_url(endpoint),
                trust_env=False,
            ),
        )
        payload = {
            "messages": deepcopy(messages),
            "n": n,
            "model": (model := self.model),
            "top_p": top_p,
            **({"max_tokens": max_tokens} if max_tokens is not None else {}),
            "temperature": temperature,
        }
        if self.tool_box is None:
            pass
        elif not self.tool_box.native_tool_calls:
            description = (
                "Use the following tools when a tool call is needed. "
                "Return tool calls in the specified format.\n\n"
                f"{self.tool_box.format_tools()}"
            )
            if payload["messages"][0]["role"] in {"system", "developer"}:
                first = payload["messages"][0]
                payload["messages"][0] = {
                    **first,
                    "content": f"{first['content']}\n\n{description}",
                }
            else:
                payload["messages"].insert(0, {"role": "system", "content": description})
        else:
            tools = self.tool_box.format_tools()
            if not isinstance(tools, list):
                raise TypeError("Native tool parser must return JSON tool descriptions")
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        assert model == "gpt-4o-mini", "Only gpt-4o-mini model is supported in chat_completions."

        self.report_progress(callback, {"type": "start", "sample": 1})
        try:
            response = client.chat.completions.create(**payload)
            details = []
            for idx, choice in enumerate(response.choices, 1):
                response_dict = {"choices": [{"message": choice.message.to_dict()}]}
                message = choice.message.to_dict()
                content = message["content"]
                truncated = getattr(choice, "finish_reason", None) == "length"
                if truncated:
                    message.pop("tool_calls", None)
                tool_call = [] if truncated else self.parse_tool_calls(message, content)
                details.append(
                    {
                        "content": content,
                        "tool_call": tool_call,
                        "token_usage": {},
                        "price_usage": {},
                        "response": response_dict,
                    }
                )
                sample_response = self.format_response(message, tool_call, content)
                sample_response.finish_reason = getattr(choice, "finish_reason", None)
                if callback is not None:
                    self.report_progress(callback, {
                        "type": "complete",
                        "sample": idx,
                        "content": sample_response.content,
                        "reasoning": sample_response.reasoning,
                        "tool_calls": [call.raw for call in sample_response.tool_calls],
                    })
                    if idx < len(response.choices):
                        self.report_progress(callback, {
                            "type": "start",
                            "sample": idx + 1,
                        })
                yield sample_response
            usage = self.parse_chat_completions_usage(response)
            for detail in details:
                detail["token_usage"] = dict(usage.get("token", {}))
                detail["price_usage"] = dict(usage.get("price", {}))
            results = {
                "ok": True,
                "error": None,
                "token_usage": usage.get("token", {}),
                "money_usage": usage.get("price", {}),
                "extra": {"responses": [response.to_dict()]},
            }
        except InterruptedError:
            raise
        except Exception as e:
            public_error = self.error_message(e)
            self.report_progress(callback, {
                "type": "failed",
                "sample": 1,
                "error": public_error,
            })
            return {
                "ok": False,
                "error": public_error,
                "token_usage": {},
                "money_usage": {},
                "extra": {},
            }
        return results

    def parse_usage(self, response: Response) -> Dict:
        """Extract token counts and estimated USD cost from an OpenAI Responses API result.

        Args:
            response: OpenAI ``Response`` object.

        Returns:
            Dict: Dictionary containing ``token_usage`` and ``money_usage`` breakdowns.
        """
        usage = {"token": defaultdict(float), "price": defaultdict(float)}
        if response.model.startswith("gpt-5-mini"):
            usage["token"]["cached"] = (
                cached_tokens := response.usage.input_tokens_details.cached_tokens
            )
            usage["token"]["prompt"] = (
                prompt_tokens := response.usage.input_tokens - cached_tokens
            )
            usage["token"]["reason"] = (
                reason_tokens := response.usage.output_tokens_details.reasoning_tokens
            )
            usage["token"]["answer"] = (
                answer_tokens := response.usage.output_tokens - reason_tokens
            )
            if (
                other := response.usage.total_tokens
                - cached_tokens
                - prompt_tokens
                - reason_tokens
                - answer_tokens
            ) != 0:
                usage["token"]["other"] = other
            usage["price"]["cached"] = 0.025 * cached_tokens / 1e6
            usage["price"]["prompt"] = 0.25 * prompt_tokens / 1e6
            usage["price"]["reason"] = 2.0 * reason_tokens / 1e6
            usage["price"]["answer"] = 2.0 * answer_tokens / 1e6
        elif response.model.startswith("gpt-4o-mini"):
            cached_tokens = 0
            usage["token"]["prompt"] += (prompt_tokens := response.usage.prompt_tokens)
            usage["token"]["reason"] += (
                reason_tokens := response.usage.completion_tokens_details.reasoning_tokens
            )
            usage["token"]["answer"] += (
                answer_tokens := response.usage.completion_tokens - reason_tokens
            )
            if (
                other := response.usage.total_tokens
                - cached_tokens
                - prompt_tokens
                - reason_tokens
                - answer_tokens
            ) != 0:
                usage["token"]["other"] = other
            usage["price"]["prompt"] += 0.15 * prompt_tokens / 1e6
            usage["price"]["reason"] += 0.60 * reason_tokens / 1e6
            usage["price"]["answer"] += 0.60 * answer_tokens / 1e6
        else:
            raise NotImplementedError(
                f"Usage parsing for model {response.model} is not implemented."
            )
        return usage

    def parse_chat_completions_usage(self, response: ChatCompletion) -> Dict:
        """Extract token counts and estimated USD cost from an OpenAI ``ChatCompletion`` result.

        Args:
            response: OpenAI ``ChatCompletion`` object.

        Returns:
            Dict: Dictionary containing ``token_usage`` and ``money_usage`` breakdowns.
        """
        usage = {"token": defaultdict(float), "price": defaultdict(float)}
        if response.model.startswith("gpt-4o-mini"):
            usage["token"]["prompt"] += (prompt_tokens := response.usage.prompt_tokens)
            usage["token"]["reason"] += (
                reason_tokens := response.usage.completion_tokens_details.reasoning_tokens
            )
            usage["token"]["answer"] += (
                answer_tokens := response.usage.completion_tokens - reason_tokens
            )
            if (
                other := response.usage.total_tokens - prompt_tokens - reason_tokens - answer_tokens
            ) > 0:
                usage["token"]["other"] = other
            usage["price"]["prompt"] += 0.15 * prompt_tokens / 1e6
            usage["price"]["reason"] += 0.60 * reason_tokens / 1e6
            usage["price"]["answer"] += 0.60 * answer_tokens / 1e6
        else:
            raise NotImplementedError(
                f"Usage parsing for model {response.model} is not implemented."
            )
        return usage
