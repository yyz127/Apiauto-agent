"""测试用例生成器

基于解析后的接口信息，自动生成正常用例和异常用例。
"""

import random
import string
from dataclasses import dataclass, field
from typing import Any

from .parser import EndpointInfo, ParameterInfo


@dataclass
class TestCase:
    """测试用例"""
    name: str
    description: str
    endpoint_path: str
    method: str
    case_type: str  # "normal" 或 "abnormal"
    parameters: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    expected_status: int | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "endpoint_path": self.endpoint_path,
            "method": self.method,
            "case_type": self.case_type,
            "parameters": self.parameters,
            "headers": self.headers,
            "expected_status": self.expected_status,
        }


def _generate_valid_value(param: ParameterInfo) -> Any:
    """为参数生成一个合法的值。"""
    # 优先使用example
    if param.example is not None:
        return param.example
    # 使用default
    if param.default is not None:
        return param.default
    # 从enum中选择
    if param.enum:
        return param.enum[0]

    t = param.param_type
    fmt = param.format or ""

    if t == "integer":
        lo = int(param.minimum) if param.minimum is not None else 1
        hi = int(param.maximum) if param.maximum is not None else 100
        return random.randint(lo, hi)
    elif t == "number":
        lo = param.minimum if param.minimum is not None else 0.0
        hi = param.maximum if param.maximum is not None else 100.0
        return round(random.uniform(lo, hi), 2)
    elif t == "boolean":
        return True
    elif t == "array":
        return []
    elif t == "object":
        return {}
    else:  # string
        if fmt == "email":
            return "test@example.com"
        elif fmt == "date":
            return "2026-01-15"
        elif fmt == "date-time":
            return "2026-01-15T10:30:00Z"
        elif fmt == "uri" or fmt == "url":
            return "https://example.com"
        elif fmt == "uuid":
            return "550e8400-e29b-41d4-a716-446655440000"
        elif fmt == "password":
            return "P@ssw0rd123"
        elif fmt == "phone":
            return "13800138000"
        else:
            length = param.min_length or 5
            if param.max_length and length > param.max_length:
                length = param.max_length
            return "test_" + "".join(random.choices(string.ascii_lowercase, k=length))


def _generate_invalid_values(param: ParameterInfo) -> list[tuple[str, Any, str]]:
    """为参数生成多种非法值。返回 [(描述, 值, 原因), ...]"""
    invalids = []
    t = param.param_type
    fmt = param.format or ""

    # 1. 空值/null
    invalids.append(("空值", None, "传入null值"))
    invalids.append(("空字符串", "", "传入空字符串"))

    # 2. 类型错误
    if t in ("integer", "number"):
        invalids.append(("类型错误-字符串", "abc", "传入非数字字符串"))
        invalids.append(("类型错误-布尔", True, "传入布尔值"))
    elif t == "string":
        invalids.append(("类型错误-数字", 12345, "传入数字类型"))
    elif t == "boolean":
        invalids.append(("类型错误-字符串", "not_bool", "传入非布尔字符串"))
    elif t == "array":
        invalids.append(("类型错误-字符串", "not_array", "传入非数组"))
    elif t == "object":
        invalids.append(("类型错误-字符串", "not_object", "传入非对象"))

    # 3. 边界值
    if t == "integer":
        if param.minimum is not None:
            invalids.append(("低于最小值", int(param.minimum) - 1, f"低于最小值{param.minimum}"))
        if param.maximum is not None:
            invalids.append(("超过最大值", int(param.maximum) + 1, f"超过最大值{param.maximum}"))
        invalids.append(("极大值", 2**31, "传入极大整数"))
        invalids.append(("负数", -1, "传入负数"))
    elif t == "number":
        if param.minimum is not None:
            invalids.append(("低于最小值", param.minimum - 0.01, f"低于最小值{param.minimum}"))
        if param.maximum is not None:
            invalids.append(("超过最大值", param.maximum + 0.01, f"超过最大值{param.maximum}"))

    # 4. 长度约束
    if t == "string":
        if param.max_length is not None:
            over = "x" * (param.max_length + 10)
            invalids.append(("超长字符串", over, f"超过最大长度{param.max_length}"))
        else:
            invalids.append(("超长字符串", "x" * 1000, "传入超长字符串"))

    # 5. 格式错误
    if t == "string":
        if fmt == "email":
            invalids.append(("格式错误-email", "not-an-email", "传入非邮箱格式"))
        elif fmt == "date":
            invalids.append(("格式错误-date", "2026-13-45", "传入非法日期"))
        elif fmt == "date-time":
            invalids.append(("格式错误-datetime", "not-a-datetime", "传入非法日期时间"))
        elif fmt == "uri" or fmt == "url":
            invalids.append(("格式错误-url", "not a url", "传入非法URL"))
        elif fmt == "uuid":
            invalids.append(("格式错误-uuid", "not-a-uuid", "传入非法UUID"))

    # 6. 枚举外的值
    if param.enum:
        invalids.append(("枚举外值", "INVALID_ENUM_VALUE", "传入不在枚举范围内的值"))

    # 7. 特殊字符/注入
    invalids.append(("特殊字符", "<script>alert(1)</script>", "XSS注入测试"))
    invalids.append(("SQL注入", "' OR 1=1 --", "SQL注入测试"))

    return invalids


