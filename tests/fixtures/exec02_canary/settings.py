from dataclasses import dataclass


@dataclass(frozen=True)
class HttpSettings:
    request_timeout_seconds: int


def load_http_settings(raw: dict[str, str]) -> HttpSettings:
    return HttpSettings(
        request_timeout_seconds=int(raw["request_timeout_ms"]),
    )
