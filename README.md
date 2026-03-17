# Apiauto-agent

接口测试智能体：输入 OpenAPI/Swagger YAML，通过 LLM 自动生成测试用例并执行。

## 功能

- 解析 OpenAPI 3.x / Swagger 2.0
- LLM 驱动的测试用例自动生成（正常 / 异常）
- 支持执行模式：`mock`（默认）/ `api`（真实接口）
- LangGraph 图引擎模式（`--use-graph`，实验性功能）
- 可选人工审核（`--human-review`，需配合 `--use-graph`）
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

使用 LangGraph 图引擎模式：

```bash
python -m apiauto_agent examples/petstore.yaml \
  --llm-api-url http://localhost:8000/v1/chat/completions \
  --use-graph
```

指定 API Key 和模型：

```bash
python -m apiauto_agent examples/petstore.yaml \
  --llm-api-url http://localhost:8000/v1/chat/completions \
  --llm-api-key YOUR_KEY \
  --llm-model gpt-4o-mini
```

使用真实接口执行：

```bash
python -m apiauto_agent examples/petstore.yaml \
  --llm-api-url http://localhost:8000/v1/chat/completions \
  --mode api \
  --api-url http://localhost:8080/api/testcase
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
| `--api-url` | 真实接口 URL（`mode=api` 时必填） | 空 |
| `--timeout` | 请求超时时间（秒） | `30` |
| `--filter` | 过滤接口路径，只测试包含该字符串的接口 | — |
| `--case-type` | 用例类型：`all`、`normal`、`abnormal` | `all` |
| `--generate-only` | 只生成用例，不执行 | — |
| `--use-graph` | 使用 LangGraph 图引擎运行（实验性功能） | — |
| `--human-review` | 启用人工审核（需配合 `--use-graph`） | — |
| `--output` / `-o` | 输出 JSON 报告到文件 | — |
| `--verbose` / `-v` | 详细输出 | — |

## 项目结构

```
apiauto_agent/
├── cli.py             # 命令行入口
├── agent.py           # Agent 主逻辑
├── parser.py          # OpenAPI/Swagger 解析
├── llm_generator.py   # LLM 用例生成
├── generator.py       # 生成器接口
├── executor.py        # 用例执行
├── graph.py           # LangGraph 图定义
├── nodes.py           # 图节点实现
└── state.py           # 图状态定义
```
