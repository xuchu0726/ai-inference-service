import json
import os
from pathlib import Path

import torch
from datasets import Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer
from llmcompressor.modifiers.quantization import QuantizationModifier
from llmcompressor.transformers import oneshot

MODEL_ID = "ByteDance-Seed/Seed-OSS-36B-Instruct"
OUTPUT_DIR = "/workspace/quantized_models/Seed-OSS-36B-Instruct-W8A8"
HF_CACHE_DIR = "/workspace/hf_cache"

NUM_CALIBRATION_SAMPLES = int(os.environ.get("NUM_CALIBRATION_SAMPLES", "16"))
MAX_SEQ_LENGTH = int(os.environ.get("MAX_SEQ_LENGTH", "512"))

CALIBRATION_PROMPTS = [
    "Explain GPU inference service in one sentence.",
    "Explain KV cache in LLM inference.",
    "Explain model quantization and its memory-latency trade-off.",
    "Explain grouped-query attention.",
    "Explain prefill and decode stages in transformer inference.",
    "Explain continuous batching in vLLM.",
    "Explain paged attention and KV cache memory management.",
    "Explain tensor parallel inference.",
    "解释什么是 GPU 推理服务。",
    "解释 KV cache 为什么能提升大模型推理效率。",
    "解释模型量化如何降低显存占用。",
    "解释 GQA 如何减少 KV cache memory。",
    "解释 batch size、吞吐量、延迟之间的关系。",
    "解释 P50、P95 latency 和 QPS 的含义。",
    "解释 W8A8 量化为什么不一定带来延迟下降。",
    "解释大模型 serving 中显存瓶颈的来源。",
]

def main():
    print("===== Offline W8A8 quantization config =====")
    print("model_id:", MODEL_ID)
    print("output_dir:", OUTPUT_DIR)
    print("hf_cache_dir:", HF_CACHE_DIR)
    print("num_calibration_samples:", NUM_CALIBRATION_SAMPLES)
    print("max_seq_length:", MAX_SEQ_LENGTH)
    print("torch:", torch.__version__)
    print("cuda_available:", torch.cuda.is_available())
    print("gpu_count:", torch.cuda.device_count())

    for i in range(torch.cuda.device_count()):
        print(f"gpu_{i}:", torch.cuda.get_device_name(i))

    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    prompts = CALIBRATION_PROMPTS[:NUM_CALIBRATION_SAMPLES]
    dataset = Dataset.from_dict({"text": prompts})

    with open(Path(OUTPUT_DIR) / "calibration_prompts.json", "w", encoding="utf-8") as f:
        json.dump(prompts, f, ensure_ascii=False, indent=2)

    print("===== Loading tokenizer =====")
    tokenizer = AutoTokenizer.from_pretrained(
        MODEL_ID,
        cache_dir=HF_CACHE_DIR,
        trust_remote_code=True,
    )

    print("===== Loading model in BF16 for offline quantization =====")
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        cache_dir=HF_CACHE_DIR,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
        low_cpu_mem_usage=True,
    )

    print("===== Starting W8A8 quantization =====")
    recipe = QuantizationModifier(
        targets="Linear",
        scheme="W8A8",
        ignore=["lm_head"],
    )

    oneshot(
        model=model,
        tokenizer=tokenizer,
        dataset=dataset,
        recipe=recipe,
        output_dir=OUTPUT_DIR,
        max_seq_length=MAX_SEQ_LENGTH,
        num_calibration_samples=len(prompts),
    )

    print("===== Quantization finished =====")
    print("output_dir:", OUTPUT_DIR)

    print("===== Output files =====")
    for path in sorted(Path(OUTPUT_DIR).glob("*")):
        print(path.name, path.stat().st_size)

    config_path = Path(OUTPUT_DIR) / "config.json"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        print("quantization_config:", cfg.get("quantization_config"))
        print("compression_config:", cfg.get("compression_config"))

if __name__ == "__main__":
    main()
