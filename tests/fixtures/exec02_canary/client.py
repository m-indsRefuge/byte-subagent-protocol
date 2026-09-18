from settings import HttpSettings


def build_request_options(settings: HttpSettings) -> dict[str, int]:
    return {"timeout": settings.request_timeout_seconds}
