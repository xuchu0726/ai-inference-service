# Week2 量化评测协议审计与定向复测结果

## 1. 文档目的

本文档统一记录 Seed-OSS-36B-Instruct 的 BF16、W8A8 compressed-tensors 与 BitsAndBytes INT8 在 GSM8K 上的原始评测协议、输出上限触顶情况、可比性边界和后续定向复测规则。

本文档不将不同量化路径的原始 accuracy 直接解释为最终量化质量排名。当前重点是区分 output truncation（输出截断）与 quantization quality regression（量化质量回归）的影响。

## 2. 路线与运行边界

| 路线 | 模型与运行方式 | Serving / runtime 边界 | 是否属于同一 serving stack |
|---|---|---|---|
| BF16 | Seed-OSS-36B-Instruct BF16 | vLLM, TP=2 | 是，作为 vLLM baseline |
| W8A8 | Seed-OSS-36B-Instruct-W8A8 | vLLM compressed-tensors backend, TP=2 | 是，与 BF16 构成同源 serving 对照 |
| BnB INT8 | Seed-OSS-36B-Instruct BF16 checkpoint | Transformers + BitsAndBytes LLM.int8() runtime quantization | 否，属于独立 runtime quantization 路线 |

说明：

- BF16 与 W8A8 可以作为固定 serving envelope 下的同源部署对照。
- BnB INT8 使用 Transformers + BitsAndBytes，不是 vLLM TP=2 serving benchmark，因此不纳入 BF16/W8A8 的纯 serving 性能排名。
- 三条路线在原始 GSM8K 评测中均使用 `max_new_tokens=256`，该输出上限需要单独审计。

## 3. 原始 GSM8K 结果：max_new_tokens=256

| 路线 | 总样本 | 正确数 | 原始 accuracy | cap-hit 样本 | cap-hit rate | cap-hit 错题 | 全部错误数 | 错误位于 cap-hit 的比例 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BF16 / vLLM | 1319 | 999 | 75.7392% | 366 | 27.75% | 294 | 320 | 91.88% |
| W8A8 / vLLM compressed-tensors | 1319 | 986 | 74.7536% | 395 | 29.95% | 310 | 333 | 93.09% |
| BnB INT8 / Transformers | 1319 | 1009 | 76.4973% | 348 | 26.38% | 279 | 310 | 90.00% |

触顶判定：

`output_tokens == max_new_tokens`

当前原始结果表明，三条路线均存在较高比例的 output cap-hit，且 90.00% 至 93.09% 的错误集中在触顶样本中。

因此，原始 `256-token` accuracy 的正确定位是：

> short-output-budget diagnostic（短输出预算诊断），而不是最终 quantization quality conclusion（最终量化质量结论）。

## 4. 解释边界

### 可以得出的结论

- `max_new_tokens=256` 与大量错误高度相关。
- BF16、W8A8 与 BnB INT8 都存在明显的输出长度触顶现象。
- 当前原始 accuracy 不能直接解释为量化格式本身造成的完整质量差异。
- W8A8 相比 BF16 的原始差异 `0.9856 percentage points` 仅保留为固定短输出预算下的观察结果。

### 不能得出的结论

- 不能把未触顶样本 accuracy 当作全量真实模型质量。
- 不能将 BnB INT8 的原始 accuracy 直接用于宣布其优于 BF16 或 W8A8。
- 不能将后续定向复测结果命名为 full GSM8K @768 rerun。
- 不能将 AWQ 的 `max_new_tokens=768` 结果与本表中的 `256-token` 结果直接做纯算法 accuracy 排名。

## 5. 定向复测协议

1. 先进行小规模 `256 vs 768` 行为验证。
2. 固定检查 cap-hit 且错误、cap-hit 但原本正确、未 cap-hit 三类样本。
3. 若验证确认更高输出预算能够显著减少截断影响，则重跑该路线的全部 cap-hit 样本。
4. 定向复测配置固定为：
   - `max_new_tokens=768`
   - `temperature=0`
   - `thinking_budget=0`
5. 定向复测对象必须包含全部 cap-hit 样本，不能只选择 cap-hit 且错误样本。
6. 合并结果统一命名为 `targeted corrected evaluation`，不能写为 `full 768-token rerun`。

## 6. 各路线执行状态与后续动作

- BnB INT8：已完成 fixed20 行为验证和全部 348 个历史 cap-hit 样本的 `@768` 定向复测，结果见第 8 节。
- BF16 / vLLM：复测全部 366 个 cap-hit 样本。
- W8A8 / vLLM compressed-tensors：复测全部 395 个 cap-hit 样本。
- 历史 `results/week2_gsm8k_full_seed_oss_max768.csv` 仅有 55 条样本，不构成完整 BF16 768 结果，不纳入正式结论。
- AWQ 已完成 external pre-quantized artifact 的 `768-token` 评测，不纳入本表的同源 `256-token` baseline ranking。
- GPTQ 需要先通过 artifact provenance、vLLM startup、API、smoke test 与小规模性能 Gate，才决定是否进行 full GSM8K benchmark。

## 7. 关联证据

