"""测试Agent核心功能"""

import json
from pathlib import Path
from unittest.mock import patch

from apiauto_agent.parser import parse_openapi_file
from apiauto_agent.generator import generate_test_cases, generate_normal_cases, generate_abnormal_cases
from apiauto_agent.agent import ApiTestAgent

EXAMPLE_YAML = Path(__file__).parent.parent / "examples" / "petstore.yaml"

# 使用一个假的 LLM URL，测试中会 mock 掉实际的 LLM 调用
MOCK_LLM_URL = "http://mock-llm.local/v1/chat/completions"


def _make_agent(**kwargs):
    """创建一个带 mock LLM 的 Agent 实例。"""
    defaults = {
        "mode": "mock",
        "llm_api_url": MOCK_LLM_URL,
    }
    defaults.update(kwargs)
    return ApiTestAgent(**defaults)


def _mock_llm_generate(endpoint, case_type="all"):
    """模拟 LLM 生成用例，实际调用规则引擎以确保测试稳定。"""
    if case_type == "normal":
        return generate_normal_cases(endpoint)
    if case_type == "abnormal":
        return generate_abnormal_cases(endpoint)
    return generate_test_cases(endpoint)


def test_parse_openapi():
    """测试OpenAPI解析"""
    endpoints = parse_openapi_file(EXAMPLE_YAML)
    assert len(endpoints) > 0
    assert len(endpoints) == 5
    methods = {(ep.method, ep.path) for ep in endpoints}
    assert ("GET", "/pets") in methods
    assert ("POST", "/pets") in methods
    assert ("DELETE", "/pets/{petId}") in methods


def test_agent_run_mock(monkeypatch):
    """测试Agent完整流程（Mock模式）"""
    agent = _make_agent()
    monkeypatch.setattr(agent.llm_generator, "generate_cases", _mock_llm_generate)

    report = agent.run(EXAMPLE_YAML)
    assert report.total_endpoints == 5
    assert report.total_cases > 0
    assert report.total_passed > 0
    assert report.total_failed == 0


def test_agent_generate_only(monkeypatch):
    """测试只生成用例"""
    agent = _make_agent()
    monkeypatch.setattr(agent.llm_generator, "generate_cases", _mock_llm_generate)

    cases = agent.generate_only(EXAMPLE_YAML)
    assert len(cases) > 0
    for c in cases:
        d = c.to_dict()
        assert "name" in d
        assert "parameters" in d
        json.dumps(d, ensure_ascii=False, default=str)


def test_agent_filter_endpoint(monkeypatch):
    """测试接口过滤"""
    agent = _make_agent()
    monkeypatch.setattr(agent.llm_generator, "generate_cases", _mock_llm_generate)

    report = agent.run(EXAMPLE_YAML, endpoint_filter="/pets/{petId}")
    assert report.total_endpoints == 3


def test_agent_case_type_filter(monkeypatch):
    """测试用例类型过滤"""
    agent = _make_agent()
    monkeypatch.setattr(agent.llm_generator, "generate_cases", _mock_llm_generate)

    report_normal = agent.run(EXAMPLE_YAML, case_type="normal")
    report_abnormal = agent.run(EXAMPLE_YAML, case_type="abnormal")

    for ep in report_normal.endpoints:
        assert ep.abnormal_cases == 0

    for ep in report_abnormal.endpoints:
        assert ep.normal_cases == 0


def test_report_summary(monkeypatch):
    """测试报告摘要输出"""
    agent = _make_agent()
    monkeypatch.setattr(agent.llm_generator, "generate_cases", _mock_llm_generate)

    report = agent.run(EXAMPLE_YAML)
    summary = report.summary()
    assert "测试报告" in summary
    assert "通过率" in summary


def test_report_to_dict(monkeypatch):
    """测试报告JSON序列化"""
    agent = _make_agent()
    monkeypatch.setattr(agent.llm_generator, "generate_cases", _mock_llm_generate)

    report = agent.run(EXAMPLE_YAML)
    d = report.to_dict()
    json_str = json.dumps(d, ensure_ascii=False, default=str)
    assert len(json_str) > 0
    assert d["total_endpoints"] == 5


def test_agent_llm_returns_empty(monkeypatch):
    """测试LLM返回空列表时 Agent 正常处理"""
    agent = _make_agent()
    monkeypatch.setattr(agent.llm_generator, "generate_cases", lambda endpoint, case_type: [])

    cases = agent.generate_only(EXAMPLE_YAML, case_type="normal")
    assert cases == []


def test_agent_requires_llm_url():
    """测试不提供 llm_api_url 时抛出 ValueError"""
    try:
        ApiTestAgent(mode="mock", llm_api_url="")
        assert False, "expected ValueError"
    except ValueError:
        pass
