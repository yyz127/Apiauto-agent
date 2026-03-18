"""LangGraph 图的单元测试和集成测试"""

import json
from pathlib import Path
from unittest.mock import patch

from apiauto_agent.graph import build_graph, get_graph_mermaid
from apiauto_agent.state import create_initial_state, ApiTestState
from apiauto_agent import nodes
from apiauto_agent.generator import generate_test_cases, generate_normal_cases, generate_abnormal_cases
from apiauto_agent.llm_generator import CaseGenerationError
from apiauto_agent.endpoint_workflow import generate_validated_cases

EXAMPLE_YAML = str(Path(__file__).parent.parent / "examples" / "petstore.yaml")


def _mock_llm_generate(endpoint, case_type="all"):
    """模拟 LLM 生成用例，调用规则引擎以确保测试稳定。"""
    if case_type == "normal":
        return generate_normal_cases(endpoint)
    if case_type == "abnormal":
        return generate_abnormal_cases(endpoint)
    return generate_test_cases(endpoint)


def _mock_llm_generate_with_feedback(endpoint, case_type="all", review_feedback=""):
    return _mock_llm_generate(endpoint, case_type)


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
        MockLLM.return_value.generate_cases_with_feedback.side_effect = _mock_llm_generate_with_feedback
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
        MockLLM.return_value.generate_cases_with_feedback.side_effect = _mock_llm_generate_with_feedback
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
        MockLLM.return_value.generate_cases_with_feedback.side_effect = _mock_llm_generate_with_feedback
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
        MockLLM.return_value.generate_cases_with_feedback.side_effect = _mock_llm_generate_with_feedback
        result = graph.invoke(initial)

    report = result["report"]
    assert report["total_endpoints"] == 3


def test_graph_report_serializable():
    """测试报告可序列化为 JSON。"""
    initial = create_initial_state(yaml_file=EXAMPLE_YAML, mode="mock")
    graph = build_graph()
    with patch("apiauto_agent.nodes.LLMCaseGenerator") as MockLLM:
        MockLLM.return_value.generate_cases_with_feedback.side_effect = _mock_llm_generate_with_feedback
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
        MockLLM.return_value.generate_cases_with_feedback.side_effect = _mock_llm_generate_with_feedback
        result = nodes.generate_cases(state)
    assert len(result["current_cases"]) > 0
    assert result["generation_method"] == "llm"
    assert result["generation_failed"] is False


def test_node_generate_cases_failure():
    """测试 generate_cases 节点在 LLM 空返回时标记生成失败。"""
    state: ApiTestState = create_initial_state(yaml_file=EXAMPLE_YAML)
    parsed = nodes.parse_yaml(state)
    state["endpoints"] = parsed["endpoints"]
    state["current_index"] = 0
    state["current_endpoint"] = parsed["endpoints"][0]

    with patch("apiauto_agent.nodes.LLMCaseGenerator") as MockLLM:
        MockLLM.return_value.generate_cases_with_feedback.side_effect = CaseGenerationError("LLM返回空数组")
        result = nodes.generate_cases(state)

    assert result["current_cases"] == []
    assert result["generation_failed"] is True
    assert result["generation_error"] == "LLM返回空数组"


def test_generate_validated_cases_failure():
    """测试业务层会拦截非法用例。"""
    from apiauto_agent.parser import parse_openapi_file

    endpoint = parse_openapi_file(EXAMPLE_YAML)[0]

    class _FakeLLM:
        @staticmethod
        def generate_cases_with_feedback(endpoint, case_type="all", review_feedback=""):
            return [
                nodes.TestCase(
                    name="case-1",
                    description="desc",
                    endpoint_path=endpoint.path,
                    method=endpoint.method,
                    case_type="abnormal",
                    parameters={},
                    headers={},
                    expected_status=200,
                )
            ]

    try:
        generate_validated_cases(endpoint, _FakeLLM(), case_type="normal")
        assert False, "expected CaseGenerationError"
    except CaseGenerationError as e:
        assert "类型与请求不一致" in str(e)


def test_node_review_cases_auto_approve():
    """测试关闭人工审核时 review_cases 直接通过。"""
    state: ApiTestState = create_initial_state(yaml_file=EXAMPLE_YAML, human_review=False)
    parsed = nodes.parse_yaml(state)
    state["current_endpoint"] = parsed["endpoints"][0]
    state["current_cases"] = []

    result = nodes.review_cases(state)
    assert result["review_status"] == "approved"


