import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


class TransformersBackend:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.tokenizer = None
        self.model = None
        self.loaded = False

    def _load_model(self):
        if self.loaded:
            return

        load_start = time.time()

        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)

        dtype = torch.float16 if self.device == "mps" else torch.float32

        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            dtype=dtype,
        )

        self.model.to(self.device)
        self.model.eval()

        self.load_latency_seconds = time.time() - load_start
        self.loaded = True

    def generate(
        self,
        prompt: str,
        max_new_tokens: int = 128,
        temperature: float = 0.7,
        thinking_budget: int | None = None,
    ) -> dict:
        self._load_model()

        messages = [
            {
                "role": "system",
                "content": "你是一个简洁、专业的 AI 推理工程助手。",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]

        text = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )

        inputs = self.tokenizer(text, return_tensors="pt").to(self.device)
        input_tokens = inputs["input_ids"].shape[-1]

        generate_start = time.time()

        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                use_cache=True,
            )

        generate_latency = time.time() - generate_start

        output_tokens = outputs.shape[-1] - input_tokens
        generated_ids = outputs[0][input_tokens:]

        response = self.tokenizer.decode(
            generated_ids,
            skip_special_tokens=True,
        )

        tokens_per_second = (
            output_tokens / generate_latency if generate_latency > 0 else 0
        )

        return {
            "response": response,
            "latency_seconds": generate_latency,
            "input_chars": len(prompt),
            "input_tokens": int(input_tokens),
            "output_tokens": int(output_tokens),
            "tokens_per_second": round(tokens_per_second, 4),
            "max_new_tokens": max_new_tokens,
            "thinking_budget": thinking_budget,
            "backend": "transformers",
            "model_name": self.model_name,
            "device": self.device,
        }
