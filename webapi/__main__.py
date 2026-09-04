from __future__ import annotations

import argparse

import uvicorn

from webapi.app import app


def main() -> None:
    try:
        from utils.config import server_config

        defaults = server_config()
    except Exception:
        defaults = {"host": "127.0.0.1", "port": 8088}
    parser = argparse.ArgumentParser(description="Zadig Agent 系统设置页")
    parser.add_argument("--host", default=defaults["host"])
    parser.add_argument("--port", type=int, default=defaults["port"])
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
