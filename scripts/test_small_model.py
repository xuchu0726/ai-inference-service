import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_NAME = "Qwen/Qwen2.5-0.5B-Instruct"


def get_device() -> str:
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def main():
    device = get_device()

    print(f"Using device: {device}")
    print(f"Loading model: {MODEL_NAME}")

    load_start = time.time()

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        torch_dtype=torch.float16 if device == "mps" else torch.float32,
    )

    model.to(device)
    model.eval()

    load_latency = time.time() - load_start
    print(f"Model loaded in {load_latency:.2f}s")

    prompt = "请用三句话解释什么是大模型推理。"

    messages = [
        {"role": "system", "content": "你是一个简洁、专业的 AI 推理工程助手。"},
        {"role": "user", "content": prompt},
    ]

    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )

    inputs = tokenizer(text, return_tensors="pt").to(device)

    input_tokens = inputs["input_ids"].shape[-1]

    generate_start = time.time()

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=128,
            do_sample=False,
            use_cache=True,
        )

    generate_latency = time.time() - generate_start

    output_tokens = outputs.shape[-1] - input_tokens

    generated_ids = outputs[0][input_tokens:]
    response = tokenizer.decode(generated_ids, skip_special_tokens=True)

    tokens_per_second = output_tokens / generate_latency if generate_latency > 0 else 0

    print("\nResponse:")
    print(response)

    print("\nMetrics:")
    print(f"Input tokens: {input_tokens}")
    print(f"Output tokens: {output_tokens}")
    print(f"Generate latency: {generate_latency:.2f}s")
    print(f"Tokens/s: {tokens_per_second:.2f}")


if __name__ == "__main__":
    main()