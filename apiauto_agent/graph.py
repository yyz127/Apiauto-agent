"""LangGraph 图定义

组装 StateGraph，定义节点和边的拓扑关系。
"""

from langgraph.graph import StateGraph, START, END

from .state import ApiTestState
from . import nodes


def build_graph(checkpointer=None):
    """构建并编译 API 测试 Agent 的 LangGraph StateGraph。

    图拓扑:
        START → parse_yaml → select_endpoint → generate_cases
              → review_cases → execute_cases → collect_results
              → [has_more_endpoints] → select_endpoint / generate_report → END

    Args:
        checkpointer: 可选的 LangGraph Checkpointer，用于断点续跑。

    Returns:
        编译后的 CompiledGraph 实例。
    """
    builder = StateGraph(ApiTestState)

    # ── 注册节点 ──
    builder.add_node("parse_yaml", nodes.parse_yaml)
    builder.add_node("select_endpoint", nodes.select_endpoint)
    builder.add_node("generate_cases", nodes.generate_cases)
    builder.add_node("review_cases", nodes.review_cases)
    builder.add_node("execute_cases", nodes.execute_cases)
    builder.add_node("collect_results", nodes.collect_results)
    builder.add_node("generate_report", nodes.generate_report)

    # ── 普通边 ──
    builder.add_edge(START, "parse_yaml")
    builder.add_edge("parse_yaml", "select_endpoint")
    builder.add_edge("select_endpoint", "generate_cases")
    builder.add_edge("generate_cases", "review_cases")
    builder.add_edge("review_cases", "execute_cases")
    builder.add_edge("execute_cases", "collect_results")
    builder.add_edge("generate_report", END)

    # ── 条件边 ──
    builder.add_conditional_edges(
        "collect_results",
        nodes.has_more_endpoints,
        {"select_endpoint": "select_endpoint", "generate_report": "generate_report"},
    )

    return builder.compile(checkpointer=checkpointer)


def get_graph_mermaid() -> str:
    """获取图的 Mermaid 可视化表示。"""
    graph = build_graph()
    return graph.get_graph().draw_mermaid()
