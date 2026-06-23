#!/usr/bin/env bash
set -u

NS="${1:-ai-inference}"
failed=0

check() {
  if kubectl -n "$NS" get "$1" "$2" >/dev/null 2>&1; then
    echo "OK   $1/$2"
  else
    echo "MISS $1/$2"
    failed=1
  fi
}

echo "===== required resources ====="
kubectl get namespace "$NS" >/dev/null 2>&1 || failed=1
check configmap gateway-config
check configmap week3-primary-runtime
check configmap week3-fallback-runtime
check configmap week3-resilience-runtime
check secret week3-primary-auth
check secret week3-fallback-auth
check deployment inference-gateway
check service inference-gateway
check hpa inference-gateway
check deployment inference-nginx
check service inference-nginx
check deployment prometheus
check deployment grafana

echo
echo "===== runtime state ====="
kubectl -n "$NS" get deployment,pod,service,hpa -o wide || failed=1

echo
echo "===== HPA state ====="
kubectl -n "$NS" describe hpa inference-gateway || failed=1

echo
echo "===== resource metrics ====="
kubectl -n "$NS" top pods || true

echo
echo "===== result ====="
if [ "$failed" -eq 0 ]; then echo "PASS"; else echo "FAIL"; fi
