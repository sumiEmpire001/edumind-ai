import math

from google import genai
from google.genai import types


class Embeddings:
    def __init__(self, settings):
        if not settings.gemini_api_key:
            raise ValueError("embeddings_unconfigured")
        self.model = settings.embedding_model
        self.client = genai.Client(
            api_key=settings.gemini_api_key.get_secret_value(),
            http_options=types.HttpOptions(
                timeout=20000,
                retry_options=types.HttpRetryOptions(attempts=2, initial_delay=1, max_delay=3),
            ),
        )

    def embed(self, texts, task="RETRIEVAL_DOCUMENT"):
        values = []
        for start in range(0, len(texts), 16):
            result = self.client.models.embed_content(
                model=self.model,
                contents=texts[start : start + 16],
                config=types.EmbedContentConfig(output_dimensionality=768, task_type=task),
            )
            batch = [item.values for item in result.embeddings or []]
            if len(batch) != len(texts[start : start + 16]):
                raise ValueError("invalid_embeddings")
            for v in batch:
                if len(v) != 768 or not all(math.isfinite(x) for x in v):
                    raise ValueError("invalid_embeddings")
                norm = math.sqrt(sum(x * x for x in v))
                if not norm:
                    raise ValueError("invalid_embeddings")
                values.append([x / norm for x in v])
        return values

    def close(self):
        self.client.close()
