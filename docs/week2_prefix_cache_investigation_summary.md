# Week2 Prefix Cache 复测分析

## 复测背景

在 64K 长上下文测试中，`100000 chars / 56303 input tokens` 的一次测试 latency 为 16.13s，而后续 `110000 chars / 61917 input tokens` 的 latency 为 7.44s。该结果不符合简单的上下文长度线性增长预期，因此需要检查是否受到 prefix cache、warm state、重复 prompt 结构或单次测量噪声影响。

## Prefix Cache 指标变化

| Metric | Before | After | Delta |
|---|---:|---:|---:|
| prefix_cache_queries_total | 171534 | 526194 | 354660 |
| prefix_cache_hits_total | 109520 | 464096 | 354576 |
| estimated hit rate during repeat | - | - | 99.98% |

## 复测结论

交替复测结果显示，56K 与 61.9K 输入在重复请求后 latency 均稳定在约 4.2s 左右，且 prefix cache 命中率很高。因此，后续较低 latency 不能被解释为纯长上下文 prefill 性能，而应解释为 prefix cache enabled、重复长文本 prompt、warm state 共同作用下的工程场景结果。

报告中应明确区分：

1. 首次长上下文梯度测试：用于观察上下文增长下的 latency/tokens/s 趋势。
2. 重复长文档请求测试：用于展示 vLLM prefix cache 在重复前缀场景下的缓存收益。
