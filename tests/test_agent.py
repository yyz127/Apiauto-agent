"""ApiTestAgent 对外接口测试。"""

from pathlib import Path

import pytest

from apiauto_agent.agent import ApiTestAgent
from apiauto_agent.generator import (
    TestCase,
    generate_abnormal_cases,
    generate_normal_cases,
    generate_test_cases,
)
from apiauto_agent.llm_generator import CaseGenerationError
from apiauto_agent.parser import parse_openapi_file

EXAMPLE_YAML = str(Path(__file__).parent.parent / "examples" / "petstore.yaml")


def _mock_llm_generate(endpoint, case_type="all", review_feedback=""):
    """稳定返回规则生成结果，避免真实 LLM 依赖。"""
    if case_type == "normal":
        return generate_normal_cases(endpoint)
    if case_type == "abnormal":
        return generate_abnormal_cases(endpoint)
    return generate_test_cases(endpoint)


def test_parse_openapi():
    """解析示例 YAML。"""
    endpoints = parse_openapi_file(EXAMPLE_YAML)
    assert len(endpoints) == 5
    assert endpoints[0].path == "/pets"
    assert endpoints[0].method == "GET"


def test_agent_requires_llm_url():
    """Agent 初始化要求提供 llm_api_url。"""
    with pytest.raises(ValueError, match="llm_api_url"):
        ApiTestAgent(mode="mock")


def test_agent_generate_only(monkeypatch):
    """generate_only 只生成，不执行。"""
    agent = ApiTestAgent(mode="mock", llm_api_url="http://mock-llm.local/v1/chat/completions")
    monkeypatch.setattr(agent.llm_generator, "generate_cases_with_feedback", _mock_llm_generate)

    cases = agent.generate_only(EXAMPLE_YAML, endpoint_filter="/pets/{petId}", case_type="normal")

    assert len(cases) > 0
    assert all(case.case_type == "normal" for case in cases)
    assert all(case.endpoint_path == "/pets/{petId}" for case in cases)


def test_agent_generate_only_generation_failure(monkeypatch):
    """generate_only 在生成失败时直接抛错，不吞异常。"""
    agent = ApiTestAgent(mode="mock", llm_api_url="http://mock-llm.local/v1/chat/completions")

    def _raise_generation_error(endpoint, case_type="all", review_feedback=""):
        raise CaseGenerationError("LLM返回空数组")

    monkeypatch.setattr(agent.llm_generator, "generate_cases_with_feedback", _raise_generation_error)

    with pytest.raises(CaseGenerationError, match="LLM返回空数组"):
        agent.generate_only(EXAMPLE_YAML)


def test_agent_run_graph_mock(monkeypatch):
    """run_graph 在 mock 模式下返回完整报告。"""
    agent = ApiTestAgent(mode="mock", llm_api_url="http://mock-llm.local/v1/chat/completions")
    monkeypatch.setattr(
        "apiauto_agent.nodes.LLMCaseGenerator",
        lambda **kwargs: type(
            "MockLLM",
            (),
            {"generate_cases_with_feedback": staticmethod(_mock_llm_generate)},
        )(),
    )

    report = agent.run_graph(EXAMPLE_YAML)

    assert report.total_endpoints == 5
    assert report.total_cases > 0
    assert report.total_failed == 0


def test_agent_filter_endpoint_run_graph(monkeypatch):
    """run_graph 支持接口过滤。"""
    agent = ApiTestAgent(mode="mock", llm_api_url="http://mock-llm.local/v1/chat/completions")
    monkeypatch.setattr(
        "apiauto_agent.nodes.LLMCaseGenerator",
        lambda **kwargs: type(
            "MockLLM",
            (),
            {"generate_cases_with_feedback": staticmethod(_mock_llm_generate)},
        )(),
    )

    report = agent.run_graph(EXAMPLE_YAML, endpoint_filter="/pets/{petId}")

    assert report.total_endpoints == 3
    assert all(endpoint.path == "/pets/{petId}" for endpoint in report.endpoints)


