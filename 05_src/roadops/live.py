"""Safe, read-only retrieval for RoadOps operational JSON sources.

RoadOps 운영 JSON 소스를 키 노출 없이 읽기 전용으로 수집합니다.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import httpx

from roadops.probe import (
    SourceSpec,
    _normalize_api_key,
    _provider_error,
    runtime_params_for,
)


class LiveFetchError(RuntimeError):
    """A sanitized source-retrieval failure that never includes the API key."""

    def __init__(
        self,
        reason: str,
        *,
        http_status: int | None = None,
        provider_result_code: str | None = None,
        provider_result_message: str | None = None,
    ):
        super().__init__(reason)
        self.reason = reason
        self.http_status = http_status
        self.provider_result_code = provider_result_code
        self.provider_result_message = provider_result_message

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "status": "fetch_failed",
            "reason": self.reason,
            "http_status": self.http_status,
        }
        if self.provider_result_code is not None:
            result["provider_result_code"] = self.provider_result_code
        if self.provider_result_message is not None:
            result["provider_result_message"] = self.provider_result_message
        return result


def fetch_json_payload(
    spec: SourceSpec,
    *,
    api_key: str,
    allow_insecure_http: bool = False,
    timeout_seconds: float = 30,
    now: datetime | None = None,
    client: httpx.Client | None = None,
) -> tuple[Mapping[str, Any], dict[str, Any]]:
    """Fetch one JSON payload while keeping credentials out of logs and outputs."""

    if spec.endpoint_url is None:
        raise LiveFetchError("endpoint_not_configured")
    if spec.authentication is None:
        raise LiveFetchError("authentication_not_configured")
    if not api_key:
        raise LiveFetchError("credential_missing")
    if spec.endpoint_url.startswith("http://") and not allow_insecure_http:
        raise LiveFetchError("insecure_transport_blocked")

    normalized_api_key = _normalize_api_key(api_key)
    params = dict(spec.default_params)
    params.update(runtime_params_for(spec.runtime_params, now))
    authentication_parameter = spec.authentication["query_parameter"]
    params[authentication_parameter] = normalized_api_key
    owns_client = client is None
    http_client = client or httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(timeout_seconds),
        headers={"User-Agent": "Jeju-RoadOps-Live-Validation/0.1"},
    )
    try:
        try:
            response = http_client.get(spec.endpoint_url, params=params)
        except httpx.HTTPError as exc:
            raise LiveFetchError(type(exc).__name__) from None
        if not response.is_success:
            raise LiveFetchError("http_error", http_status=response.status_code)
        try:
            payload = response.json()
        except json.JSONDecodeError:
            raise LiveFetchError("invalid_json", http_status=response.status_code) from None
        if not isinstance(payload, Mapping):
            raise LiveFetchError("json_root_not_object", http_status=response.status_code)
        provider_error = _provider_error(payload)
        if provider_error is not None:
            provider_message = provider_error["provider_result_message"].replace(
                normalized_api_key, "[REDACTED]"
            )
            raise LiveFetchError(
                "provider_error",
                http_status=response.status_code,
                provider_result_code=provider_error["provider_result_code"],
                provider_result_message=provider_message,
            )
        metadata = {
            "status": "response_received",
            "source_id": spec.source_id,
            "endpoint_url": spec.endpoint_url,
            "transport": "http" if spec.endpoint_url.startswith("http://") else "https",
            "http_status": response.status_code,
            "content_type": response.headers.get("content-type"),
            "response_bytes": len(response.content),
            "fetched_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
            "request_params": {
                key: value for key, value in params.items() if key != authentication_parameter
            },
        }
        return payload, metadata
    finally:
        if owns_client:
            http_client.close()
