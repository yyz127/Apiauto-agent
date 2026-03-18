"""API测试用例Agent

核心Agent模块，串联YAML解析、用例生成、用例执行的完整流程。
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from .parser import parse_openapi_file
from .generator import TestCase
from .llm_generator import LLMCaseGenerator
from .endpoint_workflow import generate_validated_cases

logger = logging.getLogger(__name__)


@dataclass
class EndpointReport:
    """单个接口的测试报告"""
    path: str
    method: str
    summary: str
    generation_failed: bool = False
    generation_error: str = ""
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
    generation_failed_endpoints: int = 0
    total_cases: int = 0
    total_passed: int = 0
    total_failed: int = 0
    endpoints: list[EndpointReport] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "yaml_file": self.yaml_file,
            "total_endpoints": self.total_endpoints,
            "generation_failed_endpoints": self.generation_failed_endpoints,
            "total_cases": self.total_cases,
            "total_passed": self.total_passed,
            "total_failed": self.total_failed,
            "pass_rate": f"{self.total_passed / self.total_cases * 100:.1f}%" if self.total_cases else "N/A",
            "endpoints": [
                {
                    "path": ep.path,
                    "method": ep.method,
                    "summary": ep.summary,
                    "generation_failed": ep.generation_failed,
                    "generation_error": ep.generation_error,
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
            f"生成失败接口: {self.generation_failed_endpoints}",
            f"用例总数: {self.total_cases}",
            f"通过: {self.total_passed}  失败: {self.total_failed}",
            f"通过率: {self.total_passed / self.total_cases * 100:.1f}%" if self.total_cases else "无用例",
            "-" * 60,
        ]
        for ep in self.endpoints:
            lines.append(f"\n[{ep.method}] {ep.path} - {ep.summary}")
            if ep.generation_failed:
                lines.append(f"  生成失败: {ep.generation_error}")
                continue
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
        report = agent.run_graph("path/to/openapi.yaml")
        print(report.summary())
    """

    def __init__(
        self,
        mode: str = "mock",
        api_url: str = "",
        timeout: int = 30,
        headers: dict[str, str] | None = None,
        llm_api_url: str = "",
        llm_api_key: str = "",
        llm_model: str = "",
        uuid: str = "",
        env: str = "",
        target_base_url: str = "",
        target_headers: dict[str, str] | None = None,
    ):
        if not llm_api_url:
            raise ValueError("需要提供llm_api_url")

        # 保留原始配置，供 run_graph / generate_only 使用
        self._mode = mode
        self._api_url = api_url
        self._timeout = timeout
        self._headers = headers or {}
        self._llm_api_url = llm_api_url
        self._llm_api_key = llm_api_key
        self._llm_model = llm_model
        self._uuid = uuid
        self._env = env
        self._target_base_url = target_base_url
        self._target_headers = target_headers or {}

        # generate_only 直接使用的实例
        self.llm_generator = LLMCaseGenerator(
            api_url=llm_api_url,
            api_key=llm_api_key,
            model=llm_model,
            timeout=timeout,
        )

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
            all_cases.extend(generate_validated_cases(endpoint, self.llm_generator, case_type=case_type))
        return all_cases

    # ── LangGraph 模式入口 ──

    def run_graph(
        self,
        yaml_file: str | Path,
        endpoint_filter: str | None = None,
        case_type: str = "all",
        human_review: bool = False,
    ) -> TestReport:
        """使用 LangGraph StateGraph 执行完整测试流程。

        当前项目的唯一完整执行入口，通过 LangGraph 图引擎驱动，
        支持条件路由和人工审核回环。
        """
        from .graph import build_graph
        from .state import create_initial_state

        initial_state = create_initial_state(
            yaml_file=str(yaml_file),
            mode=self._mode,
            api_url=self._api_url,
            timeout=self._timeout,
            headers=self._headers,
            endpoint_filter=endpoint_filter or "",
            case_type=case_type,
            human_review=human_review,
            llm_api_url=self._llm_api_url,
            llm_api_key=self._llm_api_key,
            llm_model=self._llm_model,
            uuid=self._uuid,
            env=self._env,
            target_base_url=self._target_base_url,
            target_headers=self._target_headers,
        )

        graph = build_graph()
        final_state = graph.invoke(initial_state)

        report_dict = final_state.get("report", {})
        return self._dict_to_report(report_dict)

    @staticmethod
    def _dict_to_report(d: dict) -> "TestReport":
        """将 graph 输出的 report dict 还原为 TestReport 对象。"""
        report = TestReport(
            yaml_file=d.get("yaml_file", ""),
            total_endpoints=d.get("total_endpoints", 0),
            generation_failed_endpoints=d.get("generation_failed_endpoints", 0),
            total_cases=d.get("total_cases", 0),
            total_passed=d.get("total_passed", 0),
            total_failed=d.get("total_failed", 0),
        )
        for ep_dict in d.get("endpoints", []):
            report.endpoints.append(EndpointReport(
                path=ep_dict["path"],
                method=ep_dict["method"],
                summary=ep_dict.get("summary", ""),
                generation_failed=ep_dict.get("generation_failed", False),
                generation_error=ep_dict.get("generation_error", ""),
                total_cases=ep_dict.get("total_cases", 0),
                normal_cases=ep_dict.get("normal_cases", 0),
                abnormal_cases=ep_dict.get("abnormal_cases", 0),
                passed=ep_dict.get("passed", 0),
                failed=ep_dict.get("failed", 0),
                results=ep_dict.get("results", []),
            ))
        return report
