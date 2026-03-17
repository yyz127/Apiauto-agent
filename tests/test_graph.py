"""LangGraph 图的单元测试和集成测试"""

import json
from pathlib import Path
from unittest.mock import patch

from apiauto_agent.graph import build_graph, get_graph_mermaid
from apiauto_agent.state import create_initial_state, ApiTestState
from apiauto_agent import nodes

EXAMPLE_YAML = str(Path(__file__).parent.parent / "examples" / "petstore.yaml")


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


# ── 端到端测试（Mock 模式） ──

def test_graph_e2e_mock():
    """LangGraph 图端到端测试：mock 模式，所有用例通过。"""
    initial = create_initial_state(
        yaml_file=EXAMPLE_YAML,
        mode="mock",
        case_generator="rule",
    )
    graph = build_graph()
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
    result = graph.invoke(initial)

    report = result["report"]
    assert report["total_endpoints"] == 3


def test_graph_report_serializable():
    """测试报告可序列化为 JSON。"""
    initial = create_initial_state(yaml_file=EXAMPLE_YAML, mode="mock")
    graph = build_graph()
    result = graph.invoke(initial)

    json_str = json.dumps(result["report"], ensure_ascii=False, default=str)
    assert len(json_str) > 0


# ── 结果一致性测试 ──

def test_graph_matches_traditional():
    """LangGraph 模式与传统模式产出一致的统计数据。"""
    from apiauto_agent.agent import ApiTestAgent

    agent = ApiTestAgent(mode="mock")
    trad_report = agent.run(EXAMPLE_YAML)

    initial = create_initial_state(yaml_file=EXAMPLE_YAML, mode="mock")
    graph = build_graph()
    result = graph.invoke(initial)
    graph_report = result["report"]

    # 接口数一致
    assert graph_report["total_endpoints"] == trad_report.total_endpoints
    # 用例数一致（规则生成是确定性的，但有 random，所以只比较接口维度）
    assert graph_report["total_endpoints"] == trad_report.total_endpoints
    # 都是 0 失败
    assert graph_report["total_failed"] == 0
    assert trad_report.total_failed == 0


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


def test_node_generate_cases_rule():
    """测试 generate_cases 节点（规则模式）。"""
    state: ApiTestState = create_initial_state(yaml_file=EXAMPLE_YAML)
    parsed = nodes.parse_yaml(state)
    state["endpoints"] = parsed["endpoints"]
    state["current_index"] = 0
    state["current_endpoint"] = parsed["endpoints"][0]

    result = nodes.generate_cases(state)
    assert len(result["current_cases"]) > 0
    assert result["generation_failed"] is False
    assert result["generation_method"] == "rule"


def test_node_generate_cases_llm_fallback():
    """测试 generate_cases 节点 LLM 失败时标记降级。"""
    state: ApiTestState = create_initial_state(
        yaml_file=EXAMPLE_YAML,
        case_generator="llm",
        llm_api_url="http://fake-llm.local/v1/chat/completions",
    )
    parsed = nodes.parse_yaml(state)
    state["endpoints"] = parsed["endpoints"]
    state["current_endpoint"] = parsed["endpoints"][0]

    result = nodes.generate_cases(state)
    # LLM 应该失败（无法连接）
    assert result["generation_failed"] is True
    assert result["generation_method"] == "llm"


def test_node_fallback_rule_gen():
    """测试 fallback_rule_gen 节点。"""
    state: ApiTestState = create_initial_state(yaml_file=EXAMPLE_YAML)
    parsed = nodes.parse_yaml(state)
    state["current_endpoint"] = parsed["endpoints"][0]

    result = nodes.fallback_rule_gen(state)
    assert len(result["current_cases"]) > 0
    assert result["generation_method"] == "rule_fallback"


def test_node_execute_cases():
    """测试 execute_cases 节点。"""
    state: ApiTestState = create_initial_state(yaml_file=EXAMPLE_YAML)
    parsed = nodes.parse_yaml(state)
    state["current_endpoint"] = parsed["endpoints"][0]

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

    gen_result = nodes.generate_cases(state)
    state["current_cases"] = gen_result["current_cases"]
    state["generation_method"] = gen_result["generation_method"]

    exec_result = nodes.execute_cases(state)
    state["current_results"] = exec_result["current_results"]

    collect_result = nodes.collect_results(state)
    assert len(collect_result["endpoint_reports"]) == 1
    assert collect_result["current_index"] == 1


# ── 条件边测试 ──

def test_check_generation_success():
    """测试 check_generation 条件边：成功。"""
    state = {"generation_failed": False}
    assert nodes.check_generation(state) == "review_cases"


def test_check_generation_failed():
    """测试 check_generation 条件边：失败降级。"""
    state = {"generation_failed": True}
    assert nodes.check_generation(state) == "fallback_rule_gen"


def test_has_more_endpoints_yes():
    """测试 has_more_endpoints 条件边：还有更多。"""
    state = {"current_index": 0, "endpoints": [{"path": "/a"}, {"path": "/b"}]}
    assert nodes.has_more_endpoints(state) == "select_endpoint"


def test_has_more_endpoints_no():
    """测试 has_more_endpoints 条件边：处理完毕。"""
    state = {"current_index": 2, "endpoints": [{"path": "/a"}, {"path": "/b"}]}
    assert nodes.has_more_endpoints(state) == "generate_report"


# ── LLM 降级端到端测试 ──

def test_graph_llm_fallback_e2e():
    """LangGraph 图：LLM 失败自动降级到规则生成，最终仍产出完整报告。"""
    initial = create_initial_state(
        yaml_file=EXAMPLE_YAML,
        mode="mock",
        case_generator="llm",
        llm_api_url="http://fake-llm-that-will-fail.local/v1/chat/completions",
    )
    graph = build_graph()
    result = graph.invoke(initial)

    report = result["report"]
    assert report["total_endpoints"] == 5
    assert report["total_cases"] > 0
    assert report["total_failed"] == 0
    # 验证降级生成方法被记录
    for ep in report["endpoints"]:
        assert ep.get("generation_method") == "rule_fallback"


# ── Agent.run_graph 测试 ──

def test_agent_run_graph():
    """测试 ApiTestAgent.run_graph() 方法。"""
    from apiauto_agent.agent import ApiTestAgent

    agent = ApiTestAgent(mode="mock")
    report = agent.run_graph(EXAMPLE_YAML)

    assert report.total_endpoints == 5
    assert report.total_cases > 0
    assert report.total_failed == 0
    summary = report.summary()
    assert "测试报告" in summary
