"""LangGraph 节点实现

每个节点函数接收 ApiTestState，返回需要更新的字段字典。
节点内部调用现有模块（parser/generator/llm_generator/executor），不重复造轮子。
"""

import dataclasses
import logging
from typing import Any, Literal

from .state import ApiTestState
from .parser import parse_openapi_file, EndpointInfo, ParameterInfo
from .generator import TestCase
from .llm_generator import LLMCaseGenerator, CaseGenerationError
from .executor import create_executor
from .endpoint_workflow import (
    generate_validated_cases,
    review_generated_cases,
    summarize_case_counts,
)

logger = logging.getLogger(__name__)


# ── 辅助函数：dataclass ↔ dict 序列化 ──

def _endpoint_to_dict(ep: EndpointInfo) -> dict[str, Any]:
    """EndpointInfo → 可序列化 dict。"""
    return dataclasses.asdict(ep)


def _dict_to_endpoint(d: dict[str, Any]) -> EndpointInfo:
    """dict → EndpointInfo（还原 ParameterInfo 列表）。"""
    params = [ParameterInfo(**p) for p in d.get("parameters", [])]
    return EndpointInfo(
        path=d["path"],
        method=d["method"],
        summary=d.get("summary", ""),
        description=d.get("description", ""),
        parameters=params,
        request_body_content_type=d.get("request_body_content_type", "application/json"),
        request_body_schema=d.get("request_body_schema"),
        responses=d.get("responses", {}),
        tags=d.get("tags", []),
        security=d.get("security", []),
        security_schemes=d.get("security_schemes", {}),
    )


def _case_to_dict(tc: TestCase) -> dict[str, Any]:
    """TestCase → dict。"""
    return tc.to_dict()


def _dict_to_case(d: dict[str, Any]) -> TestCase:
    """dict → TestCase。"""
    return TestCase(
        name=d["name"],
        description=d.get("description", ""),
        endpoint_path=d["endpoint_path"],
        method=d["method"],
        case_type=d.get("case_type", "normal"),
        parameters=d.get("parameters", {}),
        headers=d.get("headers", {}),
        expected_status=d.get("expected_status"),
    )


# ── 节点函数 ──

def parse_yaml(state: ApiTestState) -> dict[str, Any]:
    """节点：解析 YAML 文件，提取接口列表。"""
    yaml_file = state["yaml_file"]
    endpoint_filter = state.get("endpoint_filter", "")

    try:
        endpoints = parse_openapi_file(yaml_file)
    except Exception as e:
        logger.error("解析YAML文件失败: %s", e)
        return {"error": f"解析YAML文件失败: {e}", "endpoints": []}

    if endpoint_filter:
        endpoints = [ep for ep in endpoints if endpoint_filter in ep.path]

    logger.info("解析完成，共 %d 个接口", len(endpoints))
    return {
        "endpoints": [_endpoint_to_dict(ep) for ep in endpoints],
        "current_index": 0,
        "endpoint_reports": [],
    }


def select_endpoint(state: ApiTestState) -> dict[str, Any]:
    """节点：选取当前要处理的接口。"""
    idx = state["current_index"]
    endpoints = state["endpoints"]
    ep = endpoints[idx]
    logger.info("处理接口 [%d/%d]: [%s] %s", idx + 1, len(endpoints), ep["method"], ep["path"])
    return {"current_endpoint": ep}


def generate_cases(state: ApiTestState) -> dict[str, Any]:
    """节点：使用 LLM 生成测试用例。"""
    endpoint = _dict_to_endpoint(state["current_endpoint"])
    case_type = state.get("case_type", "all")
    review_feedback = state.get("review_feedback", "")

    llm_gen = LLMCaseGenerator(
        api_url=state["llm_api_url"],
        api_key=state.get("llm_api_key", ""),
        model=state.get("llm_model", "gpt-4o-mini"),
        timeout=state.get("timeout", 60),
    )
    try:
        cases = generate_validated_cases(
            endpoint,
            llm_gen,
            case_type=case_type,
            review_feedback=review_feedback,
        )
        logger.info("LLM 生成 %d 个用例", len(cases))
        generation_failed = False
        generation_error = ""
    except CaseGenerationError as e:
        cases = []
        generation_failed = True
        generation_error = str(e)
        logger.error("LLM 未返回有效用例: [%s] %s, 原因: %s", endpoint.method, endpoint.path, generation_error)
    return {
        "current_cases": [_case_to_dict(c) for c in cases],
        "current_results": [],
        "generation_method": "llm",
        "generation_failed": generation_failed,
        "generation_error": generation_error,
        "review_status": "pending",
    }
