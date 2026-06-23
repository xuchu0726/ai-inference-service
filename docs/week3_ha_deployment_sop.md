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

以下命令仅在确认 kubectl context 指向目标集群后执行。

```bash
kubectl apply -f deployment/week3_ha/k8s/namespace.yaml

kubectl apply -f deployment/week3_ha/k8s/gateway-config.yaml
kubectl apply -f deployment/week3_ha/k8s/gateway-resilience-config.yaml

# 先确认 primary/fallback runtime ConfigMap 与 Secret 已由受控环境创建。
kubectl -n ai-inference get configmap week3-primary-runtime week3-fallback-runtime
kubectl -n ai-inference get secret week3-primary-auth week3-fallback-auth

kubectl apply -f deployment/week3_ha/k8s/gateway-service.yaml
kubectl apply -f deployment/week3_ha/k8s/gateway-deployment.yaml
kubectl apply -f deployment/week3_ha/k8s/local_hpa/gateway-hpa.yaml

kubectl apply -f deployment/week3_ha/nginx/nginx-config.yaml
kubectl apply -f deployment/week3_ha/nginx/nginx-deployment.yaml
kubectl apply -f deployment/week3_ha/nginx/nginx-service.yaml

kubectl apply -f deployment/week3_ha/monitoring/prometheus.yaml
kubectl apply -f deployment/week3_ha/monitoring/grafana-dashboard.yaml
kubectl apply -f deployment/week3_ha/monitoring/grafana-core.yaml
```

## 5. 部署验收

```bash
kubectl -n ai-inference rollout status deployment/inference-gateway --timeout=120s
kubectl -n ai-inference rollout status deployment/inference-nginx --timeout=120s
kubectl -n ai-inference rollout status deployment/prometheus --timeout=120s
kubectl -n ai-inference rollout status deployment/grafana --timeout=120s

kubectl -n ai-inference get deployment,pod,service,hpa -o wide
kubectl -n ai-inference describe hpa inference-gateway
kubectl -n ai-inference top pods
```

成功标准：

- inference-gateway 至少 2 个 Ready Pod；
- inference-nginx 至少 2 个 Ready Pod；
- HPA 显示最小副本 2、最大副本 4，且 CPU target 为 50%；
- Gateway 可经 Nginx 访问 `/livez`、`/readyz` 与 `/health`；
- Prometheus 可抓取 Gateway 指标与 `bagel-runpod` 指标；
- Grafana 可打开 Week3 Gateway Resilience 与 Week3 BAGEL Multimodal Observability。

## 6. 负载均衡与容错逻辑

Nginx 仅将请求转发到 Kubernetes Service，不执行 upstream retry。Gateway 负责主后端超时、有界重试、process-local circuit breaker、恢复窗口判断和 fallback 路由。fallback 请求使用固定 `thinking budget=512`，避免双层重试导致重复推理。

## 7. 回滚与停止

```bash
kubectl -n ai-inference rollout undo deployment/inference-gateway
kubectl -n ai-inference rollout undo deployment/inference-nginx

# 停止 Gateway 前先删除 HPA，避免控制器重新扩容。
kubectl -n ai-inference delete hpa inference-gateway
kubectl -n ai-inference scale deployment/inference-gateway --replicas=0
```

## 8. 高价值证据保存

每次重建或复现实验时，保存 `kubectl get deployment,pod,service,hpa -o wide`、`kubectl describe hpa inference-gateway`、`kubectl top pods`、Nginx 与 Gateway 健康响应、Prometheus target 状态、关键 resilience metrics、Grafana 截图，以及失败时的 pod describe 和 container log。
