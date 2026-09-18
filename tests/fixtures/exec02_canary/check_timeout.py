from client import build_request_options
from settings import load_http_settings


settings = load_http_settings({"request_timeout_ms": "5000"})
options = build_request_options(settings)

if options["timeout"] != 5:
    print(f"FAIL expected timeout=5 seconds, got {options['timeout']}")
    raise SystemExit(1)

print("PASS")
