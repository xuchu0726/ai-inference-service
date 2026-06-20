import json
import time
import traceback
from pathlib import Path

import bitsandbytes as bnb
import torch
import transformers
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

MODEL_PATH = "/workspace/models/Seed-OSS-36B-Instruct"
RESULT_PATH = Path(
    "/workspace/ai-inference-service/results/week2_hardening/bnb_int8/"
    "seed_oss_bnb_int8_smoke_20260619.json"
)


def get_memory_snapshot() -> dict:
    """记录每张 GPU 的 PyTorch 显存状态。"""
    return {
        f"cuda:{gpu_index}": {
            "已分配显存_GiB": round(
                torch.cuda.memory_allocated(gpu_index) / 1024**3, 3
            ),
            "已保留显存_GiB": round(
                torch.cuda.memory_reserved(gpu_index) / 1024**3, 3
            ),
            "峰值已分配显存_GiB": round(
                torch.cuda.max_memory_allocated(gpu_index) / 1024**3, 3
            ),
        }
        for gpu_index in range(torch.cuda.device_count())
    }


def save_result(result: dict) -> None:
    RESULT_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    print("开始执行 BitsAndBytes LLM.int8() 双卡加载验证。")

    torch.cuda.empty_cache()
    for gpu_index in range(torch.cuda.device_count()):
        torch.cuda.reset_peak_memory_stats(gpu_index)

    quantization_config = BitsAndBytesConfig(
        load_in_8bit=True,
        llm_int8_threshold=6.0,
    )

    try:
        print("正在加载 tokenizer。")
        tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)

        print("正在以 BitsAndBytes LLM.int8() 方式加载模型。")
        load_start_time = time.perf_counter()

        model = AutoModelForCausalLM.from_pretrained(
            MODEL_PATH,
            quantization_config=quantization_config,
            device_map="auto",
            dtype=torch.bfloat16,
            attn_implementation="eager",
            low_cpu_mem_usage=True,
        )

        load_seconds = time.perf_counter() - load_start_time
        model.eval()

        int8_linear_module_count = sum(
            isinstance(module, bnb.nn.Linear8bitLt)
            for module in model.modules()
        )

        messages = [
            {
                "role": "user",
                "content": "What is the capital of France?",
            }
        ]

        inputs = tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
            thinking_budget=0,
        )

        first_parameter_device = next(model.parameters()).device
        inputs = inputs.to(first_parameter_device)

        # Seed-OSS 当前模型不使用 tokenizer 返回的 token_type_ids。
        inputs.pop("token_type_ids", None)

        print("正在执行单请求生成。")
        generate_start_time = time.perf_counter()

        with torch.inference_mode():
            outputs = model.generate(
                **inputs,
                max_new_tokens=48,
                do_sample=False,
            )

        generate_seconds = time.perf_counter() - generate_start_time
        input_token_count = int(inputs["input_ids"].shape[-1])
        generated_token_ids = outputs[0][input_token_count:]
        response = tokenizer.decode(
            generated_token_ids,
            skip_special_tokens=True,
        )

        result = {
            "状态": "通过",
            "量化路线": "BitsAndBytes LLM.int8() 运行时量化",
            "模型路径": MODEL_PATH,
            "模型原始精度": "BF16 checkpoint",
            "量化配置": {
                "load_in_8bit": True,
                "llm_int8_threshold": 6.0,
            },
            "运行环境": {
                "torch版本": torch.__version__,
                "CUDA版本": torch.version.cuda,
                "transformers版本": transformers.__version__,
                "bitsandbytes版本": bnb.__version__,
                "GPU数量": torch.cuda.device_count(),
            },
            "验证结果": {
                "INT8线性层数量": int8_linear_module_count,
                "设备映射": getattr(model, "hf_device_map", None),
                "模型加载秒数": round(load_seconds, 3),
                "单请求生成秒数": round(generate_seconds, 3),
                "输入Token数": input_token_count,
                "输出Token数": int(generated_token_ids.shape[-1]),
                "模型回复": response,
                "生成后显存快照": get_memory_snapshot(),
            },
            "结论": (
                "原始 BF16 Seed-OSS checkpoint 已通过 "
                "BitsAndBytes LLM.int8() 运行时量化完成双卡加载与单请求生成。"
            ),
        }

        save_result(result)

        print("验证通过：BitsAndBytes LLM.int8() 已完成模型加载和单请求生成。")
        print(f"INT8 线性层数量：{int8_linear_module_count}")
        print(f"模型加载耗时：{load_seconds:.3f} 秒")
        print(f"单请求生成耗时：{generate_seconds:.3f} 秒")
        print(f"模型回复：{response}")
        print(f"结果文件：{RESULT_PATH}")

    except Exception as error:
        failure_result = {
            "状态": "失败",
            "量化路线": "BitsAndBytes LLM.int8() 运行时量化",
            "模型路径": MODEL_PATH,
            "失败阶段": "模型加载或单请求生成",
            "异常类型": type(error).__name__,
            "异常信息": str(error),
            "完整Traceback": traceback.format_exc(),
            "失败时显存快照": get_memory_snapshot(),
        }
        save_result(failure_result)
        raise


if __name__ == "__main__":
    main()
