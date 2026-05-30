# RunPod Network Volume 恢复记录归档说明

## 1. 归档目的

本归档用于保存旧 RunPod Network Volume 释放前恢复出来的少量关键记录。

这些文件不属于主推理服务代码，也不属于 Week2 核心性能结果，但对后续复盘云 GPU 实验、解释 RunPod Volume 数据恢复过程、说明 GPU 显存残留和 Pod 重启异常具有辅助价值。

因此，本次不再将这些文件保留为顶层散乱目录，而是压缩保存到 artifacts/archive/，并用本文档说明其来源、内容和后续使用方式。

## 2. 归档位置

归档包路径：

- artifacts/archive/runpod_network_volume_recovery_20260527.tar.gz

原始来源目录：

- external_volume_records/runpod_network_volume_20260527/

该顶层目录已从仓库中移除，内容已通过压缩包归档保存。

## 3. 归档内容

该归档包主要包含以下类型记录：

1. 旧 RunPod Network Volume 的挂载检查记录；
2. GPU 显存残留、Pod restart、stop-start 和新 Pod 启动失败相关诊断记录；
3. 旧 volume 恢复状态快照；
4. old backup 与当前仓库之间的缺失文件检查记录；
5. bootstrap 环境探针记录；
6. 原目录内的 README 说明文件。

## 4. 未纳入归档的内容

以下内容未纳入该归档包，原因是体积大、可复现或不应作为仓库证据长期保存：

1. hf_cache：模型缓存，可通过 Hugging Face 重新下载；
2. venvs：Python virtual environment，可通过 requirements 文件重新安装；
3. tools：工具目录，可重新安装；
4. 临时 clean clone：属于过程性目录，不作为正式证据保留；
5. 重复的旧仓库快照：已通过其他审计文件确认，不重复保留。

## 5. 后续使用方式

正常查看项目代码、Week1/Week2 报告、性能结果和图表时，不需要打开该归档包。

只有在以下场景中才需要查看该归档：

1. 复盘 RunPod Network Volume 数据恢复过程；
2. 解释云 GPU 环境中显存残留或 Pod 重启异常；
3. 证明释放旧 volume 前已经进行过文件审计和关键记录保全；
4. 追溯旧 volume 中是否存在未迁移的重要文件。

## 6. 结论

该目录的原始散文件已不适合继续放在仓库顶层。当前处理方式保留了恢复证据的可追溯性，同时移除顶层目录噪音，使仓库结构更接近正式工程项目。
