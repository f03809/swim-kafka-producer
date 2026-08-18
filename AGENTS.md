# swim-kafka-producer — Agent Notes

## Deployment

The project uses GitHub Actions to build a Docker image, push it to GHCR, and deploy to a Kubernetes cluster via `kubectl` on an SSH jump host.

### Required GitHub secrets

| Secret | Purpose |
|---|---|
| `DEPLOY_HOST` | IP/hostname of the SSH host that can reach the K8s API |
| `DEPLOY_USER` | SSH user on `DEPLOY_HOST` |
| `DEPLOY_SSH_PRIVATE_KEY` | SSH private key for `DEPLOY_USER` (public key must be in `~/.ssh/authorized_keys`) |
| `DEPLOY_SSH_PORT` | SSH port (optional, defaults to `22`) |
| `KUBECONFIG_PATH` | Absolute path to a valid `kubeconfig` on `DEPLOY_HOST` (optional, defaults to `~/.kube/config`) |

### Target host setup

1. Ensure `kubectl` is installed and a working `kubeconfig` exists on the host.
2. Add the SSH public key to `~/.ssh/authorized_keys` for `DEPLOY_USER`.
3. Confirm the cluster has the `swim` namespace (created by the base manifests).

### Pipeline behavior

- Triggered on every push to `main`.
- Builds `ghcr.io/<owner>/swim-kafka-producer:latest` and a SHA tag.
- Renders `k8s/overlays/prod` with `kustomize` and pipes the manifests to `kubectl apply -f -` on `DEPLOY_HOST`.

### Local commands

```bash
uv sync
uv run python -m compileall app
docker build -t swim-kafka-producer:latest .
```
