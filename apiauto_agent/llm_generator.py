"""基于大模型的测试用例生成器。"""

import json
import logging
import re
from typing import Any

import requests

from .generator import TestCase
from .parser import EndpointInfo

logger = logging.getLogger(__name__)


class CaseGenerationError(Exception):
    """LLM 用例生成失败。"""

# ── 系统提示词 ──

SYSTEM_PROMPT = """\
你是一位资深 API 测试工程师，精通接口测试方法论（等价类划分、边界值分析、错误推测法、安全测试）。

你的任务是根据提供的 API 接口定义，生成高质量、高覆盖率的测试用例。

## 输出格式要求
必须输出 **纯 JSON 数组**（不要包裹在 markdown 代码块中），数组中每个元素包含：
- name: 用例名称，格式为 "[正常/异常] {METHOD} {PATH} - 简短描述"
- description: 用例说明，解释测试意图
- case_type: "normal" 或 "abnormal"
- parameters: 请求参数字典（key-value），只包含需要发送的参数
- headers: 请求头字典（key-value），包含 Content-Type 和认证头
- expected_status: 期望的 HTTP 状态码（整数）

## 正常用例覆盖策略（case_type="normal"）
1. **必填参数用例**：只传所有必填参数，使用合理的有效值
2. **全参数用例**：传所有参数（必填+可选），使用合理的有效值
3. **枚举遍历**：若参数有 enum 约束，为每个枚举值生成独立用例
4. **边界值（合法端）**：数值参数取 minimum 和 maximum；字符串参数取 minLength 和 maxLength

## 异常用例覆盖策略（case_type="abnormal"）
1. **缺少必填参数**：逐一移除每个必填参数，期望 400
2. **类型错误**：整数参数传字符串、字符串参数传数字等，期望 400
3. **空值/null**：必填参数传 null 或空字符串，期望 400
4. **越界值**：数值低于 minimum、高于 maximum；字符串超过 maxLength，期望 400/422
5. **格式错误**：email 参数传非邮箱、date 参数传非日期等，期望 400/422
6. **枚举外值**：enum 参数传不在枚举列表中的值，期望 400/422
7. **安全测试**：XSS 注入 (<script>alert(1)</script>)、SQL 注入 (' OR 1=1 --)，期望 400
8. **极端值**：超大整数 (2147483648)、超长字符串 (1000+字符)、负数，期望 400

## 认证与请求头
- 如果接口定义了安全认证要求（如 API Key、Bearer Token、Cookie 等），必须在每个用例的 headers 中包含对应的认证头
- 认证头的值使用占位符格式：`<请输入{认证类型}>`，例如 `"Authorization": "Bearer <请输入Token>"`、`"Cookie": "XingheToken=<请输入Token>"`
- 所有用例的 headers 至少包含 `Content-Type`

## 注意事项
- 每个用例的 parameters 必须是可直接发送的参数字典
- path 参数（如 {petId}）也需要包含在 parameters 中
- expected_status 应基于 API 定义中的 responses 信息推断
- 用例名称和描述使用中文
- 生成的用例应尽量避免重复场景\
"""


