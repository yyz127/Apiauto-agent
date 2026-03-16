"""API测试用例Agent

核心Agent模块，串联YAML解析、用例生成、用例执行的完整流程。
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .parser import parse_openapi_file, EndpointInfo
from .generator import generate_test_cases, generate_normal_cases, generate_abnormal_cases, TestCase
from .executor import create_executor, BaseExecutor, ExecutionResult

logger = logging.getLogger(__name__)


@dataclass
class EndpointReport:
    """单个接口的测试报告"""
    path: str
    method: str
    summary: str
    total_cases: int = 0
    normal_cases: int = 0
    abnormal_cases: int = 0
    passed: int = 0
    failed: int = 0
    results: list[dict] = field(default_factory=list)


@dataclass
class TestReport:
    """完整测试报告"""
    yaml_file: str
    total_endpoints: int = 0
    total_cases: int = 0
    total_passed: int = 0
    total_failed: int = 0
    endpoints: list[EndpointReport] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "yaml_file": self.yaml_file,
            "total_endpoints": self.total_endpoints,
            "total_cases": self.total_cases,
            "total_passed": self.total_passed,
            "total_failed": self.total_failed,
            "pass_rate": f"{self.total_passed / self.total_cases * 100:.1f}%" if self.total_cases else "N/A",
            "endpoints": [
                {
                    "path": ep.path,
                    "method": ep.method,
                    "summary": ep.summary,
                    "total_cases": ep.total_cases,
                    "normal_cases": ep.normal_cases,
                    "abnormal_cases": ep.abnormal_cases,
                    "passed": ep.passed,
                    "failed": ep.failed,
                    "results": ep.results,
                }
                for ep in self.endpoints
            ],
        }

    def summary(self) -> str:
        lines = [
            "=" * 60,
            f"测试报告: {self.yaml_file}",
            "=" * 60,
            f"接口数量: {self.total_endpoints}",
            f"用例总数: {self.total_cases}",
            f"通过: {self.total_passed}  失败: {self.total_failed}",
            f"通过率: {self.total_passed / self.total_cases * 100:.1f}%" if self.total_cases else "无用例",
            "-" * 60,
        ]
        for ep in self.endpoints:
            lines.append(f"\n[{ep.method}] {ep.path} - {ep.summary}")
            lines.append(f"  正常用例: {ep.normal_cases}, 异常用例: {ep.abnormal_cases}")
            lines.append(f"  通过: {ep.passed}, 失败: {ep.failed}")
            for r in ep.results:
                status = "✓" if r["success"] else "✗"
                lines.append(f"    {status} {r['test_case_name']}")
                if not r["success"] and r.get("error_message"):
                    lines.append(f"      错误: {r['error_message']}")
        lines.append("\n" + "=" * 60)
        return "\n".join(lines)


class ApiTestAgent:
    """API测试用例自动生成与执行Agent。

    使用方法:
        agent = ApiTestAgent(mode="mock")
        report = agent.run("path/to/openapi.yaml")
        print(report.summary())
    """

    def __init__(
        self,
        mode: str = "mock",
        api_url: str = "",
        timeout: int = 30,
        headers: dict[str, str] | None = None,
    ):
        self.executor = create_executor(
            mode=mode,
            api_url=api_url,
            timeout=timeout,
            headers=headers,
        )

    def run(
        self,
        yaml_file: str | Path,
        endpoint_filter: str | None = None,
        case_type: str = "all",
    ) -> TestReport:
        """执行完整流程: 解析YAML -> 生成用例 -> 执行用例 -> 返回报告。

        Args:
            yaml_file: OpenAPI YAML文件路径
            endpoint_filter: 可选，只测试包含该字符串的路径
            case_type: "all", "normal", "abnormal"
        """
        yaml_file = str(yaml_file)
        report = TestReport(yaml_file=yaml_file)

        # 1. 解析YAML
        logger.info(f"解析YAML文件: {yaml_file}")
        endpoints = parse_openapi_file(yaml_file)
        logger.info(f"发现 {len(endpoints)} 个接口")

        # 2. 过滤接口
        if endpoint_filter:
            endpoints = [ep for ep in endpoints if endpoint_filter in ep.path]
            logger.info(f"过滤后剩余 {len(endpoints)} 个接口")

        report.total_endpoints = len(endpoints)

        # 3. 为每个接口生成和执行用例
        for endpoint in endpoints:
            ep_report = self._process_endpoint(endpoint, case_type)
            report.endpoints.append(ep_report)
            report.total_cases += ep_report.total_cases
            report.total_passed += ep_report.passed
            report.total_failed += ep_report.failed

        return report

    def _process_endpoint(self, endpoint: EndpointInfo, case_type: str) -> EndpointReport:
        """处理单个接口：生成用例并执行。"""
        logger.info(f"\n处理接口: [{endpoint.method}] {endpoint.path}")

        # 生成用例
        if case_type == "normal":
            cases = generate_normal_cases(endpoint)
        elif case_type == "abnormal":
            cases = generate_abnormal_cases(endpoint)
        else:
            cases = generate_test_cases(endpoint)

        normal_count = sum(1 for c in cases if c.case_type == "normal")
        abnormal_count = sum(1 for c in cases if c.case_type == "abnormal")
        logger.info(f"生成用例: {len(cases)} 个 (正常: {normal_count}, 异常: {abnormal_count})")

        # 执行用例
        results = self.executor.execute_batch(cases)

        # 统计结果
        ep_report = EndpointReport(
            path=endpoint.path,
            method=endpoint.method,
            summary=endpoint.summary,
            total_cases=len(cases),
            normal_cases=normal_count,
            abnormal_cases=abnormal_count,
            passed=sum(1 for r in results if r.success),
            failed=sum(1 for r in results if not r.success),
            results=[r.to_dict() for r in results],
        )

        return ep_report

    def generate_only(
        self,
        yaml_file: str | Path,
        endpoint_filter: str | None = None,
        case_type: str = "all",
    ) -> list[TestCase]:
        """只生成用例不执行，返回用例列表。"""
        endpoints = parse_openapi_file(yaml_file)
        if endpoint_filter:
            endpoints = [ep for ep in endpoints if endpoint_filter in ep.path]

        all_cases = []
        for endpoint in endpoints:
            if case_type == "normal":
                cases = generate_normal_cases(endpoint)
            elif case_type == "abnormal":
                cases = generate_abnormal_cases(endpoint)
            else:
                cases = generate_test_cases(endpoint)
            all_cases.extend(cases)
        return all_cases
