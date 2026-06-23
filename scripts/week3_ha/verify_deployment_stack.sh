#!/usr/bin/env bash
set -u

NS="ai-inference"
rc=0

check() {
  if kubectl -n "$NS" get "$1" "$2" >/dev/null 2>&1; then
    echo "OK    $1/$2"
  else
    echo "MISS  $1/$2"
    rc=1
  fi
}

echo "===== required resources ====="
check configmap gateway-config
check configmap week3-primary-runtime
check configmap week3-fallback-runtime
check configmap week3-resilience-runtime
check secret week3-primary-auth
check secret week3-fallback-auth
check deployment inference-gateway
check service inference-gateway
check hpa inference-gateway
check configmap inference-nginx-config
check deployment inference-nginx
check service inference-nginx
check configmap prometheus-config
check deployment prometheus
check service prometheus
check configmap grafana-datasource
check configmap grafana-dashboard-provider
check deployment grafana
check service grafana

echo
echo "===== rollout status ====="
kubectl -n "$NS" rollout status deployment/inference-gateway --timeout=120s || rc=1
kubectl -n "$NS" rollout status deployment/inference-nginx --timeout=120s || rc=1
kubectl -n "$NS" rollout status deployment/prometheus --timeout=120s || rc=1
kubectl -n "$NS" rollout status deployment/grafana --timeout=120s || rc=1

echo
echo "===== runtime state ====="
kubectl -n "$NS" get deployment,pod,service,hpa -o wide || rc=1

echo
echo "===== HPA ====="
kubectl -n "$NS" describe hpa inference-gateway || rc=1

echo
echo "===== resource metrics ====="
kubectl -n "$NS" top pods || true

exit "$rc"