def review_cases(state: ApiTestState) -> dict[str, Any]:
    """节点：人工审核路由，具体审核逻辑下沉到 endpoint_workflow。"""
    n = len(state.get("current_cases", []))
    ep = state.get("current_endpoint", {})
    logger.info("用例审核: [%s] %s 共 %d 个用例", ep.get("method"), ep.get("path"), n)
    endpoint = _dict_to_endpoint(state["current_endpoint"])
    cases = [_dict_to_case(d) for d in state.get("current_cases", [])]
    return review_generated_cases(
        endpoint,
        cases,
        human_review=state.get("human_review", False),
        review_round=state.get("review_round", 0),
        max_review_rounds=state.get("max_review_rounds", 3),
    )


def execute_cases(state: ApiTestState) -> dict[str, Any]:
    """节点：执行当前接口的所有测试用例。"""
    mode = state.get("mode", "mock")
    api_url = state.get("api_url", "")
    timeout = state.get("timeout", 30)
    headers = state.get("headers", {})

    executor = create_executor(
        mode=mode,
        api_url=api_url,
        timeout=timeout,
        headers=headers,
        uuid=state.get("uuid", ""),
        env=state.get("env", ""),
        target_base_url=state.get("target_base_url", ""),
        target_headers=state.get("target_headers", {}),
    )

    case_dicts = state.get("current_cases", [])
    cases = [_dict_to_case(d) for d in case_dicts]
    results = executor.execute_batch(cases)

    return {
        "current_results": [r.to_dict() for r in results],
    }


def collect_results(state: ApiTestState) -> dict[str, Any]:
    """节点：汇总当前接口执行结果，推进索引。"""
    ep = state["current_endpoint"]
    cases = state.get("current_cases", [])
    results = state.get("current_results", [])
    generation_failed = state.get("generation_failed", False)
    generation_error = state.get("generation_error", "")

    case_objects = [_dict_to_case(d) for d in cases]
    normal_count, abnormal_count = summarize_case_counts(case_objects)
    passed = sum(1 for r in results if r.get("success"))
    failed = sum(1 for r in results if not r.get("success"))

    ep_report = {
        "path": ep["path"],
        "method": ep["method"],
        "summary": ep.get("summary", ""),
        "generation_failed": generation_failed,
        "generation_error": generation_error,
        "total_cases": len(cases),
        "normal_cases": normal_count,
        "abnormal_cases": abnormal_count,
        "passed": passed,
        "failed": failed,
        "results": results,
        "generation_method": state.get("generation_method", ""),
        "review_round": state.get("review_round", 0),
    }

    existing_reports = list(state.get("endpoint_reports", []))
    existing_reports.append(ep_report)

    return {
        "endpoint_reports": existing_reports,
        "current_index": state["current_index"] + 1,
        "review_feedback": "",
        "review_status": "pending",
        "review_round": 0,
    }


def generate_report(state: ApiTestState) -> dict[str, Any]:
    """节点：汇总所有 EndpointReport 为最终 TestReport。"""
    reports = state.get("endpoint_reports", [])
    generation_failed_endpoints = sum(1 for r in reports if r.get("generation_failed"))
    total_cases = sum(r["total_cases"] for r in reports)
    total_passed = sum(r["passed"] for r in reports)
    total_failed = sum(r["failed"] for r in reports)

    report = {
        "yaml_file": state["yaml_file"],
        "total_endpoints": len(reports),
        "generation_failed_endpoints": generation_failed_endpoints,
        "total_cases": total_cases,
        "total_passed": total_passed,
        "total_failed": total_failed,
        "pass_rate": f"{total_passed / total_cases * 100:.1f}%" if total_cases else "N/A",
        "endpoints": reports,
    }

    logger.info("测试完成: %d 接口, %d 用例, 通过率 %s", len(reports), total_cases, report["pass_rate"])
    return {"report": report}


# ── 条件边函数 ──

def has_more_endpoints(state: ApiTestState) -> Literal["select_endpoint", "generate_report"]:
    """条件边：判断是否还有更多接口需要处理。"""
    if state["current_index"] < len(state["endpoints"]):
        return "select_endpoint"
    return "generate_report"


def should_execute_current_endpoint(state: ApiTestState) -> Literal["review_cases", "collect_results"]:
    """条件边：当前接口生成失败时直接汇总，不进入执行阶段。"""
    if state.get("generation_failed", False):
        return "collect_results"
    return "review_cases"


def route_after_review(state: ApiTestState) -> Literal["execute_cases", "generate_cases", "collect_results"]:
    """条件边：人工审核后决定执行、回生或结束。"""
    if state.get("generation_failed", False):
        return "collect_results"
    review_status = state.get("review_status", "approved")
    if review_status == "regenerate":
        return "generate_cases"
    if review_status == "approved":
        return "execute_cases"
    return "collect_results"
