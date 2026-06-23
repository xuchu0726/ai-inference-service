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

以下命令仅作为目标 Kubernetes 集群中的部署流程记录；不得在当前 RunPod Pod 中直接执行。

### 4.1 创建命名空间和运行时依赖

先应用命名空间，然后在目标集群中创建或更新第 3 节列出的 ConfigMap 与 Secret。主、备 upstream 的 URL、模型名和 API key 必须指向两个独立且已健康的 vLLM 服务。

### 4.2 部署 Gateway、HPA、Nginx 与监控组件

```bash
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
```

部署顺序的原则是：先保证 Gateway 所依赖的运行时配置和 upstream 已存在，再创建 Gateway 与 HPA；Gateway Ready 后再部署 Nginx；最后部署 Prometheus 与 Grafana。

## 5. 部署验收标准

```bash
kubectl -n ai-inference rollout status deployment/inference-gateway --timeout=120s
kubectl -n ai-inference rollout status deployment/inference-nginx --timeout=120s
kubectl -n ai-inference rollout status deployment/prometheus --timeout=120s
kubectl -n ai-inference rollout status deployment/grafana --timeout=120s

kubectl -n ai-inference get deployment,pod,service,hpa -o wide
kubectl -n ai-inference describe hpa inference-gateway
kubectl top pods -n ai-inference
```

成功标准：

- `inference-gateway` 至少有 2 个 Ready Pod。
- `inference-nginx` 至少有 2 个 Ready Pod。
- HPA 显示最小副本数 2、最大副本数 4，并能读取 CPU 指标。
- Nginx 的 `/nginx-healthz` 返回 200；Gateway 的 `/livez`、`/readyz` 和 `/health` 可经 Nginx 访问。
- Prometheus 中 Gateway Pod target 与 `bagel-runpod` target 均为 Up。
- Grafana 可显示 `Week3 Gateway Resilience` 与 `Week3 BAGEL Multimodal Observability`。

## 6. 回滚与停止

Gateway 或 Nginx 部署变更异常时，在目标 Kubernetes 集群执行以下回滚命令：

```bash
kubectl -n ai-inference rollout undo deployment/inference-gateway
kubectl -n ai-inference rollout undo deployment/inference-nginx
```

停止 Gateway 负载前，先删除 HPA，避免控制器将副本数重新扩回目标值：

```bash
kubectl -n ai-inference delete hpa inference-gateway
kubectl -n ai-inference scale deployment/inference-gateway --replicas=0
```

恢复服务时，重新应用 HPA manifest，并等待 Gateway rollout 成功。

## 7. 复现、学习与证据保存

每次重新部署、扩缩容或故障演练后，保存以下高价值证据：

- `kubectl -n ai-inference get deployment,pod,service,hpa -o wide`；
- `kubectl -n ai-inference describe hpa inference-gateway`；
- `kubectl top pods -n ai-inference`；
- Nginx `/nginx-healthz`、Gateway `/livez`、`/readyz`、`/health` 的响应；
- Prometheus target 状态、retry、circuit breaker、fallback 指标；
- Grafana 截图与对应时间窗口；
- 失败时的 `kubectl describe pod`、容器日志、HPA events 和当前 Git commit。

建议将同一轮验证的原始输出合并为一个高信息密度 evidence 文件，并在实验完成后及时提交 GitHub。
