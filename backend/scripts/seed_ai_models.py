"""Seed AI models with correct Huawei Cloud endpoint.

All 4 working models use the same endpoint + key.
Idempotent (INSERT OR REPLACE).
"""
import asyncio, json, os, aiosqlite

DB = os.environ.get("HOMEDOCTOR_DATABASE_URL", "data/homedoctor.db")

# SECURITY: never hardcode keys in the repo — read from the environment
# (same variable the app uses). Model presets are skipped until one is set;
# a blank credential must never be stored in the database.
API_KEY = os.environ.get("HOMEDOCTOR_LLM_API_KEY", "")
ENDPOINT = "https://api.modelarts-maas.com/openai/v1/chat/completions"

MODELS = [
    {"id": "model-glm-5", "name": "智谱GLM-5.2", "provider": "智谱",
     "model_id": "GLM-5", "capabilities": ["text"],
     "max_tokens": 4096, "is_default": 1},
    {"id": "model-kimi-k2", "name": "Kimi-K2.6", "provider": "huawei_cloud",
     "model_id": "Kimi-K2.6", "capabilities": ["text", "vision"],
     "max_tokens": 8192, "is_default": 0},
    {"id": "model-qwen3-235b", "name": "Qwen3-235B", "provider": "huawei_cloud",
     "model_id": "qwen3-235b-a22b", "capabilities": ["text"],
     "max_tokens": 4096, "is_default": 0},
    {"id": "model-deepseek-v3", "name": "DeepSeek-V3", "provider": "huawei_cloud",
     "model_id": "DeepSeek-V3", "capabilities": ["text"],
     "max_tokens": 4096, "is_default": 0},
]


async def main():
    if not API_KEY:
        print("HOMEDOCTOR_LLM_API_KEY is unset; skipping optional AI model presets")
        return
    async with aiosqlite.connect(DB) as db:
        for m in MODELS:
            await db.execute(
                """INSERT OR REPLACE INTO ai_models
                   (id, name, provider, model_id, api_endpoint, api_key,
                    access_type, capabilities, max_tokens, temperature, enabled, is_default)
                   VALUES (?, ?, ?, ?, ?, ?, 'api', ?, ?, 0.3, 1, ?)""",
                (m["id"], m["name"], m["provider"], m["model_id"],
                 ENDPOINT, API_KEY,
                 json.dumps(m["capabilities"], ensure_ascii=False),
                 m["max_tokens"], m["is_default"]),
            )
        await db.commit()
        print(f"Seeded {len(MODELS)} models (Huawei Cloud, correct endpoint)")


if __name__ == "__main__":
    asyncio.run(main())
