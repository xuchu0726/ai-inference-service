# AI Inference Service

A minimal FastAPI-based LLM inference service prototype.

## Current Features

- FastAPI service
- `/health` endpoint
- `/generate` endpoint
- Mock inference backend
- `thinking_budget` parameter
- Basic benchmark client

## Project Structure

```text
ai-inference-service/
├── app/
│   ├── main.py
│   ├── inference.py
│   ├── schemas.py
│   └── config.py
├── scripts/
│   └── benchmark.py
├── docs/
├── requirements.txt
└── README.md