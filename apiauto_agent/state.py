"""LangGraph 状态定义

定义 API 测试 Agent 的共享状态 Schema。
"""

from typing import Any, Literal, TypedDict


class ApiTestState(TypedDict, total=False):
    """LangGraph StateGraph 的状态结构。

    所有节点通过读写此状态进行通信。
    """

    # ── 输入参数（由 CLI 初始化） ──
    yaml_file: str
    mode: Literal["mock", "api"]
    case_generator: Literal["rule", "llm"]
    api_url: str
    timeout: int
    headers: dict[str, str]
    endpoint_filter: str
    case_type: Literal["all", "normal", "abnormal"]
    human_review: bool

    # ── LLM 配置 ──
    llm_api_url: str
    llm_api_key: str
    llm_model: str

    # ── 流程状态（节点间传递） ──
    endpoints: list[dict[str, Any]]       # 解析后的 EndpointInfo (dict形式)
    current_index: int                     # 当前处理的接口索引
    current_endpoint: dict[str, Any]       # 当前接口信息
    current_cases: list[dict[str, Any]]    # 当前接口生成的 TestCase (dict形式)
    generation_method: str                 # "llm" / "rule" / "rule_fallback"
    generation_failed: bool                # LLM 生成是否失败

    # ── 执行结果 ──
    current_results: list[dict[str, Any]]  # 当前接口的 ExecutionResult (dict形式)
    endpoint_reports: list[dict[str, Any]] # 所有接口的 EndpointReport (dict形式)

    # ── 最终输出 ──
    report: dict[str, Any]                 # 最终 TestReport
    error: str                             # 错误信息


def create_initial_state(
    yaml_file: str,
    mode: str = "mock",
    case_generator: str = "rule",
    api_url: str = "",
    timeout: int = 30,
    headers: dict[str, str] | None = None,
    endpoint_filter: str = "",
    case_type: str = "all",
    human_review: bool = False,
    llm_api_url: str = "",
    llm_api_key: str = "",
    llm_model: str = "gpt-4o-mini",
) -> ApiTestState:
    """从 CLI 参数构建初始状态。"""
    return ApiTestState(
        yaml_file=yaml_file,
        mode=mode,
        case_generator=case_generator,
        api_url=api_url,
        timeout=timeout,
        headers=headers or {},
        endpoint_filter=endpoint_filter,
        case_type=case_type,
        human_review=human_review,
        llm_api_url=llm_api_url,
        llm_api_key=llm_api_key,
        llm_model=llm_model,
        endpoints=[],
        current_index=0,
        current_endpoint={},
        current_cases=[],
        generation_method="",
        generation_failed=False,
        current_results=[],
        endpoint_reports=[],
        report={},
        error="",
    )
