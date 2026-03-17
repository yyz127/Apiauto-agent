"""LangGraph 图的单元测试和集成测试"""

import json
from pathlib import Path
from unittest.mock import patch

from apiauto_agent.graph import build_graph, get_graph_mermaid
from apiauto_agent.state import create_initial_state, ApiTestState
from apiauto_agent import nodes
from apiauto_agent.generator import generate_test_cases, generate_normal_cases, generate_abnormal_cases

EXAMPLE_YAML = str(Path(__file__).parent.parent / "examples" / "petstore.yaml")


def _mock_llm_generate(endpoint, case_type="all"):
    """模拟 LLM 生成用例，调用规则引擎以确保测试稳定。"""
    if case_type == "normal":
        return generate_normal_cases(endpoint)
    if case_type == "abnormal":
        return generate_abnormal_cases(endpoint)
    return generate_test_cases(endpoint)


# ── 图编译测试 ──

def test_graph_compiles():
    """测试图能正常编译。"""
    graph = build_graph()
    assert graph is not None


def test_graph_mermaid():
    """测试图能输出 Mermaid 图。"""
    mermaid = get_graph_mermaid()
    assert "parse_yaml" in mermaid
    assert "generate_cases" in mermaid
    assert "generate_report" in mermaid


# ── 端到端测试（Mock 模式，mock LLM 调用） ──

def test_graph_e2e_mock():
    """LangGraph 图端到端测试：mock 模式，所有用例通过。"""
    initial = create_initial_state(
        yaml_file=EXAMPLE_YAML,
        mode="mock",
    )
    graph = build_graph()
    with patch("apiauto_agent.nodes.LLMCaseGenerator") as MockLLM:
        MockLLM.return_value.generate_cases.side_effect = _mock_llm_generate
        result = graph.invoke(initial)

    report = result["report"]
    assert report["total_endpoints"] == 5
    assert report["total_cases"] > 0
    assert report["total_passed"] > 0
    assert report["total_failed"] == 0
    assert "pass_rate" in report


def test_graph_e2e_mock_normal_only():
    """LangGraph 图：只生成正常用例。"""
    initial = create_initial_state(
        yaml_file=EXAMPLE_YAML,
        mode="mock",
        case_type="normal",
    )
    graph = build_graph()
    with patch("apiauto_agent.nodes.LLMCaseGenerator") as MockLLM:
        MockLLM.return_value.generate_cases.side_effect = _mock_llm_generate
        result = graph.invoke(initial)

    report = result["report"]
    for ep in report["endpoints"]:
        assert ep["abnormal_cases"] == 0
        assert ep["normal_cases"] > 0


def test_graph_e2e_mock_abnormal_only():
    """LangGraph 图：只生成异常用例。"""
    initial = create_initial_state(
        yaml_file=EXAMPLE_YAML,
        mode="mock",
        case_type="abnormal",
    )
    graph = build_graph()
    with patch("apiauto_agent.nodes.LLMCaseGenerator") as MockLLM:
        MockLLM.return_value.generate_cases.side_effect = _mock_llm_generate
        result = graph.invoke(initial)

    report = result["report"]
    for ep in report["endpoints"]:
        assert ep["normal_cases"] == 0


def test_graph_endpoint_filter():
    """LangGraph 图：接口过滤。"""
    initial = create_initial_state(
        yaml_file=EXAMPLE_YAML,
        mode="mock",
        endpoint_filter="/pets/{petId}",
    )
    graph = build_graph()
    with patch("apiauto_agent.nodes.LLMCaseGenerator") as MockLLM:
        MockLLM.return_value.generate_cases.side_effect = _mock_llm_generate
        result = graph.invoke(initial)

    report = result["report"]
    assert report["total_endpoints"] == 3


def test_graph_report_serializable():
    """测试报告可序列化为 JSON。"""
    initial = create_initial_state(yaml_file=EXAMPLE_YAML, mode="mock")
    graph = build_graph()
    with patch("apiauto_agent.nodes.LLMCaseGenerator") as MockLLM:
        MockLLM.return_value.generate_cases.side_effect = _mock_llm_generate
        result = graph.invoke(initial)

    json_str = json.dumps(result["report"], ensure_ascii=False, default=str)
    assert len(json_str) > 0


# ── 节点单元测试 ──

def test_node_parse_yaml():
    """测试 parse_yaml 节点。"""
    state: ApiTestState = create_initial_state(yaml_file=EXAMPLE_YAML)
    result = nodes.parse_yaml(state)
    assert len(result["endpoints"]) == 5
    assert result["current_index"] == 0


