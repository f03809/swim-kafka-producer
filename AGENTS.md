# swim-kafka-producer — Agent Notes

## Deployment

The project uses GitHub Actions to build a Docker image, push it to GHCR, and deploy to a Kubernetes cluster via a self-hosted runner on the Proxmox VM.

### Required GitHub secrets

| Secret | Purpose |
|---|---|
| `SWIM_USERNAME` | FAA SWIM username |
| `SWIM_PASSWORD` | FAA SWIM password |
| `KUBECONFIG_PATH` | Absolute path to a valid `kubeconfig` on the self-hosted runner (optional, defaults to `~/.kube/config`) |

### Target host setup (Proxmox + k3s)

Create an Ubuntu 22.04/24.04 VM in Proxmox with a static IP and outbound access to Kafka (`10.0.0.94:9092`) and the FAA SWIM Solace endpoints (`ems1/2/3.swim.faa.gov:55443`).

The `deploy` GitHub Actions job runs on a **self-hosted runner** installed on this VM. The runner connects out to GitHub and then runs `kubectl` locally, so the private `10.0.0.0/24` network does not need to be exposed to the internet.

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

4. Install the GitHub Actions self-hosted runner as `f03809`:

Get a fresh registration token from the repo Actions > Runners page or by running on this machine (after installing `gh` and `gh auth login`):

```bash
TOKEN=$(gh api repos/f03809/swim-kafka-producer/actions/runners/registration-token --method POST --jq .token)
echo $TOKEN
```

Then install the runner:

```bash
mkdir -p ~/actions-runner && cd ~/actions-runner
RUNNER_VERSION=2.317.0
curl -o actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz -L https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz
tar xzf actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz
./config.sh --url https://github.com/f03809/swim-kafka-producer --token "<TOKEN>" --name proxmox-k3s --labels self-hosted
./run.sh
```

For production, run it as a service:

```bash
sudo ./svc.sh install f03809
sudo ./svc.sh start
```

5. Confirm the cluster has the `swim` namespace after the first deploy (it is created by `k8s/base/namespace.yaml`).

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
