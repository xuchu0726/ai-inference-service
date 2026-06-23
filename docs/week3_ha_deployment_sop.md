# Week3 高可用推理栈部署 SOP

## 1. 适用范围

本 SOP 用于部署和验收 Seed-OSS 文本推理高可用链路：
`Nginx -> Kubernetes Service -> inference-gateway replicas -> primary / fallback vLLM upstream`。

监控链路：`Gateway / BAGEL metrics -> Prometheus -> Grafana`。

BAGEL 当前为 RunPod 单 Pod 图像理解服务，不属于 Kubernetes Gateway 的多副本数据平面。

## 2. 部署前置条件

- kubectl context 已切换到目标 Kubernetes 集群。
- `ai-inference-gateway:week3-resilience-v9` 已加载到目标节点；Gateway 使用 `imagePullPolicy: Never`。
- metrics-server 可用，`kubectl top pods -n ai-inference` 能返回 CPU 指标。
- primary 与 fallback vLLM upstream 已运行，且 endpoint 不相同。
- 不在仓库提交 upstream API key；认证信息通过 Kubernetes Secret 提供。

## 3. 上游运行时资源

Gateway Deployment 启动前必须存在以下资源：

- ConfigMap：`gateway-config`、`week3-primary-runtime`、`week3-fallback-runtime`、`week3-resilience-runtime`。
- Secret：`week3-primary-auth`、`week3-fallback-auth`。

主上游至少提供 `VLLM_BASE_URL`、`VLLM_MODEL_NAME` 和 `VLLM_ENABLE_SEED_THINKING_BUDGET`；备上游至少提供 `VLLM_FALLBACK_BASE_URL` 和 `VLLM_FALLBACK_MODEL_NAME`。

## 4. 部署顺序

以下命令只能在目标 Kubernetes 集群终端执行，不能在 RunPod BAGEL Pod 中执行。

1. 创建命名空间：

    kubectl apply -f deployment/week3_ha/k8s/namespace.yaml

2. 创建 Gateway 基础与韧性配置：

    kubectl apply -f deployment/week3_ha/k8s/gateway-config.yaml
    kubectl apply -f deployment/week3_ha/k8s/gateway-resilience-config.yaml

3. 在集群外部准备以下资源，并确认名称与 Gateway Deployment 的 `envFrom` 一致：

    - ConfigMap：`week3-primary-runtime`
    - ConfigMap：`week3-fallback-runtime`
    - Secret：`week3-primary-auth`
    - Secret：`week3-fallback-auth`

4. 创建 Gateway Service、Deployment 与 HPA：

    kubectl apply -f deployment/week3_ha/k8s/gateway-service.yaml
    kubectl apply -f deployment/week3_ha/k8s/gateway-deployment.yaml
    kubectl apply -f deployment/week3_ha/k8s/local_hpa/gateway-hpa.yaml

5. 创建 Nginx：

    kubectl apply -f deployment/week3_ha/nginx/nginx-config.yaml
    kubectl apply -f deployment/week3_ha/nginx/nginx-deployment.yaml
    kubectl apply -f deployment/week3_ha/nginx/nginx-service.yaml

6. 创建监控资源：

    kubectl apply -f deployment/week3_ha/monitoring/prometheus.yaml
    kubectl apply -f deployment/week3_ha/monitoring/grafana-dashboard.yaml
    kubectl apply -f deployment/week3_ha/monitoring/grafana-core.yaml

## 5. 部署后验收

执行：

    kubectl -n ai-inference rollout status deployment/inference-gateway --timeout=120s
    kubectl -n ai-inference rollout status deployment/inference-nginx --timeout=120s
    kubectl -n ai-inference rollout status deployment/prometheus --timeout=120s
    kubectl -n ai-inference rollout status deployment/grafana --timeout=120s
    kubectl -n ai-inference get deployment,pod,service,hpa -o wide
    kubectl -n ai-inference describe hpa inference-gateway
    kubectl top pods -n ai-inference

成功标准：

- `inference-gateway` 至少有 2 个 Ready Pod；
- `inference-nginx` 至少有 2 个 Ready Pod；
- HPA 最小副本为 2、最大副本为 4、CPU 目标为 50%；
- Nginx `/nginx-healthz` 返回 200，Gateway `/livez`、`/readyz`、`/health` 可经 Nginx 访问；
- Prometheus Targets 页面中 Gateway Pod 与 `bagel-runpod` 均为 Up；
- Grafana 可显示 `Week3 Gateway Resilience` 与 `Week3 BAGEL Multimodal Observability`。

## 6. 回滚与停止

Gateway 或 Nginx 变更异常时：

    kubectl -n ai-inference rollout undo deployment/inference-gateway
    kubectl -n ai-inference rollout undo deployment/inference-nginx

停止 Gateway 前先删除 HPA，避免控制器重新扩容：

    kubectl -n ai-inference delete hpa inference-gateway
    kubectl -n ai-inference scale deployment/inference-gateway --replicas=0

恢复时重新应用 HPA manifest，并等待 Gateway rollout 成功。

## 7. 复现、学习与证据保存

每次重新部署、扩缩容或故障演练后，保存：

- `kubectl -n ai-inference get deployment,pod,service,hpa -o wide`；
- `kubectl -n ai-inference describe hpa inference-gateway`；
- `kubectl top pods -n ai-inference`；
- Nginx 和 Gateway 健康检查响应；
- Prometheus Targets、retry、circuit breaker、fallback 指标；
- Grafana 截图及对应时间窗口；
- 故障时的 `kubectl describe pod`、容器日志、HPA events、Git commit。

同一轮验证应合并为少量高信息密度 evidence 文件，并及时提交 GitHub。
