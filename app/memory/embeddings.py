from typing import Any

import httpx


class VoyageEmbedder:
    """Embeds plan data with Voyage before it is written to Qdrant Cloud."""

    def __init__(
        self,
        api_key: str,
        model: str = "voyage-3",
        endpoint: str = "https://api.voyageai.com/v1/embeddings",
    ):
        self.api_key = api_key
        self.model = model
        self.endpoint = endpoint

    def embed(self, text: str) -> list[float]:
        response = httpx.post(
            self.endpoint,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "input": [text],
                "model": self.model,
                "input_type": "document",
            },
            timeout=30,
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        embedding = data["data"][0]["embedding"]
        return [float(value) for value in embedding]
