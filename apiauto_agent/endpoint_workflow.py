"""单接口处理的业务逻辑。

图模式只做编排；这里承载生成、检查、人工审核等业务细节。
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from .case_checks import validate_generated_cases
from .generator import TestCase
from .exceptions import CaseGenerationError
from .llm_generator import LLMCaseGenerator
from .parser import EndpointInfo


@dataclass
class ReviewDecision:
    """人工审核结果（与图状态解耦的领域对象）。"""
    status: Literal["approved", "regenerate", "rejected"]
    feedback: str = ""
    round: int = 0
    rejection_reason: str = ""


def generate_validated_cases(
    endpoint: EndpointInfo,
    llm_generator: LLMCaseGenerator,
    case_type: str = "all",
    review_feedback: str = "",
) -> list[TestCase]:
    """生成并校验当前接口用例。"""
    cases = llm_generator.generate_cases_with_feedback(
        endpoint,
        case_type=case_type,
        review_feedback=review_feedback,
    )
    return validate_generated_cases(endpoint, cases, requested_case_type=case_type)


def review_generated_cases(
    endpoint: EndpointInfo,
    cases: list[TestCase],
    *,
    human_review: bool = False,
    review_round: int = 0,
    max_review_rounds: int = 3,
    input_func: Callable[[str], str] | None = None,
    output_func: Callable[..., Any] | None = None,
) -> ReviewDecision:
    """人工审核生成用例，返回审核决策。"""
    if input_func is None:
        input_func = input
    if output_func is None:
        output_func = print

    if not human_review:
        return ReviewDecision(status="approved")

    output_func()
    output_func("=" * 60)
    output_func(f"人工审核 [{endpoint.method}] {endpoint.path} 第 {review_round + 1} 轮")
    output_func("=" * 60)
    for idx, case in enumerate(cases, start=1):
        output_func(f"{idx}. {case.name}")
        output_func(f"   类型: {case.case_type}")
        output_func(f"   描述: {case.description}")
        output_func(f"   参数: {case.parameters}")
        output_func(f"   请求头: {case.headers}")
        output_func(f"   期望状态码: {case.expected_status}")
        output_func()

    if review_round >= max_review_rounds:
        return ReviewDecision(
            status="rejected",
            round=review_round,
            rejection_reason=f"人工审核反馈已达到最大轮次{max_review_rounds}，仍未通过",
        )

    while True:
        decision = input_func("审核结果 [a=通过, f=反馈修改, r=拒绝]: ").strip().lower()
        if decision in {"a", "f", "r"}:
            break
        output_func("输入无效，请输入 a、f 或 r。")

    if decision == "a":
        return ReviewDecision(status="approved")

    if decision == "r":
        return ReviewDecision(
            status="rejected",
            rejection_reason="人工审核拒绝执行当前接口用例",
        )

    while True:
        feedback = input_func("请输入需要反馈给 LLM 的问题: ").strip()
        if feedback:
            break
        output_func("反馈不能为空。")

    return ReviewDecision(
        status="regenerate",
        feedback=feedback,
        round=review_round + 1,
    )


def summarize_case_counts(cases: list[TestCase]) -> tuple[int, int]:
    """统计正常/异常用例数。"""
    normal_count = sum(1 for case in cases if case.case_type == "normal")
    abnormal_count = sum(1 for case in cases if case.case_type == "abnormal")
    return normal_count, abnormal_count
