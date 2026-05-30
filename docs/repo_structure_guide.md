# 仓库结构说明

本文档说明当前 AI Inference Service 仓库的主要目录用途、证据保存边界和后续文件管理规则。

## 1. 核心代码目录

| 目录 | 作用 |
|---|---|
| `app/` | FastAPI 服务、推理入口、后端适配、metrics 接入和 workload routing 逻辑 |
| `scripts/` | benchmark、评测、绘图、量化、GPU metrics 采样和实验辅助脚本 |
| `tests/` | API 与 routing policy 单元测试 |
| `deployment/` | 本地、云端、CX3、vLLM、Prometheus 和 Grafana 相关部署配置 |

这些目录属于项目的可运行工程主体，应保持结构清晰、长期维护。

## 2. 文档目录

| 目录或文件 | 作用 |
|---|---|
| `README.md` | 项目总入口，概述当前能力、关键结果、运行方式和文档入口 |
| `docs/week1_delivery_report.md` | Week1 阶段交付报告 |
| `docs/week2_delivery_summary.md` | Week2 快速交付摘要 |
| `docs/week2_requirement_compliance_matrix.md` | Week2 交付项与证据索引 |
| `docs/week2_performance_optimization_report.md` | Week2 主性能优化报告 |
| `docs/week2_batch_token_tuning_report.md` | Batch-token 调优专项报告 |
| `docs/week2_quantization_feasibility_report.md` | FP32 vs W8A8 量化实验报告 |
| `docs/week2_observability_report.md` | Prometheus / Grafana / metrics / GPU 资源分析报告 |
| `docs/week2_eval_mini_report.md` | GSM8K full benchmark 与代码生成 mini eval 报告 |
| `docs/week2_512k_feasibility_and_resource_analysis.md` | 512K 长上下文资源可行性分析 |
| `docs/week2/seed_oss_128k_context_boundary_review.md` | 128K 长上下文边界实验复盘 |
| `docs/troubleshooting_faq.md` | 部署、推理、监控和 benchmark 故障排查手册 |
| `docs/api_error_codes.md` | API 错误码与边界情况说明 |

`docs/` 中既包含正式交付文档，也包含专项技术说明。正式阅读入口以 `README.md` 和 `docs/week2_requirement_compliance_matrix.md` 为准。

## 3. 结果、日志、图表和证据目录

| 目录 | 作用 | 管理原则 |
|---|---|---|
| `results/` | CSV、JSON、metrics snapshot、benchmark summary 等结构化结果 | 保存可复现、可引用的实验输出 |
| `logs/` | vLLM / FastAPI 启动日志、nvidia-smi、过程快照、失败记录 | 保存实验过程和故障边界 |
| `figures/` | 报告图表和截图 | 按阶段和主题分组保存 |
| `evidence/` | 阶段性冻结证据快照 | 不轻易拆分或删除 |
| `artifacts/` | 压缩证据包和归档包 | 保存重要阶段的整体 evidence bundle |

这些目录存在一定重复，是因为部分文件既在顶层 `logs/` 与 `results/` 中用于当前报告引用，也在 `evidence/` 中作为阶段冻结快照保存。后续不应直接删除重复项，应先确认正式文档引用和 evidence freeze 关系。

## 4. Week2 图表结构

Week2 图表统一保存在 `figures/week2/`。

| 子目录 | 内容 |
|---|---|
| `figures/week2/concurrency/` | 并发 QPS、P50/P95 latency、tokens/s、error rate 图 |
| `figures/week2/context/` | 长上下文 first-pass latency 和 tokens/s 图 |
| `figures/week2/prefix_cache/` | Prefix Cache repeat latency 图 |
| `figures/week2/batch_tokens/` | max_num_batched_tokens 调优图 |
| `figures/week2/quantization/` | FP32 vs W8A8 量化对比图 |
| `figures/week2/observability/` | Grafana / monitoring 相关截图 |

后续新增 Week2 图表应继续放入对应子目录，不再放入 `figures/` 根目录或 `figures/week2/`。

## 5. 外部资源与恢复记录

| 目录 | 作用 |
|---|---|
| `external_volume_records/` | RunPod network volume、pod 重启、GPU residue、旧容器恢复相关记录 |
| `volume_audit/` | volume 文件审计、保留决策和迁移记录 |

这些目录用于解释云端实验中的资源恢复、证据迁移和数据保全过程。虽然不是核心代码，但对实验可信度和复盘有价值。

## 6. 不进入 Git 的内容

以下内容不应进入 Git：

| 类型 | 说明 |
|---|---|
| `__pycache__/` | Python 缓存目录 |
| `*.pyc` | Python 编译缓存 |
| `*.pyo` | Python 优化缓存 |
| `.pytest_cache/` | pytest 缓存 |
| `tmp/` | 临时审计文件和一次性目录树输出 |
| `.DS_Store` | macOS 系统文件 |

这些内容已经写入 `.gitignore`。

## 7. 后续文件管理规则

1. 新增正式文档放入 `docs/`。
2. 新增 Week2 图表放入 `figures/week2/batch_tokens/`、`figures/week2/concurrency/`、`figures/week2/context/`、`figures/week2/quantization/` 等图表子目录。
3. 新增结构化实验结果放入 `results/`，文件名必须包含实验阶段、模型、配置或日期。
4. 新增原始运行日志放入 `logs/`，文件名必须能看出实验主题和日期。
5. 阶段性证据冻结可以放入 `evidence/week2_64k_context/` 等阶段性证据目录，但不要随意复制整个仓库。
6. 大文件、模型权重和完整 checkpoint 不进入 Git，只保存 metadata、配置、日志和必要索引。
7. 正式文档中引用的路径不要随意移动；如需移动，必须同步更新所有文档链接并做 stale path check。

## 8. 当前不立即整理的目录

| 目录 | 暂不整理原因 |
|---|---|
| `logs/` | 多份正式文档正在引用具体日志路径，直接移动会破坏证据链 |
| `results/` | 当前报告、量化对比、GSM8K、batch-token 和 128K 结果依赖这些路径 |
| `evidence/` | 属于阶段性冻结快照，不适合拆散 |
| `artifacts/` | 压缩证据包用于整体归档，不应随意删除 |
| `external_volume_records/` | 记录 RunPod volume 恢复和资源边界，保留用于审计 |
| `volume_audit/` | 记录旧 volume 文件保留决策，保留用于复盘 |

后续如果继续整理，应优先做“新增索引文档”和“引用审计”，而不是直接移动历史 evidence。
