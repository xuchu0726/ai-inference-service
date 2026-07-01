#!/usr/bin/env python3
"""采集 Redis Stream、consumer group 与 PEL 状态。"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import redis


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--redis-url", required=True)
    parser.add_argument("--queue-prefix", required=True)
    parser.add_argument("--consumer-group", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    client = redis.Redis.from_url(
        args.redis_url,
        decode_responses=True,
        socket_timeout=3,
    )

    stream_key = f"{{{args.queue_prefix}}}:stream"
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload: dict[str, object] = {
        "collected_at_utc": datetime.now(UTC).isoformat(),
        "redis_url": args.redis_url,
        "stream_key": stream_key,
        "consumer_group": args.consumer_group,
    }

    try:
        payload["stream_length"] = client.xlen(stream_key)
    except redis.RedisError as exc:
        payload["stream_length_error"] = repr(exc)

    try:
        payload["pending"] = client.xpending_range(
            stream_key,
            args.consumer_group,
            min="-",
            max="+",
            count=100,
        )
    except redis.RedisError as exc:
        payload["pending_error"] = repr(exc)

    try:
        payload["groups"] = client.xinfo_groups(stream_key)
    except redis.RedisError as exc:
        payload["groups_error"] = repr(exc)

    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"redis_state_snapshot={output_path}")


if __name__ == "__main__":
    main()
