"""Run synthetic tutor prompts against one configured provider and print JSON."""

import argparse
import asyncio
import json
from time import perf_counter

from app.ai.gemini import build_provider
from app.ai.provider import AcademicError, Turn
from app.ai.routing import OpenAIBackup
from app.core.config import get_settings

CASES = (
    (
        "lautech-source",
        "What is LAUTECH's current undergraduate application deadline? No sources are attached.",
        "Express uncertainty about the current deadline and direct the student to verify "
        "with official university admissions. Do not invent a date or claim live access.",
    ),
    (
        "cybersecurity",
        "Explain why salting password hashes does not replace a slow password-hashing algorithm.",
        "Explain that a unique salt defeats precomputed tables and identical hashes, while a "
        "slow algorithm raises the cost of each offline guess.",
    ),
    (
        "calculation",
        "A sensor draws 250 mA continuously for 3 hours. Calculate the charge used in Ah.",
        "Convert 250 mA to 0.25 A, multiply by 3 h, and state 0.75 Ah with units.",
    ),
    (
        "document",
        "Reference [S1]: Lab reports are due on Friday at 16:00. "
        "Reference [S2]: Late reports receive a 10% deduction. "
        "When is the report due and what happens if it is late? Cite the excerpts.",
        "Report Friday at 16:00 and a 10% deduction, citing [S1] and [S2] respectively.",
    ),
)


async def run(model_provider):
    config = get_settings()
    if model_provider == "gemini":
        provider = build_provider(config)
        if not provider.available:
            raise SystemExit("Set GEMINI_API_KEY first.")
        model = config.gemini_model
    else:
        key = config.openai_backup_api_key
        if not key or not key.get_secret_value().strip():
            raise SystemExit("Set OPENAI_BACKUP_API_KEY first.")
        model = config.openai_backup_model
        provider = OpenAIBackup(key.get_secret_value().strip(), model)

    results = []
    try:
        for case, prompt, rubric in CASES:
            start = perf_counter()
            answer, error = None, None
            try:
                async with asyncio.timeout(config.chat_timeout_seconds):
                    answer = await provider.generate([Turn("user", prompt)])
            except TimeoutError:
                error = "timeout"
            except AcademicError as exc:
                error = exc.code
            results.append(
                {
                    "case": case,
                    "prompt": prompt,
                    "rubric": rubric,
                    "answer": answer,
                    "error": error,
                    "latency_ms": round((perf_counter() - start) * 1000),
                }
            )
    finally:
        await provider.aclose()
    print(json.dumps({"provider": model_provider, "model": model, "results": results}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider", choices=("gemini", "openai"))
    asyncio.run(run(parser.parse_args().provider))
