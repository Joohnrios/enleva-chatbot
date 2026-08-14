"""Provedor OpenAI."""

from openai import OpenAI


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise ValueError("OPENAI_API_KEY não configurada no .env")
        self.model = model
        self._client = OpenAI(api_key=api_key)

    def complete(
        self,
        *,
        system: str,
        messages: list[dict],
        temperature: float = 0.2,
    ) -> str:
        payload = [{"role": "system", "content": system}]
        payload.extend({"role": m["role"], "content": m["content"]} for m in messages)
        response = self._client.chat.completions.create(
            model=self.model,
            temperature=temperature,
            messages=payload,
        )
        content = response.choices[0].message.content or ""
        return content.strip()
