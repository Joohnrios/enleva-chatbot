"""Provedor Google Gemini."""

import google.generativeai as genai


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise ValueError("GEMINI_API_KEY não configurada no .env")
        self.model_name = model
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(model)

    def complete(
        self,
        *,
        system: str,
        messages: list[dict],
        temperature: float = 0.2,
    ) -> str:
        history_lines: list[str] = []
        for msg in messages:
            role = "Usuário" if msg["role"] == "user" else "Assistente"
            history_lines.append(f"{role}: {msg['content']}")
        prompt = (
            f"{system}\n\n"
            f"---\nConversa:\n" + "\n".join(history_lines) + "\n\nAssistente:"
        )
        response = self._model.generate_content(
            prompt,
            generation_config={"temperature": temperature},
        )
        return (response.text or "").strip()