- BF16 summary: `results/week2_gsm8k_full_seed_oss_budget0_summary.csv`
- W8A8 summary: `results/week2_hardening/gsm8k_w8a8_full_budget0_fixed_summary_20260616.csv`
- BnB INT8 cap-hit audit: `evidence/week2_hardening/bnb_int8/bnb_int8_output_cap_audit_20260619.json`
- BnB INT8 provenance: `evidence/week2_hardening/bnb_int8/bnb_int8_final_provenance_20260619.txt`
- Historical BF16/W8A8/AWQ cap-hit audit: `evidence/week2_hardening/awq/checkpoint/gsm8k_output_cap_audit_20260619.txt`
- Historical BF16/W8A8 quality report: `docs/week2_hardening_response_summary.md`

## 8. BnB INT8 输出预算定向复测结果

### 8.1 复测范围与执行口径

BnB INT8 路线使用 Transformers 与 BitsAndBytes `LLM.int8()` 运行时量化。该路线不属于 vLLM TP=2 serving benchmark，因此本节只用于分析输出预算对该运行路径 GSM8K 质量结果的影响，不纳入 BF16/W8A8 serving 性能排名。

历史 full run 在 `max_new_tokens=256` 下完成 1319 条 GSM8K 样本，其中 348 条样本满足 `output_tokens == 256`。这些样本构成定向复测对象。复测保持相同题目、答案抽取逻辑、`temperature=0` 和 `thinking_budget=0`，仅将 `max_new_tokens` 提升至 768。

348 条样本被划分为两个各 174 条的确定性分片，并由两个独立的单 GPU BnB worker 执行。该执行方式用于缩短离线评测时间，不构成张量并行或 vLLM serving 性能测试。

### 8.2 fixed20 行为验证

在完整复测前，先构造 20 条固定样本：

- 10 条历史 cap-hit 且错误样本；
- 5 条历史 cap-hit 但正确样本；
- 5 条历史未触顶且正确样本。

固定样本在 `max_new_tokens=256` 下正确 10 条，accuracy 为 50.00%；在 `max_new_tokens=768` 下正确 20 条，accuracy 为 100.00%。该结果表明，所选历史触顶错误样本可在更高输出预算下恢复正确，同时原本正确样本未出现回归。

### 8.3 全部 348 条 cap-hit 样本复测

| 指标 | 历史 `max_new_tokens=256` | 定向复测 `max_new_tokens=768` |
|---|---:|---:|
| 样本数 | 348 | 348 |
| 正确数 | 69 | 316 |
| 错误数 | 279 | 32 |
| accuracy | 19.8276% | 90.8046% |
| 输出触顶数 | 348 | 0 |

逐题结果以 `question_preview` 进行严格一一匹配。转移结果如下：

| 转移类型 | 样本数 |
|---|---:|
| `wrong_to_correct` | 247 |
| `correct_to_correct` | 69 |
| `wrong_to_wrong` | 32 |
| `correct_to_wrong` | 0 |

历史 279 条触顶错误中，247 条在 `max_new_tokens=768` 下恢复正确，错误修复率为 88.53%。同时，没有历史正确样本在复测中退化为错误。accuracy 在该历史 cap-hit 子集上提高 70.98 个百分点，且复测样本没有继续触及 768 token 上限。

### 8.4 结论与边界

该结果证明，BnB INT8 历史 full run 中大量错误由 `max_new_tokens=256` 的输出预算限制主导，不能直接归因于 BitsAndBytes INT8 运行时量化本身。剩余 32 条错误在输出预算扩大后仍然存在，应作为非截断失败保留，可能涉及模型推理、答案抽取或具体题目难度，不在本轮结果中进一步归因。

本节结果是针对全部 348 条历史 cap-hit 样本的定向修正评测，不是 1319 条 GSM8K test set 的 full `@768` rerun。因此，90.8046% 仅表示该 cap-hit 子集在更高输出预算下的结果，不能替代完整 GSM8K accuracy。

### 8.5 新增证据

- fixed20 输入集：`data/eval/week2_quantization_validation/gsm8k_bnb_int8_256_vs_768_fixed20.jsonl`
- fixed20 manifest：`evidence/week2_hardening/bnb_int8/bnb_int8_256_vs_768_fixed20_manifest_20260620.json`
- fixed20 `@256/@768` 结果：`results/week2_hardening/bnb_int8/output_budget_validation/`
- 348 条分片输入：`data/eval/week2_quantization_validation/bnb_int8_cap_hit_768_shards/`
- 348 条 manifest：`evidence/week2_hardening/bnb_int8/output_budget_validation/bnb_int8_cap_hit_348_manifest_20260620.json`
- worker 原始结果与 summary：`results/week2_hardening/bnb_int8/output_budget_validation/cap_hit_348_max768/`
- worker 运行日志：`logs/week2_hardening/bnb_int8/output_budget_validation/cap_hit_348_max768/`
- 逐题 transition：`results/week2_hardening/bnb_int8/output_budget_validation/cap_hit_348_max768/bnb_int8_cap_hit_256_to_768_transitions_20260620.csv`
- 汇总 JSON：`evidence/week2_hardening/bnb_int8/output_budget_validation/bnb_int8_cap_hit_256_to_768_summary_20260620.json`
