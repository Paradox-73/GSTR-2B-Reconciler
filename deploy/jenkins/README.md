# Jenkins for this project

A Jenkins that comes up already configured: admin user, the `smoke-user` credential, its login
to Vault (where the Docker Hub token lives), the global env vars the Jenkinsfile reads, and the `gstr2b-reconciler` pipeline job
with **GitHub hook trigger for GITScm polling** switched on. All of it comes from `casc.yaml`
(Jenkins Configuration as Code), so there is no setup wizard and nothing to click.

The image also has the tools the Jenkinsfile runs on the Jenkins machine itself: `docker` (talks
to the host's Docker through the mounted socket), `kubectl` and `ansible-playbook`.

## Start it

```bash
cp deploy/jenkins/.env.example deploy/jenkins/.env      # fill it in
kubectl config view --flatten --minify > deploy/jenkins/kubeconfig   # minikube's, with certs inlined
docker compose -f deploy/jenkins/docker-compose.yml up -d --build
```

Open http://localhost:8081 (or `JENKINS_PORT`), log in as `admin` with `JENKINS_ADMIN_PASSWORD`.

`kubeconfig` must reach the cluster **from inside the Jenkins container**. With minikube's
docker driver the API server is on the minikube network, so either attach Jenkins to it
(`docker network connect minikube gstr2b-jenkins-jenkins-1`) or point `server:` at an address
the container can reach. Test with
`docker compose -f deploy/jenkins/docker-compose.yml exec jenkins kubectl get nodes`.

## Docker Hub token in Vault

The Push stage reads the Docker Hub user and token from Vault (`secret/jenkins/dockerhub`) with
the Jenkins Vault plugin; Jenkins logs in with an AppRole and stores no token of its own.

1. Pick two random strings for `VAULT_ROLE_ID` and `VAULT_SECRET_ID` in `.env`
   (`openssl rand -hex 16` twice), and set `VAULT_ADDR=http://<minikube node ip>:30820`.
2. Register them and store the token (also after every Vault restart, dev mode forgets):
   `ansible-playbook -i deploy/ansible/inventory/hosts.ini deploy/ansible/site.yml --tags vault -e vault_jenkins_role_id=<VAULT_ROLE_ID> -e vault_jenkins_secret_id=<VAULT_SECRET_ID> -e dockerhub_user=<user> -e dockerhub_token=<token>`
3. Test from the Jenkins container: `curl -s $VAULT_ADDR/v1/sys/health` answers JSON.

The AppRole's policy reads that one path only, and the path sits outside `secret/gstr2b/`, which
the app pods can read.

## GitHub webhook (push -> build)

GitHub has to reach Jenkins, so expose it with the bundled Cloudflare quick tunnel:

```bash
docker compose -f deploy/jenkins/docker-compose.yml --profile tunnel up -d
docker compose -f deploy/jenkins/docker-compose.yml logs tunnel | grep trycloudflare.com
```

Then in GitHub: repo Settings > Webhooks > Add webhook:
- Payload URL: `https://<the-trycloudflare-url>/github-webhook/` (trailing slash matters)
- Content type: `application/json`, events: just the push event

The quick-tunnel URL changes every time the tunnel restarts, so update the webhook after a
restart. Set `JENKINS_URL` in `.env` to the tunnel URL too, so build links point the right way.

## Tested

On a k3s test cluster, with a local registry standing in for Docker Hub
(`REGISTRY` and `DOCKERHUB_USER` both `localhost:5001`), the job came up from `casc.yaml` alone and the full
pipeline passed (build #4, 255 s): tests, golden set, model gate, build, Trivy, push, Ansible
deploy in Vault mode, smoke test. Earlier runs found and fixed: `COPY --chmod` needs BuildKit (the
image now has buildx), 3 critical CVEs in the frontend base image, the smoke test's env vars
going missing inside a docker agent. A failed smoke test rolled api/worker/frontend back.

## Security note

The container runs as root because it drives the host's Docker through the socket, which is
root-equivalent anyway. Fine for a laptop demo, not for a shared server.
