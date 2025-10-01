from __future__ import annotations

import io
from typing import Any, List

from openai import OpenAI


class FileSearchService:
    """Wrapper around OpenAI File Search vector stores."""

    def __init__(self, client: OpenAI) -> None:
        self._client = client

    def create_vector_store(self, name: str) -> str:
        store = self._client.vector_stores.create(name=name)
        return getattr(store, "id")

    def add_pdf(self, vector_store_id: str, filename: str, data: bytes) -> str:
        file_obj = self._client.files.create(
            file=(filename, io.BytesIO(data), "application/pdf"),
            purpose="file_search",
        )
        self._client.vector_stores.files.create(
            vector_store_id=vector_store_id,
            file_id=getattr(file_obj, "id"),
        )
        return getattr(file_obj, "id")

    def search(self, vector_store_id: str, query: str, max_results: int = 3) -> List[dict[str, Any]]:
        response = self._client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": query},
                    ],
                }
            ],
            attachments=[
                {
                    "file_search": {
                        "vector_store_ids": [vector_store_id],
                        "max_num_results": max_results,
                    }
                }
            ],
        )
        return getattr(response, "output", [])


__all__ = ["FileSearchService"]
