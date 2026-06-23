#!/usr/bin/env bash
set -u

NS="ai-inference"
rc=0

check_resource() {
  kind="$1"
  name="$2"
  if kubectl -n "$NS" get "$kind" "$name" >/dev/null 2>&1; then
    echo "OK    $kind/$name"
  else
    echo "MISS  $kind/$name"
    rc=1
  fi
}

echo "===== required resources ====="
check_resource namespace "$NS"
check_resource configmap gateway-config
check_resource configmap week3-primary-runtime
check_resource configmap week3-fallback-runtime
check_resource configmap week3-resilience-runtime
check_resource secret week3-primary-auth
check_resource secret week3-fallback-auth
check_resource deployment inference-gateway
check_resource service inference-gateway
check_resource hpa inference-gateway
check_resource deployment inference-nginx
check_resource service inference-nginx
check_resource deployment prometheus
check_resource deployment grafana

echo
echo "===== rollout status ====="
kubectl -n "$NS" rollout status deployment/inference-gateway --timeout=120s || rc=1
kubectl -n "$NS" rollout status deployment/inference-nginx --timeout=120s || rc=1

echo
echo "===== runtime state ====="
kubectl -n "$NS" get deployment,pod,service,hpa -o wide || rc=1

echo
echo "===== HPA ====="
kubectl -n "$NS" get hpa inference-gateway -o custom-columns=NAME:.metadata.name,MIN:.spec.minReplicas,MAX:.spec.maxReplicas,TARGET:.spec.metrics[0].resource.target.averageUtilization,CURRENT:.status.currentReplicas || rc=1

echo
echo "===== resource metrics ====="
kubectl -n "$NS" top pods || true

exit "$rc"
