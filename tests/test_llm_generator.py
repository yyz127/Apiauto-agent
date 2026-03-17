"""测试LLM用例生成能力"""

from apiauto_agent.llm_generator import LLMCaseGenerator, SYSTEM_PROMPT
from apiauto_agent.parser import EndpointInfo, ParameterInfo
import requests


def _fake_endpoint() -> EndpointInfo:
    return EndpointInfo(
        path="/pets",
        method="POST",
        summary="创建宠物",
        parameters=[
            ParameterInfo(name="name", location="body", required=True, param_type="string"),
            ParameterInfo(name="age", location="body", required=False, param_type="integer"),
        ],
    )


class _FakeResp:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "choices": [
                {
                    "message": {
                        "content": '[{"name":"[正常] POST /pets - 基础","description":"最小必填参数","case_type":"normal","parameters":{"name":"小白"},"expected_status":200}]'
                    }
                }
            ]
        }


def test_llm_generator_success(monkeypatch):
    def _fake_post(*args, **kwargs):
        return _FakeResp()

    monkeypatch.setattr("apiauto_agent.llm_generator.requests.post", _fake_post)

    g = LLMCaseGenerator(api_url="http://mock-llm.local/v1/chat/completions")
    cases = g.generate_cases(_fake_endpoint(), case_type="normal")

    assert len(cases) == 1
    assert cases[0].case_type == "normal"
    assert cases[0].parameters["name"] == "小白"


def test_llm_generator_failed_returns_empty(monkeypatch):
    def _fake_post(*args, **kwargs):
        raise requests.RequestException("network error")

    monkeypatch.setattr("apiauto_agent.llm_generator.requests.post", _fake_post)

    g = LLMCaseGenerator(api_url="http://mock-llm.local/v1/chat/completions", max_retries=1)
    cases = g.generate_cases(_fake_endpoint(), case_type="normal")
    assert cases == []


def test_llm_generator_supports_markdown_json(monkeypatch):
    class _MarkdownResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": """```json
[{"name":"md-case","description":"from markdown","case_type":"normal","parameters":{"name":"小黑"},"expected_status":200}]
```"""
                        }
                    }
                ]
            }

    monkeypatch.setattr("apiauto_agent.llm_generator.requests.post", lambda *args, **kwargs: _MarkdownResp())

    g = LLMCaseGenerator(api_url="http://mock-llm.local/v1/chat/completions")
    cases = g.generate_cases(_fake_endpoint(), case_type="normal")
    assert len(cases) == 1
    assert cases[0].name == "md-case"


def test_llm_generator_invalid_case_type():
    g = LLMCaseGenerator(api_url="http://mock-llm.local/v1/chat/completions")
    try:
        g.generate_cases(_fake_endpoint(), case_type="invalid")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_llm_generator_retry(monkeypatch):
    """测试 LLM 重试机制"""
    call_count = 0

    def _flaky_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise requests.RequestException("first attempt fails")
        return _FakeResp()

    monkeypatch.setattr("apiauto_agent.llm_generator.requests.post", _flaky_post)

    g = LLMCaseGenerator(api_url="http://mock-llm.local/v1/chat/completions", max_retries=2)
    cases = g.generate_cases(_fake_endpoint(), case_type="normal")
    assert len(cases) == 1
    assert call_count == 2


def test_system_prompt_contains_strategies():
    """验证系统提示词包含关键测试策略"""
    assert "边界值" in SYSTEM_PROMPT
    assert "必填参数" in SYSTEM_PROMPT
    assert "类型错误" in SYSTEM_PROMPT
    assert "XSS" in SYSTEM_PROMPT
    assert "SQL" in SYSTEM_PROMPT
    assert "枚举" in SYSTEM_PROMPT


def test_prompt_includes_response_info(monkeypatch):
    """验证提示词包含 responses 信息"""
    captured_payload = {}

    def _capture_post(*args, **kwargs):
        captured_payload.update(kwargs.get("json", {}))
        return _FakeResp()

    monkeypatch.setattr("apiauto_agent.llm_generator.requests.post", _capture_post)

    ep = EndpointInfo(
        path="/pets",
        method="POST",
        summary="创建宠物",
        parameters=[
            ParameterInfo(name="name", location="body", required=True, param_type="string"),
        ],
        responses={"201": {"description": "创建成功"}, "400": {"description": "参数错误"}},
    )

    g = LLMCaseGenerator(api_url="http://mock-llm.local/v1/chat/completions")
    g.generate_cases(ep, case_type="all")

    user_content = captured_payload["messages"][1]["content"]
    assert "201" in user_content
    assert "400" in user_content
    assert "创建成功" in user_content


def test_prompt_filters_none_values(monkeypatch):
    """验证提示词不包含 None 值字段，减少 token 消耗"""
    captured_payload = {}

    def _capture_post(*args, **kwargs):
        captured_payload.update(kwargs.get("json", {}))
        return _FakeResp()

    monkeypatch.setattr("apiauto_agent.llm_generator.requests.post", _capture_post)

    ep = EndpointInfo(
        path="/pets",
        method="GET",
        summary="获取宠物",
        parameters=[
            ParameterInfo(name="id", location="query", required=False, param_type="integer"),
        ],
    )

    g = LLMCaseGenerator(api_url="http://mock-llm.local/v1/chat/completions")
    g.generate_cases(ep, case_type="all")

    user_content = captured_payload["messages"][1]["content"]
    # 不应包含 "null" 或 "None" 这样的无效值
    assert '"format": null' not in user_content
    assert '"enum": null' not in user_content
