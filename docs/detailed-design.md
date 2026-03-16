# Apiauto-Agent 详细设计文档

> API接口测试用例自动生成与执行智能体
> 版本：v0.1.0 | 日期：2026-03-16

---

## 目录

1. [项目概述](#1-项目概述)
2. [系统架构](#2-系统架构)
3. [业务流程](#3-业务流程)
4. [模块详细设计](#4-模块详细设计)
5. [数据模型](#5-数据模型)
6. [接口列表](#6-接口列表)
7. [用例生成策略](#7-用例生成策略)
8. [技术实现路线](#8-技术实现路线)
9. [目录结构](#9-目录结构)
10. [配置与部署](#10-配置与部署)
11. [扩展规划](#11-扩展规划)

---

## 1. 项目概述

### 1.1 背景

在接口测试中，手动编写测试用例耗时且容易遗漏。本项目开发一个 **Agent（智能体）**，输入一份 OpenAPI/Swagger YAML 接口定义文件，即可自动：

1. 解析接口的路径、方法、参数、约束条件
2. 生成覆盖正常场景和异常场景的测试用例
3. 调用外部 **接口A** 创建并执行这些用例
4. 输出结构化测试报告

### 1.2 核心价值

| 维度 | 说明 |
|------|------|
| **输入** | OpenAPI 3.x / Swagger 2.0 YAML 文件 |
| **输出** | 结构化测试报告（控制台 + JSON 文件） |
| **自动化** | 零人工编写用例，全自动解析→生成→执行→报告 |
| **覆盖度** | 正常用例（必填/全参/枚举/边界）+ 异常用例（缺参/类型错/越界/注入等） |

### 1.3 技术栈

| 组件 | 选型 | 版本要求 |
|------|------|----------|
| 编程语言 | Python | >= 3.10 |
| YAML 解析 | PyYAML | >= 6.0 |
| HTTP 客户端 | Requests | >= 2.28.0 |
| 测试框架 | pytest | >= 7.0（开发依赖） |
| 构建工具 | setuptools | >= 68.0 |

---

## 2. 系统架构

### 2.1 整体架构图

```
┌──────────────────────────────────────────────────────────────┐
│                        用户 / CI/CD                           │
│                            │                                  │
│                     CLI 命令行入口                             │
│                    (cli.py / __main__.py)                     │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│                    Agent 编排层                                │
│                      (agent.py)                               │
│                                                               │
│   ┌─────────┐    ┌──────────────┐    ┌────────────────┐      │
│   │  解析器  │───▶│  用例生成器   │───▶│    执行器       │      │
│   │(parser) │    │ (generator)  │    │  (executor)    │      │
│   └─────────┘    └──────────────┘    └───────┬────────┘      │
│                                              │               │
│                                     ┌────────┴────────┐      │
│                                     │                 │      │
│                              MockExecutor      ApiExecutor   │
│                              (开发/测试)       (生产对接)      │
└──────────────────────────────────────────────────────────────┘
                                                      │
                                                      ▼
                                              ┌──────────────┐
                                              │   接口A       │
                                              │ (外部服务)    │
                                              └──────────────┘
```

### 2.2 分层说明

| 层级 | 模块 | 职责 |
|------|------|------|
| **入口层** | `cli.py`, `__main__.py` | 命令行参数解析、日志配置、结果输出 |
| **编排层** | `agent.py` | 串联解析→生成→执行的完整流程，汇总报告 |
| **解析层** | `parser.py` | OpenAPI/Swagger YAML 文件解析，提取接口元数据 |
| **生成层** | `generator.py` | 基于参数约束，自动生成正常和异常测试用例 |
| **执行层** | `executor.py` | 调用接口A执行用例，支持 Mock 和真实两种模式 |

### 2.3 设计原则

- **策略模式**：执行器使用 `BaseExecutor` 抽象基类 + 工厂方法，Mock 和 API 模式可无缝切换
- **数据驱动**：所有中间数据使用 `dataclass` 定义，支持序列化/反序列化
- **单一职责**：解析、生成、执行三个核心步骤互相独立，可单独测试和替换
- **渐进式对接**：先 Mock 验证流程，后续切换到真实接口零代码改动

---

## 3. 业务流程

### 3.1 主流程图

```
┌─────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────┐
│  用户    │     │  YAML 解析   │     │  用例生成     │     │  用例执行     │     │  报告输出 │
│ 提供YAML │────▶│  提取接口     │────▶│  正常+异常    │────▶│  调用接口A    │────▶│  汇总统计 │
│  文件    │     │  参数信息     │     │  用例集合     │     │  获取结果     │     │  展示结果 │
└─────────┘     └──────────────┘     └──────────────┘     └──────────────┘     └──────────┘
```

### 3.2 详细流程描述

```
开始
 │
 ├─ 1. 用户输入
 │     ├─ 提供 OpenAPI YAML 文件路径
 │     ├─ 选择执行模式 (mock / api)
 │     ├─ 可选：接口过滤条件 (--filter)
 │     └─ 可选：用例类型 (all / normal / abnormal)
 │
 ├─ 2. YAML 文件解析 (parser.py)
 │     ├─ 读取 YAML 文件
 │     ├─ 识别规范版本 (OpenAPI 3.x / Swagger 2.0)
 │     ├─ 遍历 paths 下所有接口
 │     ├─ 对每个接口提取：
 │     │     ├─ path（路径）
 │     │     ├─ method（HTTP 方法）
 │     │     ├─ parameters（query/header/path/cookie 参数）
 │     │     ├─ requestBody（请求体 schema）
 │     │     └─ 参数约束（type, format, required, enum, min, max, minLength, maxLength, pattern）
 │     ├─ 递归解析 $ref 引用
 │     ├─ 合并 allOf 组合 schema
 │     └─ 输出: List[EndpointInfo]
 │
 ├─ 3. 可选：接口过滤
 │     └─ 根据 --filter 参数，只保留路径匹配的接口
 │
 ├─ 4. 测试用例生成 (generator.py)
 │     ├─ 对每个接口分别生成：
 │     │
 │     ├─ 【正常用例】
 │     │     ├─ 必填参数用例：只传所有 required=true 的参数
 │     │     ├─ 全参数用例：传入全部参数（必填+可选）
 │     │     ├─ 枚举遍历用例：每个 enum 参数的每个合法值各一个用例
 │     │     └─ 边界值用例：数值参数取 minimum 和 maximum
 │     │
 │     └─ 【异常用例】
 │           ├─ 缺少必填参数：逐个移除必填参数
 │           ├─ 参数类型错误：为每个参数传入错误类型的值
 │           ├─ 空值测试：null 值和空字符串
 │           ├─ 边界越界：数值低于 minimum / 超过 maximum
 │           ├─ 长度越界：字符串超过 maxLength
 │           ├─ 格式错误：email/date/datetime/url/uuid 传入非法格式
 │           ├─ 枚举外值：传入不在 enum 列表中的值
 │           ├─ 安全测试：XSS 注入、SQL 注入
 │           └─ 无参数请求：不传任何参数
 │
 ├─ 5. 测试用例执行 (executor.py)
 │     ├─ 根据 mode 创建执行器：
 │     │     ├─ mock → MockExecutor（本地模拟，不依赖外部服务）
 │     │     └─ api  → ApiExecutor（POST 到接口A）
 │     ├─ 逐个执行用例
 │     ├─ 记录每个用例的：
 │     │     ├─ HTTP 状态码
 │     │     ├─ 响应体
 │     │     ├─ 执行耗时
 │     │     └─ 是否通过
 │     └─ 输出: List[ExecutionResult]
 │
 ├─ 6. 报告生成 (agent.py)
 │     ├─ 按接口维度汇总统计
 │     │     ├─ 每个接口：总用例数、正常数、异常数、通过数、失败数
 │     │     └─ 每个用例：名称、结果、状态码、耗时
 │     ├─ 汇总全局统计
 │     │     ├─ 总接口数、总用例数
 │     │     ├─ 通过数、失败数
 │     │     └─ 通过率
 │     └─ 输出格式：
 │           ├─ 控制台文本摘要
 │           └─ 可选 JSON 文件 (--output)
 │
 └─ 结束
```

### 3.3 数据流转图

```
                    YAML文件
                       │
                       ▼
              ┌─────────────────┐
              │  parse_openapi  │
              │    _file()      │
              └────────┬────────┘
                       │
                List[EndpointInfo]
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
   generate_       generate_    generate_
   normal_cases    abnormal_    test_cases
       ()          cases()         ()
          │            │            │
          └────────────┼────────────┘
                       │
                 List[TestCase]
                       │
                       ▼
              ┌─────────────────┐
              │   Executor      │
              │ .execute_batch()│
              └────────┬────────┘
                       │
              List[ExecutionResult]
                       │
                       ▼
              ┌─────────────────┐
              │   TestReport    │
              │  .summary()     │
              │  .to_dict()     │
              └─────────────────┘
                   │         │
                   ▼         ▼
               控制台      JSON文件
               输出        报告
```

---

## 4. 模块详细设计

### 4.1 parser.py — YAML 解析器

**职责**：读取 OpenAPI/Swagger YAML 文件，提取所有接口的路径、方法、参数及约束信息。

#### 4.1.1 核心函数

| 函数 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `parse_openapi_file(file_path)` | YAML 文件路径 | `list[EndpointInfo]` | 主入口，自动识别版本并分发 |
| `_parse_openapi3(spec)` | 解析后的 dict | `list[EndpointInfo]` | 处理 OpenAPI 3.x 规范 |
| `_parse_swagger2(spec)` | 解析后的 dict | `list[EndpointInfo]` | 处理 Swagger 2.0 规范 |
| `_resolve_ref(spec, ref)` | spec + `$ref` 字符串 | `dict` | 解析 JSON Pointer 引用 |
| `_resolve_schema(spec, schema)` | spec + schema dict | `dict` | 递归解析 `$ref`、`allOf` |
| `_schema_to_params(spec, schema, ...)` | schema dict | `list[ParameterInfo]` | 将 JSON Schema properties 转为参数列表 |
| `_extract_param_constraints(schema)` | schema dict | `dict` | 提取 min/max/enum/pattern 等约束 |

#### 4.1.2 解析逻辑

```
OpenAPI 3.x 解析流程:
  paths → 遍历 path
    → 遍历 method (get/post/put/delete/patch)
      → 提取 summary, description, tags
      → 解析 parameters[] (query/header/path/cookie)
        → 每个 parameter 解析 schema + 约束
      → 解析 requestBody.content."application/json".schema
        → schema.properties 转为 body 参数列表

Swagger 2.0 解析流程:
  paths → 遍历 path
    → 遍历 method
      → 解析 parameters[]
        → in=body: 解析 schema.properties
        → in=query/path/header: 直接提取类型和约束
```

#### 4.1.3 支持的参数约束

| 约束字段 | JSON Schema 关键字 | 说明 |
|----------|-------------------|------|
| 类型 | `type` | string, integer, number, boolean, array, object |
| 格式 | `format` | email, date, date-time, uri, uuid, password |
| 必填 | `required` | 参数是否必填 |
| 枚举 | `enum` | 合法值列表 |
| 最小值 | `minimum` | 数值下界 |
| 最大值 | `maximum` | 数值上界 |
| 最小长度 | `minLength` | 字符串最短长度 |
| 最大长度 | `maxLength` | 字符串最长长度 |
| 正则 | `pattern` | 字符串正则约束 |
| 默认值 | `default` | 参数默认值 |
| 示例 | `example` | 参数示例值 |

---

### 4.2 generator.py — 用例生成器

**职责**：基于 `EndpointInfo` 中的参数信息和约束，自动生成覆盖正常和异常场景的测试用例。

#### 4.2.1 核心函数

| 函数 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `generate_test_cases(endpoint)` | `EndpointInfo` | `list[TestCase]` | 生成全部用例（正常+异常） |
| `generate_normal_cases(endpoint)` | `EndpointInfo` | `list[TestCase]` | 只生成正常用例 |
| `generate_abnormal_cases(endpoint)` | `EndpointInfo` | `list[TestCase]` | 只生成异常用例 |
| `_generate_valid_value(param)` | `ParameterInfo` | `Any` | 为单个参数生成合法值 |
| `_generate_invalid_values(param)` | `ParameterInfo` | `list[tuple]` | 为单个参数生成多种非法值 |

#### 4.2.2 合法值生成策略

```
优先级：example > default > enum[0] > 按类型生成

按类型生成规则:
  integer → random.randint(minimum or 1, maximum or 100)
  number  → random.uniform(minimum or 0.0, maximum or 100.0)
  boolean → True
  array   → []
  object  → {}
  string  → 根据 format 判断:
    email     → "test@example.com"
    date      → "2026-01-15"
    date-time → "2026-01-15T10:30:00Z"
    uri/url   → "https://example.com"
    uuid      → "550e8400-e29b-41d4-a716-446655440000"
    password  → "P@ssw0rd123"
    phone     → "13800138000"
    其他       → "test_" + 随机字母(长度=minLength or 5)
```

#### 4.2.3 正常用例生成策略

| 编号 | 策略 | 说明 | 期望状态码 |
|------|------|------|-----------|
| N-1 | 必填参数 | 只传所有 required=true 的参数，值均合法 | 200 |
| N-2 | 全部参数 | 传入全部参数（必填+可选），值均合法 | 200 |
| N-3 | 枚举遍历 | 对每个 enum 参数，遍历所有合法枚举值，每值一个用例 | 200 |
| N-4 | 最小边界值 | 数值参数取 `minimum` 值 | 200 |
| N-5 | 最大边界值 | 数值参数取 `maximum` 值 | 200 |

#### 4.2.4 异常用例生成策略

| 编号 | 策略 | 方法 | 期望状态码 |
|------|------|------|-----------|
| A-1 | 缺少必填参数 | 逐个移除每个 required 参数 | 400 |
| A-2 | 空值 (null) | 将参数值设为 `None` | 400 |
| A-3 | 空字符串 | 将参数值设为 `""` | 400 |
| A-4 | 类型错误 | integer/number → 传字符串 "abc"；string → 传数字；boolean → 传字符串 | 400 |
| A-5 | 低于最小值 | 数值参数传 `minimum - 1` | 400 |
| A-6 | 超过最大值 | 数值参数传 `maximum + 1` | 400 |
| A-7 | 极大值 | integer 参数传 `2^31` | 400 |
| A-8 | 负数 | integer 参数传 `-1` | 400 |
| A-9 | 超长字符串 | 字符串参数传 `maxLength + 10` 个字符，或 1000 个字符 | 400 |
| A-10 | 格式错误 | email → "not-an-email"；date → "2026-13-45" 等 | 400 |
| A-11 | 枚举外值 | 传入 "INVALID_ENUM_VALUE" | 400 |
| A-12 | XSS 注入 | 传入 `<script>alert(1)</script>` | 400 |
| A-13 | SQL 注入 | 传入 `' OR 1=1 --` | 400 |
| A-14 | 无参数请求 | 不传任何参数（当存在必填参数时） | 400 |

#### 4.2.5 用例生成数量估算

对于一个含有 N 个参数（其中 R 个必填、E 个有枚举共计 V 个枚举值、B 个有数值边界）的接口：

```
正常用例数 ≈ 1(必填) + 1(全参) + V(枚举遍历) + 2*B(边界值)
异常用例数 ≈ R(缺必填) + N*7~12(每参数异常值) + 1(无参数)
```

以 `POST /pets`（7个参数，2个必填，2个有枚举，3个有数值边界）为例：
- 正常用例：1 + 1 + 8 + 6 = **16** 个
- 异常用例：2 + 7*~9 + 1 ≈ **66** 个

---

### 4.3 executor.py — 执行器模块

**职责**：将生成的 `TestCase` 发送到接口A执行，返回执行结果。

#### 4.3.1 类层次结构

```
BaseExecutor (ABC)              ← 抽象基类
  ├── MockExecutor              ← Mock 模式（本地模拟）
  └── ApiExecutor               ← 真实模式（HTTP 调用接口A）

create_executor(mode, ...)      ← 工厂方法
```

#### 4.3.2 MockExecutor

- 不依赖外部服务，适合开发和测试阶段
- 正常用例：返回 `status_code=200`，`success=True`
- 异常用例：返回 `status_code=expected_status(默认400)`，`success=True`（异常用例返回预期错误码算通过）
- 模拟 10ms 延迟

#### 4.3.3 ApiExecutor

- 通过 HTTP POST 将测试用例发送到接口A
- 使用 `requests.Session` 保持连接复用
- 支持自定义 `headers`（如认证 Token）
- 超时控制，默认 30 秒
- 异常处理：网络异常时标记 `success=False` 并记录错误信息

#### 4.3.4 调用接口A的请求格式

```
POST {api_url}
Content-Type: application/json

{
    "test_case_name": "[正常] POST /pets - 必填参数",
    "description": "只传入所有必填参数，验证接口正常返回",
    "endpoint_path": "/pets",
    "method": "POST",
    "case_type": "normal",
    "parameters": {
        "name": "小白",
        "species": "dog"
    },
    "headers": {},
    "expected_status": 200
}
```

---

### 4.4 agent.py — Agent 编排模块

**职责**：作为核心协调器，串联解析→生成→执行的完整流程，汇总测试报告。

#### 4.4.1 ApiTestAgent 类

```python
class ApiTestAgent:
    def __init__(mode, api_url, timeout, headers)
    def run(yaml_file, endpoint_filter, case_type) -> TestReport
    def generate_only(yaml_file, endpoint_filter, case_type) -> list[TestCase]
```

| 方法 | 说明 |
|------|------|
| `__init__` | 初始化执行器（Mock 或 API 模式） |
| `run` | 完整流程：解析 → 过滤 → 生成 → 执行 → 报告 |
| `generate_only` | 只生成用例不执行，用于预览或导出 |
| `_process_endpoint` | 处理单个接口的生成和执行 |

#### 4.4.2 报告结构

```
TestReport
  ├── yaml_file: str                    # 源文件
  ├── total_endpoints: int              # 接口总数
  ├── total_cases: int                  # 用例总数
  ├── total_passed: int                 # 通过数
  ├── total_failed: int                 # 失败数
  └── endpoints: list[EndpointReport]   # 各接口明细
        ├── path: str
        ├── method: str
        ├── summary: str
        ├── total_cases / normal_cases / abnormal_cases
        ├── passed / failed
        └── results: list[dict]          # 每条用例的执行结果
              ├── test_case_name
              ├── case_type
              ├── success
              ├── status_code
              ├── response_body
              ├── error_message
              └── duration_ms
```

---

### 4.5 cli.py — 命令行入口

**职责**：提供用户友好的命令行接口。

#### 4.5.1 CLI 参数列表

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `yaml_file` | 位置参数 | 是 | - | OpenAPI YAML 文件路径 |
| `--mode` | 选项 | 否 | `mock` | 执行模式：`mock` / `api` |
| `--api-url` | 选项 | 条件 | `""` | 接口A的 URL（mode=api 时必填） |
| `--timeout` | 选项 | 否 | `30` | 请求超时秒数 |
| `--filter` | 选项 | 否 | `None` | 接口路径过滤关键字 |
| `--case-type` | 选项 | 否 | `all` | 用例类型：`all` / `normal` / `abnormal` |
| `--generate-only` | 开关 | 否 | `False` | 只生成用例不执行 |
| `--output, -o` | 选项 | 否 | `None` | JSON 报告输出路径 |
| `--verbose, -v` | 开关 | 否 | `False` | 详细日志输出 |

#### 4.5.2 使用示例

```bash
# 基本用法：Mock 模式运行
python -m apiauto_agent examples/petstore.yaml

# 只生成异常用例并预览
python -m apiauto_agent examples/petstore.yaml --case-type abnormal --generate-only

# 过滤特定接口并导出 JSON 报告
python -m apiauto_agent examples/petstore.yaml --filter /pets/{petId} -o report.json

# 对接真实接口A
python -m apiauto_agent api_spec.yaml --mode api --api-url http://10.0.0.1:8080/api/testcase

# 详细日志
python -m apiauto_agent examples/petstore.yaml -v
```

---

## 5. 数据模型

### 5.1 核心数据结构关系

```
┌──────────────┐     1:N     ┌─────────────────┐
│ EndpointInfo │────────────▶│  ParameterInfo   │
│  (接口信息)   │             │   (参数信息)      │
└──────────────┘             └─────────────────┘
       │
       │ 1:N (生成)
       ▼
┌──────────────┐     1:1     ┌─────────────────┐
│   TestCase   │────────────▶│ ExecutionResult  │
│  (测试用例)   │   (执行后)   │   (执行结果)      │
└──────────────┘             └─────────────────┘
       │                            │
       │ N:1                        │ N:1
       ▼                            ▼
┌──────────────┐             ┌─────────────────┐
│ TestReport   │◀────────────│ EndpointReport   │
│  (总报告)     │     1:N     │  (接口维度报告)   │
└──────────────┘             └─────────────────┘
```

### 5.2 ParameterInfo（参数信息）

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | 参数名称 |
| `location` | `str` | 参数位置：query / header / path / cookie / body |
| `required` | `bool` | 是否必填 |
| `param_type` | `str` | 参数类型：string / integer / number / boolean / array / object |
| `format` | `str \| None` | 格式约束：email / date / date-time / uri / uuid 等 |
| `description` | `str` | 参数描述 |
| `enum` | `list[str] \| None` | 枚举值列表 |
| `default` | `Any` | 默认值 |
| `minimum` | `float \| None` | 数值最小值 |
| `maximum` | `float \| None` | 数值最大值 |
| `min_length` | `int \| None` | 字符串最小长度 |
| `max_length` | `int \| None` | 字符串最大长度 |
| `pattern` | `str \| None` | 正则约束 |
| `example` | `Any` | 示例值 |

### 5.3 EndpointInfo（接口信息）

| 字段 | 类型 | 说明 |
|------|------|------|
| `path` | `str` | 接口路径，如 `/pets/{petId}` |
| `method` | `str` | HTTP 方法：GET / POST / PUT / DELETE / PATCH |
| `summary` | `str` | 接口摘要 |
| `description` | `str` | 接口详细描述 |
| `parameters` | `list[ParameterInfo]` | 所有参数列表（含 query/path/body 等） |
| `request_body_content_type` | `str` | 请求体类型，默认 `application/json` |
| `request_body_schema` | `dict \| None` | 请求体的原始 JSON Schema |
| `responses` | `dict[str, dict]` | 响应定义 |
| `tags` | `list[str]` | 接口标签 |

### 5.4 TestCase（测试用例）

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | 用例名称，如 `[正常] POST /pets - 必填参数` |
| `description` | `str` | 用例描述 |
| `endpoint_path` | `str` | 目标接口路径 |
| `method` | `str` | HTTP 方法 |
| `case_type` | `str` | 用例类型：`normal` / `abnormal` |
| `parameters` | `dict[str, Any]` | 请求参数键值对 |
| `headers` | `dict[str, str]` | 请求头 |
| `expected_status` | `int \| None` | 期望 HTTP 状态码 |

### 5.5 ExecutionResult（执行结果）

| 字段 | 类型 | 说明 |
|------|------|------|
| `test_case_name` | `str` | 用例名称 |
| `case_type` | `str` | 用例类型 |
| `success` | `bool` | 是否通过 |
| `status_code` | `int \| None` | 实际 HTTP 状态码 |
| `response_body` | `Any` | 响应体 |
| `error_message` | `str` | 错误信息（网络异常等） |
| `duration_ms` | `float` | 执行耗时（毫秒） |

---

## 6. 接口列表

### 6.1 接口A（外部依赖 — 测试用例执行服务）

Agent 将生成的测试用例通过 HTTP 请求发送到接口A。

#### 6.1.1 创建并执行测试用例

| 项目 | 说明 |
|------|------|
| **URL** | 由用户通过 `--api-url` 参数配置 |
| **方法** | `POST` |
| **Content-Type** | `application/json` |

**请求体**：

```json
{
    "test_case_name": "string    — 用例名称",
    "description":    "string    — 用例描述",
    "endpoint_path":  "string    — 被测接口路径，如 /pets",
    "method":         "string    — 被测接口HTTP方法，如 POST",
    "case_type":      "string    — normal 或 abnormal",
    "parameters":     "object    — 请求参数键值对",
    "headers":        "object    — 请求头键值对",
    "expected_status": "integer  — 期望的HTTP状态码"
}
```

**请求示例**：

```json
{
    "test_case_name": "[异常] POST /pets - 缺少必填参数name",
    "description": "不传必填参数'name'，期望返回400错误",
    "endpoint_path": "/pets",
    "method": "POST",
    "case_type": "abnormal",
    "parameters": {
        "species": "dog"
    },
    "headers": {},
    "expected_status": 400
}
```

**响应**：

| HTTP 状态码 | 含义 |
|-------------|------|
| 200 | 用例执行成功 |
| 4xx | 请求参数错误 |
| 5xx | 服务端错误（Agent 标记为失败） |

**判定逻辑**：
- `status_code < 500` → `success = True`
- `status_code >= 500` → `success = False`

---

### 6.2 Agent 内部接口（Python API）

以下接口供代码集成调用：

#### 6.2.1 ApiTestAgent.run()

```python
def run(
    yaml_file: str | Path,
    endpoint_filter: str | None = None,
    case_type: str = "all",        # "all" | "normal" | "abnormal"
) -> TestReport
```

**功能**：解析 YAML → 生成用例 → 执行用例 → 返回报告

#### 6.2.2 ApiTestAgent.generate_only()

```python
def generate_only(
    yaml_file: str | Path,
    endpoint_filter: str | None = None,
    case_type: str = "all",
) -> list[TestCase]
```

**功能**：只解析和生成用例，不执行

#### 6.2.3 parse_openapi_file()

```python
def parse_openapi_file(file_path: str | Path) -> list[EndpointInfo]
```

**功能**：独立使用解析器

#### 6.2.4 create_executor()

```python
def create_executor(
    mode: str = "mock",            # "mock" | "api"
    api_url: str = "",
    timeout: int = 30,
    headers: dict[str, str] | None = None,
) -> BaseExecutor
```

**功能**：工厂方法创建执行器

---

## 7. 用例生成策略

### 7.1 策略总览表

```
┌─────────────────────────────────────────────────────────────────┐
│                          用例生成策略                             │
├──────────────┬──────────────────────────────────────────────────┤
│              │  N-1  必填参数                                    │
│   正常用例    │  N-2  全部参数（必填+可选）                        │
│  (Normal)    │  N-3  枚举值遍历                                  │
│              │  N-4  数值最小边界                                 │
│              │  N-5  数值最大边界                                 │
├──────────────┼──────────────────────────────────────────────────┤
│              │  A-1   缺少必填参数（逐个）                        │
│              │  A-2   空值 null                                  │
│              │  A-3   空字符串 ""                                 │
│              │  A-4   类型错误（string→int, int→string...）       │
│   异常用例    │  A-5   低于最小值 (minimum - 1)                    │
│  (Abnormal)  │  A-6   超过最大值 (maximum + 1)                   │
│              │  A-7   极大值 (2^31)                               │
│              │  A-8   负数 (-1)                                   │
│              │  A-9   超长字符串 (maxLength + 10)                  │
│              │  A-10  格式错误 (email/date/url...)                │
│              │  A-11  枚举外值                                    │
│              │  A-12  XSS 注入                                   │
│              │  A-13  SQL 注入                                   │
│              │  A-14  无参数请求                                  │
└──────────────┴──────────────────────────────────────────────────┘
```

### 7.2 异常值生成的参数类型适配

| 参数类型 | 适用的异常策略 |
|----------|---------------|
| `string` | A-2, A-3, A-4(传数字), A-9(超长), A-10(格式错误), A-11(枚举外), A-12, A-13 |
| `integer` | A-2, A-3, A-4(传字符串/布尔), A-5(低于min), A-6(超过max), A-7(极大值), A-8(负数), A-12, A-13 |
| `number` | A-2, A-3, A-4(传字符串/布尔), A-5(低于min), A-6(超过max), A-12, A-13 |
| `boolean` | A-2, A-3, A-4(传字符串), A-12, A-13 |
| `array` | A-2, A-3, A-4(传字符串), A-12, A-13 |
| `object` | A-2, A-3, A-4(传字符串), A-12, A-13 |

---

## 8. 技术实现路线

### 8.1 已完成（Phase 1 — 当前版本 v0.1.0）

```
✅ OpenAPI 3.x / Swagger 2.0 YAML 文件解析
✅ $ref 引用递归解析 + allOf 合并
✅ 正常用例自动生成（必填/全参/枚举遍历/边界值）
✅ 异常用例自动生成（14 种异常策略）
✅ Mock 执行器（本地模拟，无需外部服务）
✅ 真实接口A执行器（HTTP POST 方式）
✅ Agent 编排层（解析→生成→执行→报告完整流程）
✅ CLI 命令行工具（支持过滤/导出/模式切换等）
✅ 结构化测试报告（控制台摘要 + JSON 文件导出）
✅ 10 个单元测试，全部通过
```

### 8.2 Phase 2 — 对接真实接口A

```
⬜ 确认接口A的实际 URL、认证方式、请求/响应格式
⬜ 根据接口A的实际响应调整判定逻辑
⬜ 添加认证支持（Token / API Key / OAuth）
⬜ 添加重试机制（网络抖动时自动重试）
⬜ 添加并发执行支持（线程池批量调用接口A）
```

### 8.3 Phase 3 — 增强用例生成

```
⬜ 支持参数间组合测试（正交实验法 / pairwise）
⬜ 支持接口间依赖编排（如先创建再查询再删除）
⬜ 支持自定义用例模板（用户可扩展生成规则）
⬜ 支持从 response schema 自动验证返回值字段和类型
⬜ 引入 LLM（大语言模型）智能生成更丰富的测试数据
```

### 8.4 Phase 4 — 平台化

```
⬜ 提供 Web UI 管理界面
⬜ 用例执行历史持久化（接入数据库）
⬜ 支持定时任务 / CI/CD 集成
⬜ 支持多环境配置（dev / staging / prod）
⬜ 测试报告可视化（图表统计）
```

### 8.5 数据库设计（Phase 4 预留）

当引入持久化存储后，预计需要以下表结构：

```
┌─────────────────────────────────┐
│         test_projects           │
├─────────────────────────────────┤
│ id            BIGINT PK         │
│ name          VARCHAR(100)      │
│ yaml_content  TEXT              │
│ created_at    DATETIME          │
│ updated_at    DATETIME          │
└──────────────┬──────────────────┘
               │ 1:N
               ▼
┌─────────────────────────────────┐
│         test_runs               │
├─────────────────────────────────┤
│ id            BIGINT PK         │
│ project_id    BIGINT FK         │
│ total_cases   INT               │
│ passed        INT               │
│ failed        INT               │
│ pass_rate     DECIMAL(5,2)      │
│ mode          VARCHAR(10)       │  ← mock / api
│ started_at    DATETIME          │
│ finished_at   DATETIME          │
└──────────────┬──────────────────┘
               │ 1:N
               ▼
┌─────────────────────────────────┐
│       test_case_results         │
├─────────────────────────────────┤
│ id            BIGINT PK         │
│ run_id        BIGINT FK         │
│ case_name     VARCHAR(200)      │
│ case_type     VARCHAR(10)       │  ← normal / abnormal
│ endpoint_path VARCHAR(200)      │
│ method        VARCHAR(10)       │
│ parameters    JSON              │
│ expected_status INT             │
│ actual_status   INT             │
│ response_body   JSON            │
│ success       BOOLEAN           │
│ duration_ms   FLOAT             │
│ error_message TEXT              │
│ created_at    DATETIME          │
└─────────────────────────────────┘
```

**表关系**：
- `test_projects` 1:N `test_runs`（一个项目多次执行）
- `test_runs` 1:N `test_case_results`（一次执行包含多个用例结果）

---

## 9. 目录结构

```
Apiauto-agent/
├── apiauto_agent/               # 主包
│   ├── __init__.py              # 包初始化，版本号
│   ├── __main__.py              # python -m 入口
│   ├── agent.py                 # Agent 编排层（核心控制器）
│   ├── cli.py                   # CLI 命令行入口
│   ├── executor.py              # 执行器（Mock + API 两种模式）
│   ├── generator.py             # 用例生成器（正常 + 异常）
│   └── parser.py                # OpenAPI/Swagger YAML 解析器
├── examples/                    # 示例文件
│   └── petstore.yaml            # 示例 OpenAPI 定义
├── tests/                       # 测试
│   ├── __init__.py
│   └── test_agent.py            # 单元测试（10个）
├── docs/                        # 文档
│   └── detailed-design.md       # 本文档
├── .gitignore
├── pyproject.toml               # 项目配置 + 构建配置
├── requirements.txt             # Python 依赖
├── LICENSE                      # Apache 2.0
└── README.md
```

---

## 10. 配置与部署

### 10.1 安装依赖

```bash
pip install -r requirements.txt
```

### 10.2 运行方式

```bash
# 方式1: 模块方式运行
python -m apiauto_agent <yaml_file> [options]

# 方式2: 安装后使用命令
pip install -e .
apiauto-agent <yaml_file> [options]

# 方式3: Python 代码调用
from apiauto_agent.agent import ApiTestAgent
agent = ApiTestAgent(mode="mock")
report = agent.run("api_spec.yaml")
print(report.summary())
```

### 10.3 对接真实接口A

```bash
python -m apiauto_agent api_spec.yaml \
    --mode api \
    --api-url http://your-server:8080/api/testcase \
    --timeout 60 \
    -o report.json
```

---

## 11. 扩展规划

| 方向 | 说明 | 优先级 |
|------|------|--------|
| 认证支持 | 支持 Bearer Token / API Key / Basic Auth | 高 |
| 并发执行 | 线程池并发调用接口A，提升执行效率 | 高 |
| 参数组合 | 正交实验法/pairwise 生成参数组合用例 | 中 |
| 接口编排 | 支持多接口串联（创建→查询→更新→删除） | 中 |
| LLM 增强 | 用大模型生成更智能的测试数据和边界场景 | 中 |
| Web UI | 提供管理界面、历史记录、可视化报告 | 低 |
| 数据库 | 用例和结果持久化存储 | 低 |
| CI/CD 集成 | 提供 GitHub Actions / Jenkins 插件 | 低 |
