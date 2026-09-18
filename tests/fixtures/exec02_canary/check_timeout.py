import importlib


client = importlib.import_module("client")
settings = importlib.import_module("settings")

http_settings = settings.load_http_settings({"request_timeout_ms": "5000"})
options = client.build_request_options(http_settings)

if options["timeout"] != 5:
    print(f"FAIL expected timeout=5 seconds, got {options['timeout']}")
    raise SystemExit(1)

print("PASS")
