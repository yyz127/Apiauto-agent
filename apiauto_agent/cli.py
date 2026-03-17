"""命令行入口

提供CLI接口，方便用户直接通过命令行使用Agent。
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from .agent import ApiTestAgent


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def main():
    parser = argparse.ArgumentParser(
        description="API测试用例自动生成与执行Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # Mock模式运行（默认使用LangGraph图引擎）
  python -m apiauto_agent examples/petstore.yaml --llm-api-url http://localhost:8000/v1/chat/completions

  # 只生成用例，不执行
  python -m apiauto_agent examples/petstore.yaml --llm-api-url http://localhost:8000/v1/chat/completions --generate-only

  # 只生成异常用例
  python -m apiauto_agent examples/petstore.yaml --llm-api-url http://localhost:8000/v1/chat/completions --case-type abnormal

  # 过滤特定接口
  python -m apiauto_agent examples/petstore.yaml --llm-api-url http://localhost:8000/v1/chat/completions --filter /pets

  # 使用真实接口
  python -m apiauto_agent examples/petstore.yaml --llm-api-url http://localhost:8000/v1/chat/completions --mode api --api-url http://localhost:8080/api/testcase

  # 启用人工审核
  python -m apiauto_agent examples/petstore.yaml --llm-api-url http://localhost:8000/v1/chat/completions --human-review

  # 输出JSON报告
  python -m apiauto_agent examples/petstore.yaml --llm-api-url http://localhost:8000/v1/chat/completions --output report.json
        """,
    )
    parser.add_argument("yaml_file", help="OpenAPI/Swagger YAML文件路径")
    parser.add_argument("--mode", choices=["mock", "api"], default="mock",
                        help="执行模式: mock(默认) 或 api(真实接口)")
    parser.add_argument("--api-url", default="",
                        help="接口A的URL地址（mode=api时必填）")
    parser.add_argument("--timeout", type=int, default=30,
                        help="请求超时时间（秒），默认30")
    parser.add_argument("--filter", dest="endpoint_filter", default=None,
                        help="过滤接口路径，只测试包含该字符串的接口")
    parser.add_argument("--case-type", choices=["all", "normal", "abnormal"], default="all",
                        help="用例类型: all(默认), normal(正常), abnormal(异常)")
    parser.add_argument("--generate-only", action="store_true",
                        help="只生成用例，不执行")
    parser.add_argument("--output", "-o", default=None,
                        help="输出JSON报告到文件")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="详细输出")
    parser.add_argument("--llm-api-url", required=True,
                        help="大模型API地址（必填，OpenAI兼容接口）")
    parser.add_argument("--llm-api-key", default="",
                        help="大模型API Key（可选）")
    parser.add_argument("--llm-model", default="gpt-4o-mini",
                        help="大模型名称，默认gpt-4o-mini")
    parser.add_argument("--human-review", action="store_true",
                        help="启用人工审核")
    parser.add_argument("--uuid", default="",
                        help="测试任务唯一标识（mode=api时使用，不传则自动生成）")
    parser.add_argument("--env", default="",
                        help="环境标识: dev, uat, test（mode=api时使用）")
    parser.add_argument("--target-base-url", default="",
                        help="被测接口的基础URL（mode=api时使用，如 http://localhost:8080）")
    parser.add_argument("--target-headers", default="",
                        help="被测接口的请求头（JSON字符串），如 '{\"Cookie\":\"XingheToken=xxx\"}'")

    args = parser.parse_args()
    setup_logging(args.verbose)

    # 验证YAML文件存在
    yaml_path = Path(args.yaml_file)
    if not yaml_path.exists():
        print(f"错误: 文件不存在: {args.yaml_file}", file=sys.stderr)
        sys.exit(1)

    # 自动生成 uuid（如果未指定且为 api 模式，使用基于时间的 UUID v1）
    task_uuid = args.uuid
    if not task_uuid and args.mode == "api":
        import uuid
        task_uuid = str(uuid.uuid1())

    # 解析 target-headers
    target_headers = {}
    if args.target_headers:
        try:
            target_headers = json.loads(args.target_headers)
        except json.JSONDecodeError:
            print("错误: --target-headers 不是合法的JSON字符串", file=sys.stderr)
            sys.exit(1)

    # 创建Agent
    agent = ApiTestAgent(
        mode=args.mode,
        api_url=args.api_url,
        timeout=args.timeout,
        llm_api_url=args.llm_api_url,
        llm_api_key=args.llm_api_key,
        llm_model=args.llm_model,
        uuid=task_uuid,
        env=args.env,
        target_base_url=args.target_base_url,
        target_headers=target_headers,
    )

    if args.generate_only:
        # 只生成用例
        cases = agent.generate_only(
            yaml_file=args.yaml_file,
            endpoint_filter=args.endpoint_filter,
            case_type=args.case_type,
        )
        print(f"\n共生成 {len(cases)} 个测试用例:\n")
        for i, tc in enumerate(cases, 1):
            print(f"  {i}. {tc.name}")
            print(f"     {tc.description}")
            print(f"     参数: {json.dumps(tc.parameters, ensure_ascii=False, default=str)}")
            print()

        if args.output:
            data = [tc.to_dict() for tc in cases]
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"用例已保存到: {args.output}")
    else:
        # LangGraph 模式
        report = agent.run_graph(
            yaml_file=args.yaml_file,
            endpoint_filter=args.endpoint_filter,
            case_type=args.case_type,
            human_review=args.human_review,
        )
        print(report.summary())

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
            print(f"\nJSON报告已保存到: {args.output}")


if __name__ == "__main__":
    main()
