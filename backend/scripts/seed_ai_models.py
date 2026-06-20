"""Seed current AI models into ai_models registry.

Pre-configures the models already in use (Kimi/Qwen/GLM/DeepSeek).
Idempotent (INSERT OR REPLACE). Standalone (aiosqlite direct).
"""
import asyncio, json, os, aiosqlite

DB = os.environ.get("HOMEDOCTOR_DATABASE_URL", "data/homedoctor.db")

MODELS = [
    {
        "id": "model-kimi-k2",
        "name": "Kimi-K2.6",
        "provider": "moonshot",
        "model_id": "Kimi-K2.6",
        "api_endpoint": "https://api.openai.com/v1/chat/completions",
        "api_key": os.environ.get("HOMEDOCTOR_LLM_API_KEY", ""),
        "access_type": "api",
        "capabilities": ["text"],
        "max_tokens": 8192,
        "temperature": 0.3,
        "enabled": 1,
        "is_default": 1,
    },
    {
        "id": "model-glm-5",
        "name": "GLM-5",
        "provider": "zhipu",
        "model_id": "GLM-5",
        "api_endpoint": "https://api.openai.com/v1/chat/completions",
        "api_key": os.environ.get("HOMEDOCTOR_LLM_API_KEY", ""),
        "access_type": "api",
        "capabilities": ["text"],
        "max_tokens": 4096,
        "temperature": 0.3,
        "enabled": 1,
        "is_default": 0,
    },
    {
        "id": "model-qwen3-235b",
        "name": "Qwen3-235B",
        "provider": "alibaba",
        "model_id": "qwen3-235b-a22b",
        "api_endpoint": "https://api.openai.com/v1/chat/completions",
        "api_key": os.environ.get("HOMEDOCTOR_LLM_API_KEY", ""),
        "access_type": "api",
        "capabilities": ["text"],
        "max_tokens": 4096,
        "temperature": 0.3,
        "enabled": 1,
        "is_default": 0,
    },
    {
        "id": "model-deepseek-v3",
        "name": "DeepSeek-V3",
        "provider": "deepseek",
        "model_id": "DeepSeek-V3",
        "api_endpoint": "https://api.openai.com/v1/chat/completions",
        "api_key": os.environ.get("HOMEDOCTOR_LLM_API_KEY", ""),
        "access_type": "api",
        "capabilities": ["text"],
        "max_tokens": 4096,
        "temperature": 0.3,
        "enabled": 1,
        "is_default": 0,
    },
    {
        "id": "model-qwen-vl",
        "name": "Qwen2.5-VL-72B",
        "provider": "alibaba",
        "model_id": "qwen2.5-vl-72b",
        "api_endpoint": "https://api.modelarts-maas.com/v1/chat/completions",
        "api_key": os.environ.get("HOMEDOCTOR_LLM_API_KEY", ""),
        "access_type": "api",
        "capabilities": ["text", "vision"],
        "max_tokens": 4096,
        "temperature": 0.2,
        "enabled": 1,
        "is_default": 0,
    },
]


async def main():
    async with aiosqlite.connect(DB) as db:
        count = 0
        for m in MODELS:
            await db.execute(
                """INSERT OR REPLACE INTO ai_models
                   (id, name, provider, model_id, api_endpoint, api_key,
                    access_type, capabilities, max_tokens, temperature,
                    enabled, is_default)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    m["id"], m["name"], m["provider"], m["model_id"],
                    m["api_endpoint"], m["api_key"],
                    m["access_type"],
                    json.dumps(m["capabilities"], ensure_ascii=False),
                    m["max_tokens"], m["temperature"],
                    m["enabled"], m["is_default"],
                ),
            )
            count += 1
        await db.commit()
        print(f"Seeded {count} AI models into registry")


if __name__ == "__main__":
    asyncio.run(main())
