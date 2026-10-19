from typing import Any
import re
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

class SpecDetective:
    def __init__(self, openapi_spec: dict[str, Any]): self.spec = openapi_spec

    def validate_actual_response(self, path: str, method: str, status_code: int, payload: Any) -> list[dict]:
        paths = self.spec.get("paths", {})
        matched_path = path if path in paths else next((candidate for candidate in paths if re.fullmatch(re.sub(r"\\\{[^/{}]+\\\}", r"[^/]+", re.escape(candidate)), path)), None)
        if matched_path is None:
            return [{"type": "undocumented_endpoint", "message": f"Endpoint {path} is not present in the OpenAPI document.", "path": []}]
        operation = paths[matched_path].get(method.lower())
        if not operation:
            return [{"type": "undocumented_method", "message": f"Method {method.upper()} is not documented for {path}.", "path": []}]
        responses = operation.get("responses", {})
        response = responses.get(str(status_code)) or responses.get(f"{status_code // 100}XX") or responses.get("default")
        if not response:
            return [{"type": "undocumented_status", "message": f"Status {status_code} is not documented for {method.upper()} {path}.", "path": []}]
        content = response.get("content", {})
        media = content.get("application/json") or next((v for k, v in content.items() if k.endswith("+json")), None)
        schema = media.get("schema") if media else None
        if not schema:
            return []
        try:
            root = self.spec.get("components", {})
            Draft202012Validator.check_schema(schema)
            validator = Draft202012Validator(schema, registry=None, format_checker=FormatChecker())
            # Resolve local OpenAPI component references against the root document.
            from jsonschema import RefResolver
            resolver = RefResolver.from_schema(self.spec)
            validator = Draft202012Validator(schema, resolver=resolver, format_checker=FormatChecker())
            errors = sorted(validator.iter_errors(payload), key=lambda e: (list(map(str, e.absolute_path)), e.message))
            return [{"type": "schema_mismatch", "message": e.message, "path": list(e.absolute_path)} for e in errors[:20]]
        except (SchemaError, ValueError) as exc:
            return [{"type": "invalid_spec", "message": f"OpenAPI response schema is invalid: {exc.message if hasattr(exc, 'message') else str(exc)}", "path": []}]


