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
from .llm_generator import LLMCaseGenerator
from .executor import create_executor

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

    llm_gen = LLMCaseGenerator(
        api_url=state["llm_api_url"],
        api_key=state.get("llm_api_key", ""),
        model=state.get("llm_model", "gpt-4o-mini"),
        timeout=state.get("timeout", 60),
    )
    cases = llm_gen.generate_cases(endpoint, case_type)
    if cases:
        logger.info("LLM 生成 %d 个用例", len(cases))
    else:
        logger.warning("LLM 未返回有效用例: [%s] %s", endpoint.method, endpoint.path)
    return {
        "current_cases": [_case_to_dict(c) for c in cases],
        "generation_method": "llm",
    }


def review_cases(state: ApiTestState) -> dict[str, Any]:
    """节点：用例审核（human_review=True 时可扩展为 interrupt）。

    当前版本直接通过，不阻塞。
    未来可接入 LangGraph interrupt 机制实现人工审核。
    """
    n = len(state.get("current_cases", []))
    ep = state.get("current_endpoint", {})
    logger.info("用例审核: [%s] %s 共 %d 个用例", ep.get("method"), ep.get("path"), n)
    return {}


def execute_cases(state: ApiTestState) -> dict[str, Any]:
    """节点：执行当前接口的所有测试用例。"""
    mode = state.get("mode", "mock")
    api_url = state.get("api_url", "")
    timeout = state.get("timeout", 30)
    headers = state.get("headers", {})

    executor = create_executor(mode=mode, api_url=api_url, timeout=timeout, headers=headers)

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

    normal_count = sum(1 for c in cases if c.get("case_type") == "normal")
    abnormal_count = sum(1 for c in cases if c.get("case_type") == "abnormal")
    passed = sum(1 for r in results if r.get("success"))
    failed = sum(1 for r in results if not r.get("success"))

    ep_report = {
        "path": ep["path"],
        "method": ep["method"],
        "summary": ep.get("summary", ""),
        "total_cases": len(cases),
        "normal_cases": normal_count,
        "abnormal_cases": abnormal_count,
        "passed": passed,
        "failed": failed,
        "results": results,
        "generation_method": state.get("generation_method", ""),
    }

    existing_reports = list(state.get("endpoint_reports", []))
    existing_reports.append(ep_report)

    return {
        "endpoint_reports": existing_reports,
        "current_index": state["current_index"] + 1,
    }


def generate_report(state: ApiTestState) -> dict[str, Any]:
    """节点：汇总所有 EndpointReport 为最终 TestReport。"""
    reports = state.get("endpoint_reports", [])
    total_cases = sum(r["total_cases"] for r in reports)
    total_passed = sum(r["passed"] for r in reports)
    total_failed = sum(r["failed"] for r in reports)

    report = {
        "yaml_file": state["yaml_file"],
        "total_endpoints": len(reports),
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
