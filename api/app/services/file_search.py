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
            purpose="assistants",
        )
        self._client.vector_stores.files.create(
            vector_store_id=vector_store_id,
            file_id=getattr(file_obj, "id"),
        )
        return getattr(file_obj, "id")

    def search(self, vector_store_id: str, query: str, max_results: int = 3) -> List[dict[str, Any]]:
        # Responses API input: List of Message objects
        # Each message MUST have "type": "message" at top level (verified via SDK types)
        user_msg = {
            "type": "message",
            "role": "user",
            "content": [
                {"type": "input_text", "text": query}
            ]
        }

        response = self._client.responses.create(
            model="gpt-4.1-mini",
            input=[user_msg],
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

    def vector_store_exists(self, vector_store_id: str) -> bool:
        if not vector_store_id:
            return False
        try:
            self._client.vector_stores.retrieve(vector_store_id)
            return True
        except Exception:
            return False


__all__ = ["FileSearchService"]
