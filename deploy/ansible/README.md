# Ansible

Two playbooks, both run against `localhost` (the laptop that hosts minikube and Jenkins).

| Playbook | Roles | When |
|---|---|---|
| `site.yml` | common, docker, k8s_cluster, vault, elk, monitoring, app_deploy | once, on a fresh Ubuntu machine |
| `deploy.yml` | app_deploy | every commit; Jenkins runs it with the new image tag |

| Role | What it does |
|---|---|
| `common` | apt base packages, Python Kubernetes client for the `kubernetes.core` modules |
| `docker` | Docker Engine from Docker's apt repo, adds you to the `docker` group |
| `k8s_cluster` | kubectl, minikube and helm binaries; starts minikube; enables ingress and metrics-server |
| `vault` | Vault Helm chart (namespace `vault`, injector on); KV v2, Transit key `uploads`, Kubernetes auth, policies and roles for api/worker/trainer |
| `elk` | Elasticsearch, Logstash, Kibana, Filebeat in namespace `logging`; configs from `deploy/elk/` |
| `monitoring` | Prometheus + Grafana in namespace `monitoring`, built with kustomize from `deploy/k8s-monitoring/` |
| `app_deploy` | pins image tags, starts postgres, runs the migrations Job, applies `deploy/k8s`, waits for every rollout |

Settings (namespace, minikube size, ELK heap, Docker Hub user) are in `group_vars/all.yml`.
Tool versions are in each role's `defaults/main.yml`.

## Setup

Ansible runs on Linux only. On Windows, use WSL 2 with Ubuntu (see below).

```bash
sudo apt install pipx && pipx install ansible-core   # or any Ansible >= 2.15
cd deploy/ansible
ansible-galaxy collection install -r requirements.yml
```

`requirements.yml` installs `kubernetes.core` and `community.general`.

## Run

```bash
cd deploy/ansible

# fresh machine, everything (asks for your sudo password)
ansible-playbook -i inventory/hosts.ini site.yml -K -e dockerhub_user=<you>

# one part only
ansible-playbook -i inventory/hosts.ini site.yml -K --tags vault

# deploy one image tag (what Jenkins does)
ansible-playbook -i inventory/hosts.ini deploy.yml -e dockerhub_user=<you> -e image_tag=<git-sha>
```

Run as your normal user, not with `sudo`: minikube refuses to run as root, and the
tasks that need root ask for it themselves. Every role can be re-run; a second run
should report no changes except where noted in the task.

Before the first `app_deploy`, create the app secret (`deploy/k8s/README.md`, step 2);
the role stops with a message if it is missing.

After `vault` runs, put the app secrets into Vault by hand (they never go in git):

```bash
kubectl -n vault exec -it vault-0 -- vault kv put secret/gstr2b/db username=gstr2b password=<db password>
kubectl -n vault exec -it vault-0 -- vault kv put secret/gstr2b/app jwt_secret=<random> admin_password=<password>
```

Vault runs in dev mode (in memory, unsealed). If `vault-0` restarts, re-run
`--tags vault` and the two commands above.

Kibana: `kubectl -n logging port-forward svc/kibana 5601`, then open http://localhost:5601.

## Jenkins

Jenkins runs `deploy.yml` as the `jenkins` user, which needs:

- membership of the `docker` group: `sudo usermod -aG docker jenkins`, then restart Jenkins
- a kubeconfig for minikube: copy `~/.kube/config` and `~/.minikube/` (the certificates the
  config points to) into the jenkins home, and fix the paths inside the config
- `ansible-playbook` and `kubectl` on its `PATH`

`app_deploy` only calls `kubectl`, so the jenkins user does not need the Python Kubernetes client.

## WSL (Windows)

1. Install Ubuntu: `wsl --install -d Ubuntu-24.04`, and run everything inside it.
2. Turn on systemd so the docker service can start: add `[boot]` and `systemd=true` to
   `/etc/wsl.conf`, then `wsl --shutdown` from Windows.
3. Give WSL enough memory for an 8 GB minikube: in `%UserProfile%\.wslconfig` set
   `[wsl2]` / `memory=12GB`.
4. If you use Docker Desktop with WSL integration instead of Docker Engine inside WSL,
   skip the docker role (`--skip-tags docker`) and pass `-e '{"minikube_shell": "sh -c"}'`.
5. The minikube IP is usually not reachable from Windows. Run `minikube tunnel` in a
   separate terminal and use `http://127.0.0.1/`.
