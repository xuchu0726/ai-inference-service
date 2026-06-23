# Week3 高可用推理栈部署 SOP

## 1. 适用范围

本 SOP 用于部署和验收 Seed-OSS 文本推理高可用链路：

`Nginx -> Kubernetes Service -> inference-gateway replicas -> primary / fallback vLLM upstream`

监控链路：

`Gateway / BAGEL metrics -> Prometheus -> Grafana`

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

以下命令仅在目标 Kubernetes 集群执行；不要在 RunPod BAGEL Pod 中执行。

    kubectl apply -f deployment/week3_ha/k8s/namespace.yaml
    kubectl apply -f deployment/week3_ha/k8s/gateway-config.yaml
    kubectl apply -f deployment/week3_ha/k8s/gateway-resilience-config.yaml
    kubectl apply -f deployment/week3_ha/k8s/gateway-service.yaml
    kubectl apply -f deployment/week3_ha/k8s/gateway-deployment.yaml
    kubectl apply -f deployment/week3_ha/k8s/local_hpa/gateway-hpa.yaml
    kubectl apply -f deployment/week3_ha/nginx/nginx-config.yaml
    kubectl apply -f deployment/week3_ha/nginx/nginx-deployment.yaml
    kubectl apply -f deployment/week3_ha/nginx/nginx-service.yaml
    kubectl apply -f deployment/week3_ha/monitoring/prometheus.yaml
    kubectl apply -f deployment/week3_ha/monitoring/grafana-dashboard.yaml
    kubectl apply -f deployment/week3_ha/monitoring/grafana-core.yaml

## 5. 部署成功标准

    kubectl -n ai-inference rollout status deployment/inference-gateway --timeout=120s
    kubectl -n ai-inference rollout status deployment/inference-nginx --timeout=120s
    kubectl -n ai-inference rollout status deployment/prometheus --timeot=120s
    kubectl -n ai-inference rollout status deployment/grafana --timeout=120s
    kubectl -n ai-inference get deployment,pod,service,hpa -o wide
    kubectl -n ai-inference describe hha inference-gateway
    kubectl top pods -n ai-inference

见收条件:

- Gateway Deployment 至少 2 个 Ready Pod。
- Nginx Deployment 至少 2 个 Ready Pod。
- HPA 显示最小副本 2、最大副本 4，CPU 目标 50%。
- Nginx `/nginx-healthz`、Gateway `/livez`、`/readyz` 和 `/health` 可用。
- Prometheus 中 Gateway Pod targets 可抓取；BAGEL 目标 `up{job="bagel-runpod"}` 为 1。
- Grafana 可显示 Week3 Gateway Resilience 与 Week3 BAGEL Multimodal Observability。

## 6. 负载均衡与容错訽逻辑

Nginx 仅负责将请求转发到 Kubernetes Service，不执行 upstream retry。

Gateway 负责主后端超时控制、一次有界重试、失败阈值触发 process-local circuit breaker、恢复窗口后的恢复探测，以及主后端不可用或熔断时的 fallback 路由。fallback 请求固定使用低预算 `thinking budget=512`。

该分层避免 Nginx 与 Gateway 双层重试造成重姍推理请求。

## 7. 回滚与停止

回滚最近一次 Gateway 或 Nginx Deployment 变更：

    kubectl -n ai-inference rollout undo deployment/inference-gateway
    kubectl -n ai-inference rollout undo deployment/inference-nginx

停止 Gateway 前先删除 HPA，避免控制器重新扩容：

    kubectl -n ai-inference delete hpa inference-gateway
    kubectl -n ai-inference scale deployment/inference-gateway --replicas=0

恢姍时重新 apply HPA manifest，并等待 Gateway rollout 完成。

## 8. 证据保存与复盘

每次重新部署或复现实验时，保存以下高价值杀料：

- `kubectl get deployment,pod,service,hpa -o wide`
- `kubectl describe hpa inference-gateway`
- `kubectl top pods -n ai-inference`
- Nginx `/health`、Gateway `/readyz` 响应
- Prometheus targets 与 retry、circuit、fallback 指标
- Grafana 截图
- 失败时的 pod describe、container logs 和 HPA events

这些证据用于复现、性能分析、简历追溯与面试深挛。