def test_node_parse_yaml_with_filter():
    """测试 parse_yaml 节点带过滤。"""
    state: ApiTestState = create_initial_state(yaml_file=EXAMPLE_YAML, endpoint_filter="/pets/{petId}")
    result = nodes.parse_yaml(state)
    assert len(result["endpoints"]) == 3


def test_node_parse_yaml_invalid_file():
    """测试 parse_yaml 节点处理无效文件。"""
    state: ApiTestState = create_initial_state(yaml_file="/nonexistent.yaml")
    result = nodes.parse_yaml(state)
    assert result["error"] != ""
    assert len(result["endpoints"]) == 0


def test_node_select_endpoint():
    """测试 select_endpoint 节点。"""
    state: ApiTestState = create_initial_state(yaml_file=EXAMPLE_YAML)
    parsed = nodes.parse_yaml(state)
    state["endpoints"] = parsed["endpoints"]
    state["current_index"] = 0
    result = nodes.select_endpoint(state)
    assert result["current_endpoint"]["path"] is not None


def test_node_generate_cases():
    """测试 generate_cases 节点（mock LLM）。"""
    state: ApiTestState = create_initial_state(yaml_file=EXAMPLE_YAML)
    parsed = nodes.parse_yaml(state)
    state["endpoints"] = parsed["endpoints"]
    state["current_index"] = 0
    state["current_endpoint"] = parsed["endpoints"][0]

    with patch("apiauto_agent.nodes.LLMCaseGenerator") as MockLLM:
        MockLLM.return_value.generate_cases.side_effect = _mock_llm_generate
        result = nodes.generate_cases(state)
    assert len(result["current_cases"]) > 0
    assert result["generation_method"] == "llm"


def test_node_execute_cases():
    """测试 execute_cases 节点。"""
    state: ApiTestState = create_initial_state(yaml_file=EXAMPLE_YAML)
    parsed = nodes.parse_yaml(state)
    state["current_endpoint"] = parsed["endpoints"][0]

    with patch("apiauto_agent.nodes.LLMCaseGenerator") as MockLLM:
        MockLLM.return_value.generate_cases.side_effect = _mock_llm_generate
        gen_result = nodes.generate_cases(state)
    state["current_cases"] = gen_result["current_cases"]

    exec_result = nodes.execute_cases(state)
    assert len(exec_result["current_results"]) == len(state["current_cases"])


def test_node_collect_results():
    """测试 collect_results 节点。"""
    state: ApiTestState = create_initial_state(yaml_file=EXAMPLE_YAML)
    parsed = nodes.parse_yaml(state)
    state["endpoints"] = parsed["endpoints"]
    state["current_index"] = 0
    state["current_endpoint"] = parsed["endpoints"][0]

    with patch("apiauto_agent.nodes.LLMCaseGenerator") as MockLLM:
        MockLLM.return_value.generate_cases.side_effect = _mock_llm_generate
        gen_result = nodes.generate_cases(state)
    state["current_cases"] = gen_result["current_cases"]
    state["generation_method"] = gen_result["generation_method"]

    exec_result = nodes.execute_cases(state)
    state["current_results"] = exec_result["current_results"]

    collect_result = nodes.collect_results(state)
    assert len(collect_result["endpoint_reports"]) == 1
    assert collect_result["current_index"] == 1


# ── 条件边测试 ──

def test_has_more_endpoints_yes():
    """测试 has_more_endpoints 条件边：还有更多。"""
    state = {"current_index": 0, "endpoints": [{"path": "/a"}, {"path": "/b"}]}
    assert nodes.has_more_endpoints(state) == "select_endpoint"


def test_has_more_endpoints_no():
    """测试 has_more_endpoints 条件边：处理完毕。"""
    state = {"current_index": 2, "endpoints": [{"path": "/a"}, {"path": "/b"}]}
    assert nodes.has_more_endpoints(state) == "generate_report"


# ── Agent.run_graph 测试 ──

def test_agent_run_graph(monkeypatch):
    """测试 ApiTestAgent.run_graph() 方法。"""
    from apiauto_agent.agent import ApiTestAgent

    agent = ApiTestAgent(mode="mock", llm_api_url="http://mock-llm.local/v1/chat/completions")
    monkeypatch.setattr(
        "apiauto_agent.nodes.LLMCaseGenerator",
        lambda **kwargs: type("MockLLM", (), {"generate_cases": staticmethod(_mock_llm_generate)})(),
    )

    report = agent.run_graph(EXAMPLE_YAML)

    assert report.total_endpoints == 5
    assert report.total_cases > 0
    assert report.total_failed == 0
    summary = report.summary()
    assert "测试报告" in summary
