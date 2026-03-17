"""接口A调用模块

负责将生成的测试用例发送到接口A执行。
提供Mock模式和真实模式两种实现。
"""

import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import requests

from .generator import TestCase

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """测试用例执行结果"""
    test_case_name: str
    case_type: str
    success: bool
    status_code: int | None = None
    response_body: Any = None
    error_message: str = ""
    duration_ms: float = 0

    def to_dict(self) -> dict:
        return {
            "test_case_name": self.test_case_name,
            "case_type": self.case_type,
            "success": self.success,
            "status_code": self.status_code,
            "response_body": self.response_body,
            "error_message": self.error_message,
            "duration_ms": self.duration_ms,
        }


class BaseExecutor(ABC):
    """执行器基类"""

    @abstractmethod
    def execute(self, test_case: TestCase) -> ExecutionResult:
        """执行单个测试用例。"""

    def execute_batch(self, test_cases: list[TestCase]) -> list[ExecutionResult]:
        """批量执行测试用例。"""
        results = []
        for tc in test_cases:
            logger.info(f"执行用例: {tc.name}")
            result = self.execute(tc)
            results.append(result)
            status = "✓ 通过" if result.success else "✗ 失败"
            logger.info(f"  结果: {status} (HTTP {result.status_code}, {result.duration_ms:.0f}ms)")
        return results


class MockExecutor(BaseExecutor):
    """Mock模式执行器

    模拟接口A的行为，不需要真实服务。
    适合开发和测试阶段使用。
    """

    def execute(self, test_case: TestCase) -> ExecutionResult:
        start = time.time()

        # 模拟处理时间
        time.sleep(0.01)

        if test_case.case_type == "normal":
            # 正常用例模拟成功
            result = ExecutionResult(
                test_case_name=test_case.name,
                case_type=test_case.case_type,
                success=True,
                status_code=200,
                response_body={"code": 0, "message": "success", "data": {"id": 1}},
                duration_ms=(time.time() - start) * 1000,
            )
        else:
            # 异常用例模拟返回预期的错误码
            expected = test_case.expected_status or 400
            result = ExecutionResult(
                test_case_name=test_case.name,
                case_type=test_case.case_type,
                success=True,  # 异常用例返回预期错误码也算"通过"
                status_code=expected,
                response_body={"code": expected, "message": "参数错误"},
                duration_ms=(time.time() - start) * 1000,
            )

        return result


class ApiExecutor(BaseExecutor):
    """真实接口A执行器

    将测试用例发送到接口A（POST /report/generatAutotestReport）执行。
    请求格式适配 Java 端 ReportGenerateRequest：
      { url, header(JSON字符串), param(JSON字符串列表), uuid, env }
    """

    def __init__(
        self,
        api_url: str,
        timeout: int = 30,
        headers: dict[str, str] | None = None,
        uuid: str = "",
        env: str = "",
        target_base_url: str = "",
        target_headers: dict[str, str] | None = None,
    ):
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout
        self.uuid = uuid
        self.env = env
        self.target_base_url = target_base_url.rstrip("/")
        self.target_headers = target_headers or {}
        self.session = requests.Session()
        if headers:
            self.session.headers.update(headers)

    def _build_target_url(self, test_case: TestCase) -> str:
        """拼接目标接口的完整 URL。"""
        return f"{self.target_base_url}{test_case.endpoint_path}"

    def execute(self, test_case: TestCase) -> ExecutionResult:
        start = time.time()

        # 构建接口A期望的 ReportGenerateRequest 格式
        target_url = self._build_target_url(test_case)
        # 合并请求头：先放测试用例的 headers，再用 CLI 传入的 target_headers 覆盖
        # 确保 Cookie/Token 等认证头始终保留（CLI 输入优先级最高）
        merged_headers = dict(test_case.headers) if test_case.headers else {}
        merged_headers.update(self.target_headers)
        header_json = json.dumps(merged_headers, ensure_ascii=False)
        param_json = json.dumps(test_case.parameters, ensure_ascii=False, default=str)

        payload = {
            "url": target_url,
            "header": header_json,
            "param": [param_json],
            "uuid": self.uuid,
            "env": self.env,
        }

        try:
            resp = self.session.post(
                self.api_url,
                json=payload,
                timeout=self.timeout,
            )
            duration = (time.time() - start) * 1000
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text

            return ExecutionResult(
                test_case_name=test_case.name,
                case_type=test_case.case_type,
                success=resp.status_code < 500,
                status_code=resp.status_code,
                response_body=body,
                duration_ms=duration,
            )
        except requests.RequestException as e:
            duration = (time.time() - start) * 1000
            return ExecutionResult(
                test_case_name=test_case.name,
                case_type=test_case.case_type,
                success=False,
                error_message=str(e),
                duration_ms=duration,
            )


def create_executor(
    mode: str = "mock",
    api_url: str = "",
    timeout: int = 30,
    headers: dict[str, str] | None = None,
    uuid: str = "",
    env: str = "",
    target_base_url: str = "",
    target_headers: dict[str, str] | None = None,
) -> BaseExecutor:
    """工厂方法，根据模式创建对应的执行器。"""
    if mode == "mock":
        return MockExecutor()
    elif mode == "api":
        if not api_url:
            raise ValueError("真实模式需要提供api_url参数")
        return ApiExecutor(
            api_url=api_url,
            timeout=timeout,
            headers=headers,
            uuid=uuid,
            env=env,
            target_base_url=target_base_url,
            target_headers=target_headers,
        )
    else:
        raise ValueError(f"不支持的模式: {mode}，可选: mock, api")
