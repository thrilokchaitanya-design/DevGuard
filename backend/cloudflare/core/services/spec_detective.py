from typing import Any
import re
from jsonschema import Draft202012Validator, FormatChecker

class SpecDetective:
    """Validates captured responses against local, offline OpenAPI JSON documents."""
    def __init__(self, openapi_spec: dict[str, Any]): self.spec = openapi_spec

    @staticmethod
    def _external_refs(value: Any) -> list[str]:
        found: list[str] = []
        if isinstance(value, dict):
            ref = value.get("$ref")
            if isinstance(ref, str) and not ref.startswith("#/"):
                found.append(ref)
            for item in value.values():
                found.extend(SpecDetective._external_refs(item))
        elif isinstance(value, list):
            for item in value:
                found.extend(SpecDetective._external_refs(item))
        return found

    def validate_actual_response(self, path: str, method: str, status_code: int, payload: Any) -> list[dict]:
        version = self.spec.get("openapi", "")
        paths = self.spec.get("paths")
        if not isinstance(version, str) or not version.startswith("3.") or not isinstance(paths, dict):
            return [{"type": "invalid_spec", "message": "A valid OpenAPI 3.x document with a paths object is required.", "path": []}]
        external_refs = self._external_refs(self.spec)
        if external_refs:
            return [{"type": "unsupported_reference", "message": "Only local OpenAPI references are allowed; external references are blocked.", "path": []}]
        matched_path = path if path in paths else next((candidate for candidate in paths if isinstance(candidate, str) and re.fullmatch(re.sub(r"\\\{[^/{}]+\\\}", r"[^/]+", re.escape(candidate)), path)), None)
        if matched_path is None:
            return [{"type": "undocumented_endpoint", "message": f"Endpoint {path} is not present in the OpenAPI document.", "path": []}]
        path_item = paths.get(matched_path)
        if not isinstance(path_item, dict):
            return [{"type": "invalid_spec", "message": "The selected OpenAPI path item is invalid.", "path": []}]
        operation = path_item.get(method.lower())
        if not isinstance(operation, dict):
            return [{"type": "undocumented_method", "message": f"Method {method.upper()} is not documented for {path}.", "path": []}]
        responses = operation.get("responses")
        if not isinstance(responses, dict):
            return [{"type": "invalid_spec", "message": "The selected operation has no valid responses object.", "path": []}]
        response = responses.get(str(status_code)) or responses.get(f"{status_code // 100}XX") or responses.get("default")
        if response is None:
            return [{"type": "undocumented_status", "message": f"Status {status_code} is not documented for {method.upper()} {path}.", "path": []}]
        if not isinstance(response, dict):
            return [{"type": "invalid_spec", "message": "The selected response definition is invalid.", "path": []}]
        content = response.get("content", {})
        if not isinstance(content, dict):
            return [{"type": "invalid_spec", "message": "The response content definition is invalid.", "path": []}]
        media = content.get("application/json") or next((v for k, v in content.items() if isinstance(k, str) and k.endswith("+json")), None)
        schema = media.get("schema") if isinstance(media, dict) else None
        if schema is None:
            return []
        try:
            Draft202012Validator.check_schema(schema)
            from jsonschema import RefResolver
            resolver = RefResolver.from_schema(self.spec)
            validator = Draft202012Validator(schema, resolver=resolver, format_checker=FormatChecker())
            errors = sorted(validator.iter_errors(payload), key=lambda e: (list(map(str, e.absolute_path)), e.message))
            return [{"type": "schema_mismatch", "message": e.message, "path": list(e.absolute_path)} for e in errors[:20]]
        except Exception:
            return [{"type": "invalid_spec", "message": "The response schema is invalid or references an unknown local component.", "path": []}]
