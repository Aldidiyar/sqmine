#!/usr/bin/env bash
# Deploy the batch workload to whatever cluster kubectl currently points at,
# and prove it ran. Intended for a local Minikube or k3s.
#
# This exists because the Jenkins controller in docker-compose.yml has no
# kubectl and no route to a cluster running on the host. On a real cluster the
# equivalent stage in the Jenkinsfile does the same thing from inside the
# pipeline; on a laptop, running it here is the shorter honest path.
#
#   ./k8s/deploy.sh [image]      default: aldidiyar/sqmine:latest
set -euo pipefail

IMAGE="${1:-aldidiyar/sqmine:latest}"
NS=sqmine
RUN="verify-$(date +%s)"

command -v kubectl >/dev/null || { echo "kubectl is not installed" >&2; exit 1; }
echo "cluster: $(kubectl config current-context)"
echo "image:   ${IMAGE}"

kubectl apply -k "$(dirname "$0")"

if ! kubectl -n "$NS" get secret sqmine-pseudonymisation-key >/dev/null 2>&1; then
    echo "creating a development pseudonymisation key"
    kubectl -n "$NS" create secret generic sqmine-pseudonymisation-key \
        --from-literal=pseudonymisation.key="$(head -c 32 /dev/urandom | base64 | tr -d '\n')"
fi

kubectl -n "$NS" set image cronjob/sqmine-nightly-ingest "sqmine=${IMAGE}"

# A CronJob at 02:17 proves nothing at four in the afternoon, so trigger one
# run now from the same template the schedule uses.
kubectl -n "$NS" create job "$RUN" --from=cronjob/sqmine-nightly-ingest
kubectl -n "$NS" wait --for=condition=complete --timeout=180s "job/$RUN"

echo "--- job output -------------------------------------------------------"
kubectl -n "$NS" logs "job/$RUN"
echo "----------------------------------------------------------------------"
kubectl -n "$NS" get cronjob,job,pod