def generate_normal_cases(endpoint: EndpointInfo) -> list[TestCase]:
    """为接口生成正常测试用例。"""
    cases = []
    prefix = f"{endpoint.method} {endpoint.path}"

    # 用例1: 所有必填参数都填写
    all_required_params = {}
    for p in endpoint.parameters:
        if p.required:
            all_required_params[p.name] = _generate_valid_value(p)

    cases.append(TestCase(
        name=f"[正常] {prefix} - 必填参数",
        description="只传入所有必填参数，验证接口正常返回",
        endpoint_path=endpoint.path,
        method=endpoint.method,
        case_type="normal",
        parameters=dict(all_required_params),
        expected_status=200,
    ))

    # 用例2: 所有参数（必填+可选）都填写
    all_params = {}
    for p in endpoint.parameters:
        all_params[p.name] = _generate_valid_value(p)
    if all_params != all_required_params:
        cases.append(TestCase(
            name=f"[正常] {prefix} - 全部参数",
            description="传入所有参数（必填+可选），验证接口正常返回",
            endpoint_path=endpoint.path,
            method=endpoint.method,
            case_type="normal",
            parameters=all_params,
            expected_status=200,
        ))

    # 用例3: 如果有enum参数，为每个enum值生成一个用例
    for p in endpoint.parameters:
        if p.enum and len(p.enum) > 1:
            for val in p.enum:
                params = dict(all_required_params)
                params[p.name] = val
                cases.append(TestCase(
                    name=f"[正常] {prefix} - {p.name}={val}",
                    description=f"参数{p.name}使用枚举值'{val}'",
                    endpoint_path=endpoint.path,
                    method=endpoint.method,
                    case_type="normal",
                    parameters=params,
                    expected_status=200,
                ))

    # 用例4: 边界值用例（最小值和最大值）
    for p in endpoint.parameters:
        if p.param_type in ("integer", "number"):
            if p.minimum is not None:
                params = dict(all_required_params)
                params[p.name] = int(p.minimum) if p.param_type == "integer" else p.minimum
                cases.append(TestCase(
                    name=f"[正常] {prefix} - {p.name}=最小值({p.minimum})",
                    description=f"参数{p.name}使用最小边界值",
                    endpoint_path=endpoint.path,
                    method=endpoint.method,
                    case_type="normal",
                    parameters=params,
                    expected_status=200,
                ))
            if p.maximum is not None:
                params = dict(all_required_params)
                params[p.name] = int(p.maximum) if p.param_type == "integer" else p.maximum
                cases.append(TestCase(
                    name=f"[正常] {prefix} - {p.name}=最大值({p.maximum})",
                    description=f"参数{p.name}使用最大边界值",
                    endpoint_path=endpoint.path,
                    method=endpoint.method,
                    case_type="normal",
                    parameters=params,
                    expected_status=200,
                ))

    return cases


def generate_abnormal_cases(endpoint: EndpointInfo) -> list[TestCase]:
    """为接口生成异常测试用例。"""
    cases = []
    prefix = f"{endpoint.method} {endpoint.path}"

    # 先构建一份合法基础参数
    base_params = {}
    for p in endpoint.parameters:
        if p.required:
            base_params[p.name] = _generate_valid_value(p)

    # 1. 缺少必填参数
    required_params = [p for p in endpoint.parameters if p.required]
    for p in required_params:
        params = dict(base_params)
        params.pop(p.name, None)
        cases.append(TestCase(
            name=f"[异常] {prefix} - 缺少必填参数{p.name}",
            description=f"不传必填参数'{p.name}'，期望返回400错误",
            endpoint_path=endpoint.path,
            method=endpoint.method,
            case_type="abnormal",
            parameters=params,
            expected_status=400,
        ))

    # 2. 对每个参数生成异常值用例
    for p in endpoint.parameters:
        invalid_values = _generate_invalid_values(p)
        for desc, value, reason in invalid_values:
            params = dict(base_params)
            params[p.name] = value
            cases.append(TestCase(
                name=f"[异常] {prefix} - {p.name}({desc})",
                description=f"参数'{p.name}'{reason}，期望返回4xx错误",
                endpoint_path=endpoint.path,
                method=endpoint.method,
                case_type="abnormal",
                parameters=params,
                expected_status=400,
            ))

    # 3. 无参数请求（如果有必填参数）
    if required_params:
        cases.append(TestCase(
            name=f"[异常] {prefix} - 无任何参数",
            description="不传任何参数，期望返回400错误",
            endpoint_path=endpoint.path,
            method=endpoint.method,
            case_type="abnormal",
            parameters={},
            expected_status=400,
        ))

    return cases


def generate_test_cases(endpoint: EndpointInfo) -> list[TestCase]:
    """为接口生成所有测试用例（正常+异常）。"""
    normal = generate_normal_cases(endpoint)
    abnormal = generate_abnormal_cases(endpoint)
    return normal + abnormal
