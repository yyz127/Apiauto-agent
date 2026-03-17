"""测试LLM用例生成能力"""

from apiauto_agent.llm_generator import LLMCaseGenerator
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

    g = LLMCaseGenerator(api_url="http://mock-llm.local/v1/chat/completions")
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
