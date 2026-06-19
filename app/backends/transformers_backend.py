import time

import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)


class TransformersBackend:
    """基于 Hugging Face Transformers 的本地推理后端。"""

    def __init__(
        self,
        model_name: str,
        load_in_8bit: bool = False,
        device_map: str | None = None,
        default_thinking_budget: int | None = None,
    ):
        self.model_name = model_name
        self.load_in_8bit = load_in_8bit
        self.device_map = device_map
        self.default_thinking_budget = default_thinking_budget

        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.input_device = None
        self.tokenizer = None
        self.model = None
        self.loaded = False
        self.load_latency_seconds = None

    def _load_model(self) -> None:
        """按当前配置加载普通模型或 BitsAndBytes LLM.int8() 模型。"""
        if self.loaded:
            return

        load_start = time.time()
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)

        if self.load_in_8bit:
            quantization_config = BitsAndBytesConfig(
                load_in_8bit=True,
                llm_int8_threshold=6.0,
            )

            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_name,
                quantization_config=quantization_config,
                device_map=self.device_map or "auto",
                dtype=torch.bfloat16,
                attn_implementation="eager",
                low_cpu_mem_usage=True,
            )

            # device_map="auto" 已完成模型分配，禁止再调用 model.to(...)
            self.input_device = next(self.model.parameters()).device
            self.device = str(self.input_device)
        else:
            dtype = torch.float16 if self.device == "mps" else torch.float32

            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_name,
                dtype=dtype,
            )
            self.model.to(self.device)
            self.input_device = self.device

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
        """生成单次模型回复。"""
        self._load_model()

        # 与 vLLM 基线保持一致：评测时只传入 user prompt。
        messages = [
            {
                "role": "user",
                "content": prompt,
            },
        ]

        effective_thinking_budget = (
            thinking_budget
            if thinking_budget is not None
            else self.default_thinking_budget
        )

        template_kwargs = {
            "tokenize": True,
            "add_generation_prompt": True,
            "return_dict": True,
            "return_tensors": "pt",
        }

        if effective_thinking_budget is not None:
            template_kwargs["thinking_budget"] = effective_thinking_budget

        inputs = self.tokenizer.apply_chat_template(
            messages,
            **template_kwargs,
        )

        inputs = inputs.to(self.input_device)

        # Seed-OSS 当前模型不接收 tokenizer 返回的 token_type_ids。
        inputs.pop("token_type_ids", None)

        input_tokens = int(inputs["input_ids"].shape[-1])
        generate_start = time.time()

        with torch.inference_mode():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                use_cache=True,
            )

        generate_latency = time.time() - generate_start
        output_tokens = int(outputs.shape[-1] - input_tokens)
        generated_ids = outputs[0][input_tokens:]

        response = self.tokenizer.decode(
            generated_ids,
            skip_special_tokens=True,
        )

        tokens_per_second = (
            output_tokens / generate_latency
            if generate_latency > 0
            else 0
        )

        return {
            "response": response,
            "latency_seconds": generate_latency,
            "input_chars": len(prompt),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "tokens_per_second": round(tokens_per_second, 4),
            "max_new_tokens": max_new_tokens,
            "thinking_budget": effective_thinking_budget,
            "backend": "transformers",
            "model_name": self.model_name,
            "device": self.device,
        }
