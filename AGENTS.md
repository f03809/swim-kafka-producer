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

### Target host setup (Proxmox + k3s)

Create an Ubuntu 22.04/24.04 VM in Proxmox with a static IP and outbound access to Kafka (`10.0.0.94:9092`) and the FAA SWIM Solace endpoints (`ems1/2/3.swim.faa.gov:55443`).

1. Create the `f03809` user and prepare SSH:

```bash
sudo adduser f03809
sudo usermod -aG sudo f03809
sudo mkdir -p /home/f03809/.ssh
echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKeMVLnVGAnmnbwZQAsEIL68b5RNfAnC0tt3MbYO2WV5 github-actions-deploy" | sudo tee /home/f03809/.ssh/authorized_keys
sudo chmod 600 /home/f03809/.ssh/authorized_keys
sudo chown -R f03809:f03809 /home/f03809/.ssh
```

2. Install k3s:

```bash
curl -sfL https://get.k3s.io | sudo sh -
export PATH=$PATH:/usr/local/bin:/usr/local/sbin
kubectl get nodes
```

3. Copy the k3s admin kubeconfig for `f03809`:

```bash
sudo mkdir -p /home/f03809/.kube
sudo cp /etc/rancher/k3s/k3s.yaml /home/f03809/.kube/config
sudo chown f03809:f03809 /home/f03809/.kube/config
sudo chmod 600 /home/f03809/.kube/config
```

Verify as `f03809`:

```bash
su - f03809
kubectl get nodes
```

4. Confirm the cluster has the `swim` namespace after the first deploy (it is created by `k8s/base/namespace.yaml`).

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
