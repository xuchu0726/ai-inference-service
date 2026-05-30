# Volume Audit 归档说明

## 1. 归档目的

本归档用于保存旧 RunPod Network Volume 释放前的仓库审计、文件差异检查和证据保全决策记录。

这些文件不属于推理服务代码，也不属于 Week2 核心性能结果，但对后续复盘云 GPU 实验迁移过程、解释旧 volume 中哪些文件被保留或排除、证明释放旧 volume 前已完成审计具有辅助价值。

因此，本次不再将 `volume_audit/` 作为顶层目录保留，而是压缩保存到 `artifacts/archive/`，并通过本文档说明其来源、内容和使用方式。

## 2. 归档位置

归档包路径：

- `artifacts/archive/volume_audit_20260527.tar.gz`

原始来源目录：

- `volume_audit/`

该顶层目录已从仓库中移除，内容已通过压缩包归档保存。

## 3. 归档内容

该归档包主要包含以下类型记录：

1. GitHub clean 仓库与旧 volume 仓库的文件对比清单；
2. GitHub-only 文件清单；
3. volume-only 文件清单；
4. 需要保存到 GitHub 的旧 volume 独有 evidence 清单；
5. Prometheus 原始 TSDB 归档文件清单；
6. old backup 检查和保存决策；
7. Network Volume 保存决策；
8. 旧 workspace 顶层文件和 tar 包预览记录。

## 4. 主要结论

根据审计记录，旧 RunPod Network Volume 中没有 GitHub 缺失的核心代码或正式文档。

旧 volume 独有内容主要属于以下几类：

1. 实验日志；
2. 运行环境记录；
3. GPU 显存残留和 Pod 重启异常诊断；
4. Prometheus 原始监控数据；
5. 临时迁移和审计过程记录。

其中，关键小型 logs/results 已进入仓库，Prometheus 原始监控数据已单独压缩保存，旧完整仓库快照已保存为 artifact。`hf_cache`、`venvs`、`tools`、临时 clean clone、`.git`、`__pycache__` 等内容不作为正式证据保留。

## 5. 后续使用方式

正常查看项目代码、Week1/Week2 报告、性能结果和图表时，不需要打开该归档包。

只有在以下场景中才需要查看该归档：

1. 复盘旧 RunPod Network Volume 的文件迁移过程；
2. 解释为什么某些缓存、虚拟环境或临时目录没有保存；
3. 证明释放旧 volume 前已经完成文件审计；
4. 追溯旧 volume 中是否存在未迁移的重要 evidence；
5. 学习云 GPU 项目中如何做实验资产保全和仓库清理。

## 6. 结论

`volume_audit/` 的原始散文件不适合继续放在仓库顶层。当前处理方式保留了审计记录的可追溯性，同时移除了顶层目录噪音，使仓库结构更接近正式工程项目。
