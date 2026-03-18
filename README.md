# Apiauto-agent

接口测试智能体：输入 OpenAPI/Swagger YAML，通过 LLM 自动生成测试用例，并通过 LangGraph 图引擎驱动完整测试流程。

## 功能

- 解析 OpenAPI 3.x / Swagger 2.0
- LLM 驱动的测试用例自动生成（正常 / 异常）
- 生成结果的最小有效性检查
- 支持执行模式：`mock`（默认）/ `api`（真实接口）
- 基于 LangGraph 的图引擎编排，支持条件路由
- 可选人工审核（`--human-review`）
- 人工审核可反馈问题并驱动 LLM 重新生成用例
- JSON 报告输出

## 当前入口

- 完整执行入口：`ApiTestAgent.run_graph()`
- 仅生成入口：`ApiTestAgent.generate_only()`
- CLI 默认走完整图流程，不存在 `--use-graph` 开关

## 安装

需要 Python >= 3.10。

```bash
pip install -e .
```

依赖：pyyaml, requests, langgraph, langchain-core

## 快速开始

基本用法（Mock 模式）：

```bash
python -m apiauto_agent examples/petstore.yaml \
  --llm-api-url http://localhost:8000/v1/chat/completions
```

仅生成用例，不执行：

```bash
python -m apiauto_agent examples/petstore.yaml \
  --llm-api-url http://localhost:8000/v1/chat/completions \
  --generate-only
```

启用人工审核：

```bash
python -m apiauto_agent examples/petstore.yaml \
  --llm-api-url http://localhost:8000/v1/chat/completions \
  --human-review
```

启用后，终端会在每个接口生成并校验完成后展示用例列表。人工可选择：
- `a`：审核通过，继续执行
- `f`：输入反馈问题，返回 LLM 重新生成
- `r`：拒绝当前接口，标记为生成失败并跳过执行

指定 API Key 和模型：

```bash
python -m apiauto_agent examples/petstore.yaml \
  --llm-api-url http://localhost:8000/v1/chat/completions \
  --llm-api-key YOUR_KEY \
  --llm-model gpt-4o-mini
```

使用真实接口A执行（带 Cookie 认证）：

```bash
python -m apiauto_agent examples/petstore.yaml \
  --llm-api-url http://localhost:8000/v1/chat/completions \
  --mode api \
  --api-url http://localhost:8080/report/generatAutotestReport \
  --target-base-url http://localhost:8080 \
  --target-headers '{"Cookie":"XingheToken=eyJhbGci...","Content-Type":"application/json"}' \
  --env dev
```

输出 JSON 报告：

```bash
python -m apiauto_agent examples/petstore.yaml \
  --llm-api-url http://localhost:8000/v1/chat/completions \
  --output report.json
```

## CLI 参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `yaml_file` | OpenAPI/Swagger YAML 文件路径（位置参数） | — |
| `--llm-api-url` | 大模型 API 地址（必填，OpenAI 兼容接口） | — |
| `--llm-api-key` | 大模型 API Key | 空 |
| `--llm-model` | 大模型名称 | `gpt-4o-mini` |
| `--mode` | 执行模式：`mock` 或 `api` | `mock` |
| `--api-url` | 接口A的 URL 地址（`mode=api` 时必填） | 空 |
| `--target-base-url` | 被测接口的基础 URL（`mode=api` 时使用） | 空 |
| `--target-headers` | 被测接口的请求头（JSON 字符串，如 Cookie/Token），会合并到每个用例的 header 中 | 空 |
| `--uuid` | 测试任务唯一标识（`mode=api` 时使用，不传则自动生成） | 空 |
| `--env` | 环境标识：`dev`、`uat`、`test`（`mode=api` 时使用） | 空 |
| `--timeout` | 请求超时时间（秒） | `30` |
| `--filter` | 过滤接口路径，只测试包含该字符串的接口 | — |
| `--case-type` | 用例类型：`all`、`normal`、`abnormal` | `all` |
| `--generate-only` | 只生成用例，不执行 | — |
| `--human-review` | 启用人工审核 | — |
| `--output` / `-o` | 输出 JSON 报告到文件 | — |
| `--verbose` / `-v` | 详细输出 | — |

## 接口A对接说明

`api` 模式下，Agent 将测试用例逐个发送到接口A（`POST /report/generatAutotestReport`），请求格式如下：

```json
{
  "url": "http://target-host/pets",
  "header": "{\"Content-Type\":\"application/json\"}",
  "param": ["{\"limit\":10,\"status\":\"available\"}"],
  "uuid": "550e8400-e29b-41d4-a716-446655440000",
  "env": "dev"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `url` | string | 被测接口的完整 URL（`--target-base-url` + 接口路径） |
| `header` | string | 请求头的 JSON 字符串（`--target-headers` 与用例 headers 合并） |
| `param` | list\<string\> | 请求参数列表，每个元素是一个 JSON 字符串 |
| `uuid` | string | 测试任务唯一标识 |
| `env` | string | 环境标识（dev / uat / test） |

接口A当前按同步方式返回结果。仓库中的 Java `TestReportController.java` 已改为：

- 接收 `ReportGenerateRequest`
- 同步调用 `generatReport(...).get()`
- 成功直接返回 `Result.ok(result)`
- 不再使用回调

如果某个接口的 LLM 用例生成失败，Agent 会将该接口显式标记为“生成失败”，并跳过执行阶段，不会进入伪成功报告。

## 架构

基于 LangGraph StateGraph 的流水线：

```
START → parse_yaml → select_endpoint → generate_cases
      → [生成成功?] → review_cases / collect_results
      → [审核结果] → execute_cases / generate_cases / collect_results
      → [has_more_endpoints?] → select_endpoint / generate_report → END
```

其中：

- `generate_cases` 节点负责调用 LLM，并完成最小有效性检查
- `review_cases` 节点负责人工审核通过 / 反馈重生成 / 拒绝
- `collect_results` 节点负责汇总接口级报告并推进到下一个接口

## 当前限制

以下是当前代码里的真实限制：

1. 图模式没有单独的 YAML 解析失败终止分支
2. `ApiExecutor` 还没有独立的请求渲染层，`path/query/header/body` 没有严格拆分
3. `ApiExecutor` 当前仍以 `status_code < 500` 作为成功判定
4. `requestBody` 仍然只取第一个 `content-type`

## 项目结构

```
apiauto_agent/
├── cli.py             # 命令行入口
├── agent.py           # Agent 入口和报告对象
├── case_checks.py     # 生成结果校验
├── endpoint_workflow.py # 单接口业务逻辑
├── parser.py          # OpenAPI/Swagger 解析
├── llm_generator.py   # LLM 用例生成
├── generator.py       # 规则生成器
├── executor.py        # 用例执行（Mock / 接口A）
├── graph.py           # LangGraph 图定义
├── nodes.py           # 图节点实现
├── state.py           # 图状态定义
└── TestReportController.java # 接口A Java 控制器示例
```
