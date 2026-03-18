"""生成用例检查逻辑。"""

from .generator import TestCase
from .exceptions import CaseGenerationError
from .parser import EndpointInfo


def validate_generated_cases(
    endpoint: EndpointInfo,
    cases: list[TestCase],
    requested_case_type: str = "all",
) -> list[TestCase]:
    """校验生成用例是否满足最小执行要求。

    注意: endpoint_path 和 method 由 _to_test_cases() 从 endpoint 强制赋值，
    无需重复校验。
    """
    if not cases:
        raise CaseGenerationError("LLM未生成任何有效用例")

    for index, case in enumerate(cases, start=1):
        if not case.name.strip():
            raise CaseGenerationError(f"第{index}个用例缺少名称")
        if case.case_type not in {"normal", "abnormal"}:
            raise CaseGenerationError(f"第{index}个用例case_type非法: {case.case_type}")
        if requested_case_type != "all" and case.case_type != requested_case_type:
            raise CaseGenerationError(
                f"第{index}个用例类型与请求不一致: 期望{requested_case_type}, 实际{case.case_type}"
            )
        if not isinstance(case.parameters, dict):
            raise CaseGenerationError(f"第{index}个用例parameters必须是对象")
        if not isinstance(case.headers, dict):
            raise CaseGenerationError(f"第{index}个用例headers必须是对象")
        if case.expected_status is not None and not isinstance(case.expected_status, int):
            raise CaseGenerationError(f"第{index}个用例expected_status必须是整数")

    return cases
