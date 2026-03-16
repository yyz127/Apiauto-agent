"""测试Agent核心功能"""

import json
from pathlib import Path

from apiauto_agent.parser import parse_openapi_file
from apiauto_agent.generator import generate_test_cases, generate_normal_cases, generate_abnormal_cases
from apiauto_agent.agent import ApiTestAgent

EXAMPLE_YAML = Path(__file__).parent.parent / "examples" / "petstore.yaml"


def test_parse_openapi():
    """测试OpenAPI解析"""
    endpoints = parse_openapi_file(EXAMPLE_YAML)
    assert len(endpoints) > 0
    # 应该有5个接口: GET /pets, POST /pets, GET /pets/{petId}, PUT /pets/{petId}, DELETE /pets/{petId}
    assert len(endpoints) == 5
    methods = {(ep.method, ep.path) for ep in endpoints}
    assert ("GET", "/pets") in methods
    assert ("POST", "/pets") in methods
    assert ("DELETE", "/pets/{petId}") in methods


def test_generate_normal_cases():
    """测试正常用例生成"""
    endpoints = parse_openapi_file(EXAMPLE_YAML)
    for ep in endpoints:
        cases = generate_normal_cases(ep)
        assert len(cases) > 0
        for c in cases:
            assert c.case_type == "normal"
            assert c.method == ep.method


def test_generate_abnormal_cases():
    """测试异常用例生成"""
    endpoints = parse_openapi_file(EXAMPLE_YAML)
    # POST /pets 有必填参数，应该能生成异常用例
    post_pets = [ep for ep in endpoints if ep.method == "POST" and ep.path == "/pets"][0]
    cases = generate_abnormal_cases(post_pets)
    assert len(cases) > 0
    for c in cases:
        assert c.case_type == "abnormal"


def test_generate_all_cases():
    """测试生成所有用例"""
    endpoints = parse_openapi_file(EXAMPLE_YAML)
    for ep in endpoints:
        cases = generate_test_cases(ep)
        normal = [c for c in cases if c.case_type == "normal"]
        abnormal = [c for c in cases if c.case_type == "abnormal"]
        assert len(normal) > 0
        # 有参数的接口应该都有异常用例
        if ep.parameters:
            assert len(abnormal) > 0


def test_agent_run_mock():
    """测试Agent完整流程（Mock模式）"""
    agent = ApiTestAgent(mode="mock")
    report = agent.run(EXAMPLE_YAML)
    assert report.total_endpoints == 5
    assert report.total_cases > 0
    assert report.total_passed > 0
    # Mock模式下所有用例都应该通过
    assert report.total_failed == 0


def test_agent_generate_only():
    """测试只生成用例"""
    agent = ApiTestAgent(mode="mock")
    cases = agent.generate_only(EXAMPLE_YAML)
    assert len(cases) > 0
    # 检查用例可以序列化
    for c in cases:
        d = c.to_dict()
        assert "name" in d
        assert "parameters" in d
        json.dumps(d, ensure_ascii=False, default=str)


def test_agent_filter_endpoint():
    """测试接口过滤"""
    agent = ApiTestAgent(mode="mock")
    report = agent.run(EXAMPLE_YAML, endpoint_filter="/pets/{petId}")
    # 应该只有 GET/PUT/DELETE /pets/{petId}
    assert report.total_endpoints == 3


def test_agent_case_type_filter():
    """测试用例类型过滤"""
    agent = ApiTestAgent(mode="mock")

    report_normal = agent.run(EXAMPLE_YAML, case_type="normal")
    report_abnormal = agent.run(EXAMPLE_YAML, case_type="abnormal")

    # 正常用例报告中不应有异常用例
    for ep in report_normal.endpoints:
        assert ep.abnormal_cases == 0

    # 异常用例报告中不应有正常用例
    for ep in report_abnormal.endpoints:
        assert ep.normal_cases == 0


def test_report_summary():
    """测试报告摘要输出"""
    agent = ApiTestAgent(mode="mock")
    report = agent.run(EXAMPLE_YAML)
    summary = report.summary()
    assert "测试报告" in summary
    assert "通过率" in summary


def test_report_to_dict():
    """测试报告JSON序列化"""
    agent = ApiTestAgent(mode="mock")
    report = agent.run(EXAMPLE_YAML)
    d = report.to_dict()
    # 确保可以序列化为JSON
    json_str = json.dumps(d, ensure_ascii=False, default=str)
    assert len(json_str) > 0
    assert d["total_endpoints"] == 5
