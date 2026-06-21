# Week2 量化路线选型矩阵

## 最终结论

本阶段已完成 BF16、W8A8 compressed-tensors、BnB INT8 与 AWQ 四条量化/部署路线的真实验证，但它们的 checkpoint 来源、dtype、kernel、prompt 模板与 serving runtime 不完全一致，因此不能合并成单一“量化精度排行榜”。

W8A8 compressed-tensors 是当前主推荐路线。该 artifact 由本项目完成离线量化，已形成 vLLM + FastAPI serving 闭环，并具备受控吞吐、P95 延迟、模型加载显存、KV Cache headroom、完整 GSM8K 与 output-cap 定向复测证据。

## 路线与证据

| 路线 | Full GSM8K 结果 | 输出预算证据 | 运行栈边界 | 可得结论 |
|---|---|---|---|---|
| BF16 / vLLM | 1319 条，999 正确，75.7392%，max_new_tokens=256 | 366 条 cap-hit 复测至 768；333 正确，90.9836%；263 条错误恢复为正确 | 同源 vLLM 基线 | 原始 full 结果仅代表短输出预算下的 serving 行为，不是最终数学推理质量 |
| W8A8 compressed-tensors / vLLM | 1319 条，986 正确，74.7536%，max_new_tokens=256 | 395 条 cap-hit 复测至 768；353 正确，89.3671%；272 条错误恢复为正确；1 条仍触顶 | 自主离线量化 artifact；vLLM + FastAPI | 主 serving 路线，已完成性能、显存、KV Cache 与质量边界验证 |
| BnB INT8 / Transformers | 1319 条，1009 正确，76.4973%；0 API failed | 348 条 cap-hit 复测至 768；316 正确，90.8046%；247 条错误恢复为正确 | Transformers + BitsAndBytes，不是 vLLM TP=2 benchmark | 已完成运行时量化质量与截断诊断；不得进入 vLLM 吞吐排名 |
| AWQ external artifact / AWQ-Marlin | 1319 条，1258 正确，95.3753%；max_new_tokens=768；0 API failed | 10 条 smoke 从 256 下的 5/10 恢复为 768 下的 10/10 | 第三方 AWQ artifact；vLLM FP16 + AWQ-Marlin | 已验证外部 AWQ serving stack；不能解释为单纯“4-bit 优于 8-bit” |
| GPTQ | 未形成真实评测结果 | 未完成 | 未形成稳定 artifact 或 serving | 明确未完成，不纳入结果比较 |

## 可比性与解释边界

1. BF16 与 W8A8 的历史 full GSM8K 不能解释为纯量化精度对照。W8A8 adapter 额外加入 system message 与 evaluation instruction，1319 条样本均固定多出 72 input tokens。

2. BF16、W8A8 与 BnB INT8 的历史 full run 均使用 max_new_tokens=256。其 accuracy 应定位为短输出预算诊断。后续 768 定向复测仅解释 cap-hit 子集，不替代完整 1319 条 full @768 重跑。

3. AWQ 使用第三方预量化 checkpoint、自带 chat template、FP16 与 AWQ-Marlin backend。其 95.3753% 说明该 serving stack 在完整输出预算下可稳定完成 GSM8K，不应归因于 AWQ 位宽本身。

4. 吞吐、P95 延迟、模型加载显存与 KV Cache 收益只使用受控的 BF16 vs W8A8 vLLM microbenchmark。两侧使用相同 workload multiset、batch profile 与固定输出长度。

## 当前选型

- 主 serving 路线：W8A8 compressed-tensors + vLLM + FastAPI。
- 同源基线：BF16 + vLLM。
- 运行时量化诊断路线：BnB INT8 + Transformers。
- 外部部署替代方案：AWQ artifact + vLLM FP16 + AWQ-Marlin。
- 未完成路线：GPTQ。

## 关键证据位置

- 协议审计：docs/week2_quantization_protocol_audit.md
- BF16 cap-hit：results/week2_hardening/bf16_controlled/cap_hit_366_max768/
- W8A8 cap-hit：results/week2_hardening/w8a8_controlled/cap_hit_395_max768/
- BnB full audit：evidence/week2_hardening/bnb_int8/bnb_int8_full_combined_audit_20260621.json
- BnB cap-hit audit：evidence/week2_hardening/bnb_int8/output_budget_validation/bnb_int8_cap_hit_256_to_768_summary_20260620.json
- AWQ protocol boundary：evidence/week2_hardening/awq/checkpoint/awq_gsm8k_protocol_comparability_20260619.txt
- AWQ full summary：results/week2_hardening/awq/gsm8k_awq_marlin_full_budget0_max768_20260619_summary.csv
