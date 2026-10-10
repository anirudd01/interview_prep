#!/usr/bin/env bash
# Graceful-shutdown experiment on kind: rolling restart under load,
# first WITHOUT preStop, then WITH preStop, and compare loadgen error counts.
#
# Usage:   ./run_demo.sh            # both rounds
#          ./run_demo.sh without    # just the broken config
#          ./run_demo.sh with       # just the fixed config
#          ./run_demo.sh cleanup    # delete the kind cluster
#
# Needs: docker (running), kind, kubectl. Works from Git Bash on Windows.
set -euo pipefail
cd "$(dirname "$0")"

CLUSTER=drain-demo
IMAGE=drain-demo:local
MODE=${1:-both}

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

if [[ "$MODE" == "cleanup" ]]; then
  kind delete cluster --name "$CLUSTER"
  exit 0
fi

setup() {
  if ! kind get clusters 2>/dev/null | grep -qx "$CLUSTER"; then
    say "Creating kind cluster '$CLUSTER'"
    kind create cluster --name "$CLUSTER" --config k8s/kind-config.yaml
  fi
  kubectl config use-context "kind-$CLUSTER" >/dev/null
  say "Building image and loading it into kind"
  docker build -t "$IMAGE" .
  kind load docker-image "$IMAGE" --name "$CLUSTER"
}

deploy() {  # $1 = with | without
  kubectl apply -f k8s/app.yaml
  if [[ "$1" == "without" ]]; then
    # Strip the preStop hook to reproduce the race.
    kubectl patch deployment drain-demo --type=json \
      -p='[{"op":"remove","path":"/spec/template/spec/containers/0/lifecycle"}]'
  fi
  kubectl rollout status deployment/drain-demo --timeout=180s
  # Wait for any pods from the previous config to finish terminating.
  while kubectl get pods -l app=drain-demo 2>/dev/null | grep -q Terminating; do sleep 2; done
}

round() {  # $1 = with | without
  say "ROUND: $1 preStop"
  deploy "$1"

  kubectl delete pod loadgen --ignore-not-found --wait=true >/dev/null
  kubectl apply -f k8s/loadgen.yaml
  kubectl wait --for=condition=Ready pod/loadgen --timeout=60s
  sleep 8   # steady-state traffic first

  say "Rolling restart under load (watch app logs: kubectl logs -l app=drain-demo -f --prefix)"
  kubectl rollout restart deployment/drain-demo
  kubectl rollout status deployment/drain-demo --timeout=300s

  say "Waiting for loadgen to finish"
  kubectl wait --for=jsonpath='{.status.phase}'=Succeeded pod/loadgen --timeout=300s
  kubectl logs loadgen > "loadgen_$1.log"
  grep -E 'ERRORS|SUMMARY|requests:|errors by kind|distinct pods' "loadgen_$1.log" || true
  echo "(full per-second output in loadgen_$1.log)"
}

setup
case "$MODE" in
  without) round without ;;
  with)    round with ;;
  both)    round without; round with ;;
  *) echo "unknown mode: $MODE"; exit 1 ;;
esac

say "Done. Re-run a round any time; './run_demo.sh cleanup' deletes the cluster."