def test_node_review_cases_feedback(monkeypatch):
    """测试人工审核可反馈并触发重新生成。"""
    state: ApiTestState = create_initial_state(yaml_file=EXAMPLE_YAML, human_review=True)
    parsed = nodes.parse_yaml(state)
    state["current_endpoint"] = parsed["endpoints"][0]
    state["current_cases"] = [
        {
            "name": "case-1",
            "description": "desc",
            "endpoint_path": parsed["endpoints"][0]["path"],
            "method": parsed["endpoints"][0]["method"],
            "case_type": "normal",
            "parameters": {},
            "headers": {},
            "expected_status": 200,
        }
    ]

    answers = iter(["f", "请补充边界场景"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    result = nodes.review_cases(state)
    assert result["review_status"] == "regenerate"
    assert result["review_feedback"] == "请补充边界场景"
    assert result["review_round"] == 1


def test_node_review_cases_reaches_max_rounds():
    """测试人工审核达到最大轮次后直接失败。"""
    state: ApiTestState = create_initial_state(yaml_file=EXAMPLE_YAML, human_review=True, max_review_rounds=2)
    parsed = nodes.parse_yaml(state)
    state["current_endpoint"] = parsed["endpoints"][0]
    state["current_cases"] = []
    state["review_round"] = 2

    result = nodes.review_cases(state)
    assert result["generation_failed"] is True
    assert result["review_status"] == "rejected"


def test_route_after_review():
    """测试人工审核后的路由。"""
    assert nodes.route_after_review({"review_status": "approved"}) == "execute_cases"
    assert nodes.route_after_review({"review_status": "regenerate"}) == "generate_cases"
    assert nodes.route_after_review({"review_status": "rejected", "generation_failed": True}) == "collect_results"


def test_node_execute_cases():
    """测试 execute_cases 节点。"""
    state: ApiTestState = create_initial_state(yaml_file=EXAMPLE_YAML)
    parsed = nodes.parse_yaml(state)
    state["current_endpoint"] = parsed["endpoints"][0]

    with patch("apiauto_agent.nodes.LLMCaseGenerator") as MockLLM:
        MockLLM.return_value.generate_cases_with_feedback.side_effect = _mock_llm_generate_with_feedback
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
        MockLLM.return_value.generate_cases_with_feedback.side_effect = _mock_llm_generate_with_feedback
        gen_result = nodes.generate_cases(state)
    state["current_cases"] = gen_result["current_cases"]
    state["generation_method"] = gen_result["generation_method"]

    exec_result = nodes.execute_cases(state)
    state["current_results"] = exec_result["current_results"]

    collect_result = nodes.collect_results(state)
    assert len(collect_result["endpoint_reports"]) == 1
    assert collect_result["current_index"] == 1


def test_graph_generation_failure_skips_execute():
    """LangGraph 图：生成失败时跳过 execute_cases，并记录失败接口。"""
    initial = create_initial_state(
        yaml_file=EXAMPLE_YAML,
        mode="mock",
        case_type="normal",
    )
    graph = build_graph()

    with patch("apiauto_agent.nodes.LLMCaseGenerator") as MockLLM, \
            patch("apiauto_agent.nodes.create_executor", side_effect=AssertionError("execute_cases should be skipped")):
        MockLLM.return_value.generate_cases_with_feedback.side_effect = CaseGenerationError("LLM返回空数组")
        result = graph.invoke(initial)

    report = result["report"]
    assert report["total_endpoints"] == 5
    assert report["generation_failed_endpoints"] == 5
    assert report["total_cases"] == 0
    assert all(ep["generation_failed"] for ep in report["endpoints"])


def test_graph_check_failure_skips_execute():
    """LangGraph 图：生成成功但检查失败时也应跳过 execute_cases。"""
    initial = create_initial_state(
        yaml_file=EXAMPLE_YAML,
        mode="mock",
        case_type="normal",
    )
    graph = build_graph()

    bad_case = {
        "name": "bad-case",
        "description": "wrong type",
        "case_type": "abnormal",
        "parameters": {},
        "headers": {},
        "expected_status": 400,
    }

    with patch("apiauto_agent.nodes.LLMCaseGenerator") as MockLLM, \
            patch("apiauto_agent.nodes.create_executor", side_effect=AssertionError("execute_cases should be skipped")):
        MockLLM.return_value.generate_cases_with_feedback.return_value = [
            nodes.TestCase(
                name=bad_case["name"],
                description=bad_case["description"],
                endpoint_path="/pets",
                method="GET",
                case_type=bad_case["case_type"],
                parameters=bad_case["parameters"],
                headers=bad_case["headers"],
                expected_status=bad_case["expected_status"],
            )
        ]
        result = graph.invoke(initial)

    report = result["report"]
    assert report["generation_failed_endpoints"] == 5
    assert all(ep["generation_failed"] for ep in report["endpoints"])


def test_graph_human_review_feedback_loop(monkeypatch):
    """LangGraph 图：人工审核反馈后回到 LLM 重新生成，再通过执行。"""
    initial = create_initial_state(
        yaml_file=EXAMPLE_YAML,
        mode="mock",
        case_type="normal",
        human_review=True,
    )
    graph = build_graph()

    call_count = 0

    def _reviewable_llm(endpoint, case_type="all", review_feedback=""):
        nonlocal call_count
        call_count += 1
        if not review_feedback:
            return [
                nodes.TestCase(
                    name="初版用例",
                    description="需要人工要求补充边界",
                    endpoint_path=endpoint.path,
                    method=endpoint.method,
                    case_type="normal",
                    parameters={},
                    headers={},
                    expected_status=200,
                )
            ]
        assert "补充边界" in review_feedback
        return [
            nodes.TestCase(
                name="修订后用例",
                description="已根据反馈修订",
                endpoint_path=endpoint.path,
                method=endpoint.method,
                case_type="normal",
                parameters={},
                headers={},
                expected_status=200,
            )
        ]

    answers = iter(["f", "请补充边界", "a"] * 5)
    monkeypatch.setattr("builtins.input", lambda _: next(answers))

    with patch("apiauto_agent.nodes.LLMCaseGenerator") as MockLLM:
        MockLLM.return_value.generate_cases_with_feedback.side_effect = _reviewable_llm
        result = graph.invoke(initial)

    report = result["report"]
    assert call_count >= 2
    assert report["generation_failed_endpoints"] == 0
    assert report["total_cases"] > 0


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
        lambda **kwargs: type(
            "MockLLM",
            (),
            {"generate_cases_with_feedback": staticmethod(_mock_llm_generate_with_feedback)},
        )(),
    )

    report = agent.run_graph(EXAMPLE_YAML)

    assert report.total_endpoints == 5
    assert report.total_cases > 0
    assert report.total_failed == 0
    summary = report.summary()
    assert "测试报告" in summary
