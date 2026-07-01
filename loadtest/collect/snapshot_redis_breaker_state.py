#!/usr/bin/env python3
"""采集 Redis shared circuit breaker 的原始状态。"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import redis


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--redis-url", required=True)
    parser.add_argument("--key-prefix", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    client = redis.Redis.from_url(
        args.redis_url,
        decode_responses=True,
        socket_timeout=3,
    )

    state_key = f"{{{args.key_prefix}}}:circuit"
    probe_key = f"{{{args.key_prefix}}}:probe"

    payload: dict[str, object] = {
        "collected_at_utc": datetime.now(UTC).isoformat(),
        "redis_url": args.redis_url,
        "key_prefix": args.key_prefix,
        "state_key": state_key,
        "probe_key": probe_key,
    }

    try:
        payload["state_hash"] = client.hgetall(state_key)
        payload["probe_value"] = client.get(probe_key)
        payload["probe_ttl_ms"] = client.pttl(probe_key)
    except redis.RedisError as exc:
        payload["redis_error"] = repr(exc)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"redis_breaker_snapshot={output}")


if __name__ == "__main__":
    main()