class LLMCaseGenerator:
    """调用OpenAI兼容接口生成测试用例。"""

    def __init__(
        self,
        api_url: str,
        api_key: str = "",
        model: str = "",
        timeout: int = 60,
        max_retries: int = 2,
    ):
        self.api_url = api_url
        self.api_key = api_key
        self.model = model or "gpt-4o-mini"
        self.timeout = timeout
        self.max_retries = max_retries

    def generate_cases(self, endpoint: EndpointInfo, case_type: str = "all") -> list[TestCase]:
        if case_type not in {"all", "normal", "abnormal"}:
            raise ValueError(f"不支持的case_type: {case_type}")
        return self.generate_cases_with_feedback(endpoint, case_type=case_type, review_feedback="")

    def generate_cases_with_feedback(
        self,
        endpoint: EndpointInfo,
        case_type: str = "all",
        review_feedback: str = "",
    ) -> list[TestCase]:
        if case_type not in {"all", "normal", "abnormal"}:
            raise ValueError(f"不支持的case_type: {case_type}")

        prompt = self._build_prompt(endpoint, case_type, review_feedback=review_feedback)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        last_error = None
        for attempt in range(1, self.max_retries + 1):
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
                    logger.warning("LLM返回内容为空 (第%d次尝试)", attempt)
                    last_error = "LLM返回内容为空"
                    continue
                raw_cases = self._extract_json(content)
                cases = self._to_test_cases(raw_cases, endpoint)
                if not cases:
                    logger.warning("LLM返回JSON为空数组 (第%d次尝试)", attempt)
                    last_error = "LLM返回空数组"
                    continue
                logger.info("LLM生成 %d 个用例 (第%d次尝试)", len(cases), attempt)
                return cases
            except (requests.RequestException, json.JSONDecodeError, ValueError, KeyError, IndexError, TypeError) as e:
                logger.warning("LLM生成用例失败 (第%d次尝试): %s", attempt, e)
                last_error = str(e)

        error_message = last_error or "LLM未返回有效用例"
        logger.error("LLM生成用例最终失败，共尝试%d次，最后错误: %s", self.max_retries, error_message)
        raise CaseGenerationError(error_message)

    def _build_prompt(self, endpoint: EndpointInfo, case_type: str, review_feedback: str = "") -> str:
        # 构建参数信息，过滤掉 None 值以减少 token 消耗
        params_desc = []
        for p in endpoint.parameters:
            param = {"name": p.name, "location": p.location, "required": p.required, "type": p.param_type}
            if p.format:
                param["format"] = p.format
            if p.enum:
                param["enum"] = p.enum
            if p.minimum is not None:
                param["minimum"] = p.minimum
            if p.maximum is not None:
                param["maximum"] = p.maximum
            if p.min_length is not None:
                param["minLength"] = p.min_length
            if p.max_length is not None:
                param["maxLength"] = p.max_length
            if p.pattern:
                param["pattern"] = p.pattern
            if p.example is not None:
                param["example"] = p.example
            if p.default is not None:
                param["default"] = p.default
            if p.description:
                param["description"] = p.description
            params_desc.append(param)

        # 构建响应状态码信息
        responses_desc = {}
        if endpoint.responses:
            for code, detail in endpoint.responses.items():
                desc = detail.get("description", "") if isinstance(detail, dict) else str(detail)
                responses_desc[str(code)] = desc

        endpoint_desc = {
            "path": endpoint.path,
            "method": endpoint.method,
            "summary": endpoint.summary,
            "description": endpoint.description,
            "parameters": params_desc,
        }
        if responses_desc:
            endpoint_desc["responses"] = responses_desc

        # 构建安全认证信息
        if endpoint.security and endpoint.security_schemes:
            security_desc = []
            for sec_req in endpoint.security:
                for scheme_name in sec_req:
                    scheme = endpoint.security_schemes.get(scheme_name, {})
                    if scheme:
                        security_desc.append({
                            "name": scheme_name,
                            "type": scheme.get("type", ""),
                            "scheme": scheme.get("scheme", ""),
                            "in": scheme.get("in", ""),
                            "paramName": scheme.get("name", ""),
                            "description": scheme.get("description", ""),
                        })
            if security_desc:
                endpoint_desc["security"] = security_desc

        # 构建用户提示词
        case_type_instruction = {
            "all": "请同时生成正常用例和异常用例，确保全面覆盖。",
            "normal": "请只生成正常用例（case_type=\"normal\"），覆盖所有正常使用场景。",
            "abnormal": "请只生成异常用例（case_type=\"abnormal\"），覆盖各类错误输入场景。",
        }

        prompt = (
            f"请为以下 API 接口生成测试用例。\n\n"
            f"**生成要求**: {case_type_instruction[case_type]}\n\n"
            f"**接口定义**:\n```json\n{json.dumps(endpoint_desc, ensure_ascii=False, indent=2)}\n```"
        )
        if review_feedback.strip():
            prompt += (
                "\n\n"
                "### 人工审核反馈\n"
                "以下是上一轮生成结果的人工审核问题，请严格根据这些问题修正并重新生成完整用例集：\n"
                f"{review_feedback.strip()}\n"
            )
        return prompt

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
                headers=item.get("headers", {}) or {},
                expected_status=item.get("expected_status"),
            ))
        return test_cases
