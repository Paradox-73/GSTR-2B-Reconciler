# Kubernetes manifests

Plain manifests for the whole app on one minikube cluster, combined with kustomize
(`kubectl apply -k`). Normally `deploy/ansible/deploy.yml` applies them (Jenkins runs it on
every commit). The steps below do the same thing by hand.

| File | What it creates |
|---|---|
| `namespace.yaml` | namespace `gstr2b` |
| `config.yaml` | ConfigMap `gstr2b-config` (non-secret env vars) |
| `secret.example.yaml` | template for Secret `gstr2b-secrets`; not applied by kustomize |
| `serviceaccounts.yaml` | ServiceAccounts `api`, `worker` (Vault binds its roles to them) |
| `storage.yaml` | PVCs `uploads` and `mlflow-artifacts` |
| `postgres.yaml`, `redis.yaml` | StatefulSets with headless Services; postgres gets a 2Gi volume |
| `api.yaml`, `worker.yaml`, `frontend.yaml` | the app Deployments (+ Services for api and frontend) |
| `mlflow.yaml` | MLflow tracking server (week 4) |
| `hpa.yaml` | autoscalers: api 2-4 pods at 70% CPU, worker 1-5 pods at 60% CPU |
| `ingress.yaml` | `/api` to api:8000, `/` to frontend:8080 |
| `migrations/` | the `alembic upgrade head` Job, kept separate so it can run before the api rolls out |

Runtime settings the images expect are in [`docs/runtime-contract.md`](../../docs/runtime-contract.md).

## 1. Start minikube

```bash
minikube start --driver=docker --cpus 4 --memory 8192
minikube addons enable ingress
minikube addons enable metrics-server
```

8 GB is enough for the app plus ELK. `--cpus` and `--memory` only apply when the cluster
is created; to change them, run `minikube delete` first.

## 2. Load the secret

The real secret file is never committed (`deploy/k8s/secret.yaml` is in `.gitignore`).
Vault replaces this step in issue #19.

```bash
cp deploy/k8s/secret.example.yaml deploy/k8s/secret.yaml
# edit deploy/k8s/secret.yaml: replace every CHANGE_ME, using the same DB password in all three URLs
kubectl apply -f deploy/k8s/namespace.yaml
kubectl apply -f deploy/k8s/secret.yaml
```

To change a value later, edit the file, apply it again, then restart the pods that read it:
`kubectl -n gstr2b rollout restart deployment/api deployment/worker`.

## 3. Apply

Easiest, from `deploy/ansible/`:

```bash
ansible-playbook -i inventory/hosts.ini deploy.yml -e dockerhub_user=<you> -e image_tag=latest
```

By hand, first put your Docker Hub user in each `newName` under `images:` in
`kustomization.yaml` and `migrations/kustomization.yaml` (do not commit that edit), then:

```bash
# 1. database first, because migrations need it
kubectl apply -k deploy/k8s -l app.kubernetes.io/name=postgres
kubectl -n gstr2b rollout status statefulset/postgres

# 2. migrations (a Job cannot be changed after creation, so delete the old one)
kubectl -n gstr2b delete job migrations --ignore-not-found
kubectl apply -k deploy/k8s/migrations
kubectl -n gstr2b wait --for=condition=complete job/migrations --timeout=300s

# 3. everything else
kubectl apply -k deploy/k8s
```

To see what kustomize will send without applying: `kubectl kustomize deploy/k8s`.

## 4. Check the rollout

```bash
kubectl -n gstr2b get pods
kubectl -n gstr2b rollout status deployment/api --timeout=300s
kubectl -n gstr2b get hpa
curl -I http://$(minikube ip)/   # frontend, through the ingress
```

Roll back one Deployment: `kubectl -n gstr2b rollout undo deployment/api`.
Logs: `kubectl -n gstr2b logs deployment/api -f`.

## Troubleshooting

**`kubectl get hpa` shows `<unknown>/70%`.** The HPA has no CPU numbers yet. Check
`minikube addons list | grep metrics-server` says enabled, then wait a minute;
`kubectl top pods -n gstr2b` must print numbers before the HPA can. A pod with no CPU
request also shows `<unknown>`.

**`ImagePullBackOff` or `InvalidImageName`.** `kubectl -n gstr2b describe pod <pod>` shows
the image it tried. `DOCKERHUB_USER/...` means the `images:` block was not filled in
(step 3). A real name that fails means the tag was never pushed or the repo is private.
To test an image you built locally without pushing it:
`minikube image load <you>/gstr2b-api:latest`.

**`Permission denied` writing to `/data/uploads` (or MLflow / Elasticsearch data).**
minikube's default storage is a host directory, and Kubernetes does not apply `fsGroup`
to those, so uid 10001 may not own it. Find the volume path with
`kubectl get pv -o wide` and `kubectl describe pv <name>`, then
`minikube ssh -- sudo chown -R 10001:10001 <path>`.

**`http://$(minikube ip)/` returns 404 from nginx.** The request reached the ingress
controller but matched no rule. Check `kubectl -n gstr2b get ingress` shows an address
(the ingress addon is running), and `kubectl -n gstr2b get endpoints api frontend`
lists pod IPs (empty means no pod is Ready yet). Under WSL or macOS with the docker
driver the minikube IP may not be reachable; run `minikube tunnel` and use
`http://127.0.0.1/`.

## Model registry (MLflow)

Workers poll MLflow every 60s for the model with the `production` alias. On a fresh cluster the
registry is empty, so workers use the model baked into their image (run pages show `v2`). To put
it in the registry as `r1` (or retrain with whatever review decisions exist):

```bash
kubectl -n gstr2b run model-bootstrap --rm -i --restart=Never \
  --image=<dockerhub-user>/gstr2b-trainer:latest \
  --overrides='{"spec":{"containers":[{"name":"model-bootstrap","image":"<dockerhub-user>/gstr2b-trainer:latest","command":["python","-m","trainer","--bootstrap"],"envFrom":[{"configMapRef":{"name":"gstr2b-config"}}],"env":[{"name":"DATABASE_URL","valueFrom":{"secretKeyRef":{"name":"gstr2b-secrets","key":"DATABASE_URL"}}}]}]}}'
```

Use `"command":["python","-m","trainer","--force"]` to retrain now regardless of label count.
(`command`, not `args`: the image has no ENTRYPOINT, so `args` would replace the whole command and
the pod fails with `exec: "--bootstrap": executable file not found`. Tested on a k3s cluster.) The
`trainer` CronJob does the nightly run (skips under 50 new decisions).

## With Vault (`deploy/k8s-vault`)

Once `roles/vault` has run and the KV secrets exist (`deploy/ansible/README.md`), deploy the Vault
variant instead of the base: `kubectl apply -k deploy/k8s-vault`, or
`ansible-playbook ... deploy.yml -e app_use_vault=true` (Jenkins: `APP_USE_VAULT=true`).

What changes: the api and worker pods get a `vault-agent` sidecar that logs in with the pod's
ServiceAccount and writes `/vault/secrets/{db,jwt,admin,token}`; the app reads them through
`DATABASE_URL_FILE` etc. instead of the Kubernetes Secret, and `VAULT_ADDR` turns on Transit
encryption, so files under `/data/uploads` start with `vault:v1:`. The `gstr2b-secrets` Secret
is still needed for postgres itself and the migrations Job.

Tested on k3s: smoke test passes, uploads land encrypted, Ansible rerun reports `changed=0`.
