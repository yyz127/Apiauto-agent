"""基于大模型的测试用例生成器。"""

import json
import logging
import re
from typing import Any

import requests

from .generator import TestCase
from .parser import EndpointInfo

logger = logging.getLogger(__name__)


class LLMCaseGenerator:
    """调用OpenAI兼容接口生成测试用例。"""

    def __init__(
        self,
        api_url: str,
        api_key: str = "",
        model: str = "",
        timeout: int = 30,
    ):
        self.api_url = api_url
        self.api_key = api_key
        self.model = model or "gpt-4o-mini"
        self.timeout = timeout

    def generate_cases(self, endpoint: EndpointInfo, case_type: str = "all") -> list[TestCase]:
        if case_type not in {"all", "normal", "abnormal"}:
            raise ValueError(f"不支持的case_type: {case_type}")

        prompt = self._build_prompt(endpoint, case_type)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是资深API测试工程师。仅返回JSON数组，不要返回markdown代码块。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            resp = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content:
                logger.warning("LLM返回内容为空")
                return []
            raw_cases = self._extract_json(content)
            return self._to_test_cases(raw_cases, endpoint)
        except (requests.RequestException, json.JSONDecodeError, ValueError, KeyError, IndexError, TypeError) as e:
            logger.warning("LLM生成用例失败: %s", e)
            return []

    def _build_prompt(self, endpoint: EndpointInfo, case_type: str) -> str:
        endpoint_desc = {
            "path": endpoint.path,
            "method": endpoint.method,
            "summary": endpoint.summary,
            "description": endpoint.description,
            "parameters": [
                {
                    "name": p.name,
                    "location": p.location,
                    "required": p.required,
                    "param_type": p.param_type,
                    "format": p.format,
                    "enum": p.enum,
                    "minimum": p.minimum,
                    "maximum": p.maximum,
                    "min_length": p.min_length,
                    "max_length": p.max_length,
                    "pattern": p.pattern,
                    "example": p.example,
                    "default": p.default,
                }
                for p in endpoint.parameters
            ],
        }

        return (
            f"请为以下接口生成测试用例，case_type={case_type}。\n"
            "要求覆盖正常与异常场景（按case_type裁剪），每个用例输出字段："
            "name, description, case_type(normal/abnormal), parameters(dict), expected_status(int)。\n"
            "输出必须是JSON数组。\n"
            f"接口信息: {json.dumps(endpoint_desc, ensure_ascii=False)}"
        )

    @staticmethod
    def _extract_json(content: str) -> list[dict[str, Any]]:
        content = content.strip()
        # 兼容```json ...```和纯JSON两种格式
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, flags=re.DOTALL | re.IGNORECASE)
        if match:
            content = match.group(1).strip()

        data = json.loads(content)
        if not isinstance(data, list):
            raise ValueError("LLM返回格式错误，期望JSON数组")
        return data

    @staticmethod
    def _to_test_cases(raw_cases: list[dict[str, Any]], endpoint: EndpointInfo) -> list[TestCase]:
        test_cases = []
        for item in raw_cases:
            test_cases.append(TestCase(
                name=item.get("name", f"[LLM] {endpoint.method} {endpoint.path}"),
                description=item.get("description", ""),
                endpoint_path=endpoint.path,
                method=endpoint.method,
                case_type=item.get("case_type", "normal"),
                parameters=item.get("parameters", {}) or {},
                expected_status=item.get("expected_status"),
            ))
        return test_cases
