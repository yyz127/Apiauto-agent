# Apiauto-agent

接口测试智能体：输入 OpenAPI/Swagger YAML，自动解析接口并生成测试用例执行。

## 功能

- 解析 OpenAPI 3.x / Swagger 2.0
- 自动生成正常 / 异常测试用例
- 支持执行模式：`mock` / `api`
- 支持用例生成模式：`rule`（规则）/ `llm`（大模型）
- `llm` 模式在模型调用失败或输出非法时，会自动降级回 `rule` 生成，保证流程可用

## 快速开始

```bash
python -m apiauto_agent examples/petstore.yaml
```

仅生成用例：

```bash
python -m apiauto_agent examples/petstore.yaml --generate-only
```

使用大模型生成用例：

```bash
python -m apiauto_agent examples/petstore.yaml \
  --case-generator llm \
  --llm-api-url http://localhost:8000/v1/chat/completions \
  --llm-api-key YOUR_KEY \
  --llm-model gpt-4o-mini
```
