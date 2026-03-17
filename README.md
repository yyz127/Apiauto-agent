# Apiauto-agent

接口测试智能体：输入 OpenAPI/Swagger YAML，通过 LLM 自动生成测试用例并执行。基于 LangGraph 图引擎驱动完整测试流程。

## 功能

- 解析 OpenAPI 3.x / Swagger 2.0
- LLM 驱动的测试用例自动生成（正常 / 异常）
- 支持执行模式：`mock`（默认）/ `api`（真实接口）
- 基于 LangGraph 的图引擎编排，支持可观测性与条件路由
- 可选人工审核（`--human-review`）
- JSON 报告输出

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

指定 API Key 和模型：

```bash
python -m apiauto_agent examples/petstore.yaml \
  --llm-api-url http://localhost:8000/v1/chat/completions \
  --llm-api-key YOUR_KEY \
  --llm-model gpt-4o-mini
```

使用真实接口A执行：

```bash
python -m apiauto_agent examples/petstore.yaml \
  --llm-api-url http://localhost:8000/v1/chat/completions \
  --mode api \
  --api-url http://localhost:8080/report/generatAutotestReport \
  --target-base-url http://localhost:8080 \
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
| `header` | string | 请求头的 JSON 字符串 |
| `param` | list\<string\> | 请求参数列表，每个元素是一个 JSON 字符串 |
| `uuid` | string | 测试任务唯一标识 |
| `env` | string | 环境标识（dev / uat / test） |

接口A是异步执行的，接收请求后立即返回，测试完成后通过回调通知结果。

## 架构

基于 LangGraph StateGraph 的流水线：

```
START → parse_yaml → select_endpoint → generate_cases
      → review_cases → execute_cases → collect_results
      → [has_more_endpoints?] → select_endpoint / generate_report → END
```

## 项目结构

```
apiauto_agent/
├── cli.py             # 命令行入口
├── agent.py           # Agent 主逻辑
├── parser.py          # OpenAPI/Swagger 解析
├── llm_generator.py   # LLM 用例生成
├── generator.py       # 生成器接口
├── executor.py        # 用例执行（Mock / 接口A）
├── graph.py           # LangGraph 图定义
├── nodes.py           # 图节点实现
└── state.py           # 图状态定义
```
