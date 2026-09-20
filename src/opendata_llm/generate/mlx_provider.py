"""MLX generation provider (Apple Silicon) using mlx-lm."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any

from .base import Message


class MLXGenerator:
    def __init__(
        self,
        model_id: str,
        max_tokens: int = 384,
        temperature: float = 0.2,
    ) -> None:
        self.model_id = model_id
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._model: Any = None
        self._tokenizer: Any = None

    def warmup(self) -> None:
        """Load the model (e.g. at server startup) so the first request is fast."""
        self._ensure_loaded()

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        from mlx_lm import load

        loaded = load(self.model_id)
        self._model = loaded[0]
        self._tokenizer = loaded[1]

    def _options(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        from mlx_lm.sample_utils import make_sampler

        max_tokens = kwargs.get("max_tokens") or self.max_tokens
        temperature = kwargs.get("temperature")
        if temperature is None:
            temperature = self.temperature
        options: dict[str, Any] = {"max_tokens": max_tokens}
        if temperature and temperature > 0:
            options["sampler"] = make_sampler(temp=float(temperature), top_p=0.95)
        return options

    def _format(self, messages: Sequence[Message]) -> str:
        return str(
            self._tokenizer.apply_chat_template(
                list(messages), add_generation_prompt=True, tokenize=False
            )
        )

    def generate(self, messages: Sequence[Message], **kwargs: Any) -> str:
        self._ensure_loaded()
        from mlx_lm import generate as mlx_generate

        prompt = self._format(messages)
        return str(
            mlx_generate(
                self._model,
                self._tokenizer,
                prompt=prompt,
                verbose=False,
                **self._options(kwargs),
            )
        )

    def stream(self, messages: Sequence[Message], **kwargs: Any) -> Iterator[str]:
        self._ensure_loaded()
        from mlx_lm import stream_generate

        prompt = self._format(messages)
        for response in stream_generate(
            self._model, self._tokenizer, prompt=prompt, **self._options(kwargs)
        ):
            text = getattr(response, "text", "")
            if text:
                yield str(text)
