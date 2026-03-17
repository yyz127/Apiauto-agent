"""OpenAPI/Swagger YAML文件解析器

解析OpenAPI 3.0或Swagger 2.0格式的YAML文件，提取接口信息。
"""

import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ParameterInfo:
    """接口参数信息"""
    name: str
    location: str  # query, header, path, cookie, body
    required: bool = False
    param_type: str = "string"
    format: str | None = None
    description: str = ""
    enum: list[str] | None = None
    default: Any = None
    minimum: float | None = None
    maximum: float | None = None
    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None
    example: Any = None


@dataclass
class EndpointInfo:
    """单个接口信息"""
    path: str
    method: str  # GET, POST, PUT, DELETE, PATCH
    summary: str = ""
    description: str = ""
    parameters: list[ParameterInfo] = field(default_factory=list)
    request_body_content_type: str = "application/json"
    request_body_schema: dict | None = None
    responses: dict[str, dict] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    security: list[dict[str, list[str]]] = field(default_factory=list)
    security_schemes: dict[str, dict] = field(default_factory=dict)


def parse_openapi_file(file_path: str | Path) -> list[EndpointInfo]:
    """解析OpenAPI/Swagger YAML文件，返回所有接口信息列表。"""
    file_path = Path(file_path)
    with open(file_path, "r", encoding="utf-8") as f:
        spec = yaml.safe_load(f)

    # 判断版本
    if spec.get("openapi", "").startswith("3."):
        return _parse_openapi3(spec)
    elif spec.get("swagger", "").startswith("2."):
        return _parse_swagger2(spec)
    else:
        raise ValueError("不支持的规范格式，请使用OpenAPI 3.x或Swagger 2.0")


def _resolve_ref(spec: dict, ref: str) -> dict:
    """解析$ref引用。"""
    parts = ref.lstrip("#/").split("/")
    obj = spec
    for part in parts:
        obj = obj[part]
    return obj


def _resolve_schema(spec: dict, schema: dict) -> dict:
    """递归解析schema中的$ref。"""
    if not isinstance(schema, dict):
        return schema
    if "$ref" in schema:
        resolved = _resolve_ref(spec, schema["$ref"])
        return _resolve_schema(spec, resolved)
    result = dict(schema)
    if "properties" in result:
        result["properties"] = {
            k: _resolve_schema(spec, v)
            for k, v in result["properties"].items()
        }
    if "items" in result:
        result["items"] = _resolve_schema(spec, result["items"])
    if "allOf" in result:
        merged = {}
        for sub in result["allOf"]:
            resolved = _resolve_schema(spec, sub)
            merged.update(resolved)
        result = merged
    return result


def _extract_param_constraints(schema: dict) -> dict:
    """从schema中提取参数约束。"""
    return {
        "minimum": schema.get("minimum"),
        "maximum": schema.get("maximum"),
        "min_length": schema.get("minLength"),
        "max_length": schema.get("maxLength"),
        "pattern": schema.get("pattern"),
        "enum": schema.get("enum"),
        "default": schema.get("default"),
        "example": schema.get("example"),
    }


def _schema_to_params(
    spec: dict,
    schema: dict,
    location: str = "body",
    required_fields: list[str] | None = None,
) -> list[ParameterInfo]:
    """将JSON Schema转换为参数列表。"""
    schema = _resolve_schema(spec, schema)
    params = []
    properties = schema.get("properties", {})
    required_fields = required_fields or schema.get("required", [])

    for name, prop in properties.items():
        prop = _resolve_schema(spec, prop)
        constraints = _extract_param_constraints(prop)
        params.append(ParameterInfo(
            name=name,
            location=location,
            required=name in required_fields,
            param_type=prop.get("type", "string"),
            format=prop.get("format"),
            description=prop.get("description", ""),
            **{k: v for k, v in constraints.items() if v is not None},
        ))
    return params


def _parse_openapi3(spec: dict) -> list[EndpointInfo]:
    """解析OpenAPI 3.0规范。"""
    endpoints = []
    paths = spec.get("paths", {})
    global_security = spec.get("security", [])
    security_schemes = spec.get("components", {}).get("securitySchemes", {})

    for path, path_item in paths.items():
        for method in ("get", "post", "put", "delete", "patch"):
            if method not in path_item:
                continue
            operation = path_item[method]
            # 接口级 security 优先，否则使用全局 security
            op_security = operation.get("security", global_security)
            endpoint = EndpointInfo(
                path=path,
                method=method.upper(),
                summary=operation.get("summary", ""),
                description=operation.get("description", ""),
                tags=operation.get("tags", []),
                responses=operation.get("responses", {}),
                security=op_security,
                security_schemes=security_schemes,
            )

            # 解析parameters (query, header, path, cookie)
            for param in operation.get("parameters", []) + path_item.get("parameters", []):
                if "$ref" in param:
                    param = _resolve_ref(spec, param["$ref"])
                schema = _resolve_schema(spec, param.get("schema", {}))
                constraints = _extract_param_constraints(schema)
                endpoint.parameters.append(ParameterInfo(
                    name=param["name"],
                    location=param["in"],
                    required=param.get("required", False),
                    param_type=schema.get("type", "string"),
                    format=schema.get("format"),
                    description=param.get("description", ""),
                    **{k: v for k, v in constraints.items() if v is not None},
                ))

            # 解析requestBody
            request_body = operation.get("requestBody", {})
            if "$ref" in request_body:
                request_body = _resolve_ref(spec, request_body["$ref"])
            content = request_body.get("content", {})
            for content_type, media in content.items():
                schema = media.get("schema", {})
                endpoint.request_body_content_type = content_type
                endpoint.request_body_schema = _resolve_schema(spec, schema)
                body_params = _schema_to_params(spec, schema)
                endpoint.parameters.extend(body_params)
                break  # 只取第一个content type

            endpoints.append(endpoint)
    return endpoints


def _parse_swagger2(spec: dict) -> list[EndpointInfo]:
    """解析Swagger 2.0规范。"""
    endpoints = []
    paths = spec.get("paths", {})
    global_security = spec.get("security", [])
    security_definitions = spec.get("securityDefinitions", {})

    for path, path_item in paths.items():
        for method in ("get", "post", "put", "delete", "patch"):
            if method not in path_item:
                continue
            operation = path_item[method]
            op_security = operation.get("security", global_security)
            endpoint = EndpointInfo(
                path=path,
                method=method.upper(),
                summary=operation.get("summary", ""),
                description=operation.get("description", ""),
                tags=operation.get("tags", []),
                responses=operation.get("responses", {}),
                security=op_security,
                security_schemes=security_definitions,
            )

            for param in operation.get("parameters", []) + path_item.get("parameters", []):
                if "$ref" in param:
                    param = _resolve_ref(spec, param["$ref"])

                if param.get("in") == "body":
                    schema = _resolve_schema(spec, param.get("schema", {}))
                    endpoint.request_body_schema = schema
                    body_params = _schema_to_params(spec, schema)
                    endpoint.parameters.extend(body_params)
                else:
                    constraints = _extract_param_constraints(param)
                    endpoint.parameters.append(ParameterInfo(
                        name=param["name"],
                        location=param["in"],
                        required=param.get("required", False),
                        param_type=param.get("type", "string"),
                        format=param.get("format"),
                        description=param.get("description", ""),
                        **{k: v for k, v in constraints.items() if v is not None},
                    ))

            endpoints.append(endpoint)
    return endpoints