def test_agent_case_type_filter_run_graph(monkeypatch):
    """run_graph 支持按用例类型过滤。"""
    agent = ApiTestAgent(mode="mock", llm_api_url="http://mock-llm.local/v1/chat/completions")
    monkeypatch.setattr(
        "apiauto_agent.nodes.LLMCaseGenerator",
        lambda **kwargs: type(
            "MockLLM",
            (),
            {"generate_cases_with_feedback": staticmethod(_mock_llm_generate)},
        )(),
    )

    report = agent.run_graph(EXAMPLE_YAML, case_type="abnormal")

    assert report.total_endpoints == 5
    assert all(endpoint.normal_cases == 0 for endpoint in report.endpoints)
    assert report.total_cases > 0


def test_report_summary_run_graph(monkeypatch):
    """run_graph 结果可输出文本摘要。"""
    agent = ApiTestAgent(mode="mock", llm_api_url="http://mock-llm.local/v1/chat/completions")
    monkeypatch.setattr(
        "apiauto_agent.nodes.LLMCaseGenerator",
        lambda **kwargs: type(
            "MockLLM",
            (),
            {"generate_cases_with_feedback": staticmethod(_mock_llm_generate)},
        )(),
    )

    report = agent.run_graph(EXAMPLE_YAML)
    summary = report.summary()

    assert "测试报告" in summary
    assert "接口数量: 5" in summary
    assert "生成失败接口: 0" in summary


def test_report_to_dict_run_graph(monkeypatch):
    """run_graph 结果可序列化为 dict。"""
    agent = ApiTestAgent(mode="mock", llm_api_url="http://mock-llm.local/v1/chat/completions")
    monkeypatch.setattr(
        "apiauto_agent.nodes.LLMCaseGenerator",
        lambda **kwargs: type(
            "MockLLM",
            (),
            {"generate_cases_with_feedback": staticmethod(_mock_llm_generate)},
        )(),
    )

    report = agent.run_graph(EXAMPLE_YAML)
    data = report.to_dict()

    assert data["yaml_file"] == EXAMPLE_YAML
    assert data["total_endpoints"] == 5
    assert isinstance(data["endpoints"], list)
    assert len(data["endpoints"]) == 5


def test_agent_run_graph_marks_generation_failure(monkeypatch):
    """run_graph 在 LLM 生成失败时返回接口级失败报告。"""
    agent = ApiTestAgent(mode="mock", llm_api_url="http://mock-llm.local/v1/chat/completions")

    def _raise_generation_error(endpoint, case_type="all", review_feedback=""):
        raise CaseGenerationError("LLM返回空数组")

    monkeypatch.setattr(
        "apiauto_agent.nodes.LLMCaseGenerator",
        lambda **kwargs: type(
            "MockLLM",
            (),
            {"generate_cases_with_feedback": staticmethod(_raise_generation_error)},
        )(),
    )

    report = agent.run_graph(EXAMPLE_YAML, case_type="normal")

    assert report.total_endpoints == 5
    assert report.generation_failed_endpoints == 5
    assert report.total_cases == 0
    assert all(endpoint.generation_failed for endpoint in report.endpoints)


def test_agent_run_graph_marks_case_check_failure(monkeypatch):
    """run_graph 在生成结果不合法时也标记为生成失败。"""
    agent = ApiTestAgent(mode="mock", llm_api_url="http://mock-llm.local/v1/chat/completions")

    def _invalid_cases(endpoint, case_type="all", review_feedback=""):
        return [
            TestCase(
                name="bad-case",
                description="wrong case type",
                endpoint_path=endpoint.path,
                method=endpoint.method,
                case_type="abnormal",
                parameters={},
                headers={},
                expected_status=400,
            )
        ]

    monkeypatch.setattr(
        "apiauto_agent.nodes.LLMCaseGenerator",
        lambda **kwargs: type(
            "MockLLM",
            (),
            {"generate_cases_with_feedback": staticmethod(_invalid_cases)},
        )(),
    )

    report = agent.run_graph(EXAMPLE_YAML, case_type="normal")

    assert report.generation_failed_endpoints == 5
    assert all(endpoint.generation_failed for endpoint in report.endpoints)
    assert all("类型与请求不一致" in endpoint.generation_error for endpoint in report.endpoints)
