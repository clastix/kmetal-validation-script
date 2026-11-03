# Configuration: `setup.env`

[← Index](README.md)

`setup.env` describes the under cluster as the customer intends it: nodes, roles, networks,
VLANs and addresses. The `undercluster` checks compare the real nodes against it. `kmetal` uses
it optionally, for the checks that need SSH.

The file is **sourced by bash**: it is plain variable assignments plus associative arrays. Load a
different file with `-e FILE`; the default is `./setup.env`.

## Keys

### SSH

| Key | Default | Meaning |
|---|---|---|
| `SSH_USER` | `ubuntu` | User on every node; it connects to the node's `mgmt` address |
| `SSH_OPTS` | `-o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new` | Extra `ssh` options, e.g. `-J user@bastion` or `-i key` |
| `SSH_SUDO` | `sudo -n` | Prefix for commands that need root; `""` when `SSH_USER` is root |

### Size

| Key | Meaning |
|---|---|
| `CP_COUNT` | Expected number of control planes; must equal the `cp` rows in `NODES` (optional) |
| `WORKER_COUNT` | Expected number of workers; must equal the `worker` rows in `NODES` (optional) |

### Networks carrying a node address

| Key | Meaning |
|---|---|
| `NETWORKS` | Space-separated network names. `mgmt`, `tenant` and `overlay` are mandatory; others (e.g. `storage`) are allowed. **The address columns of `NODES` follow this order.** |
| `NET_IFACE[net]` | Interface name on the nodes: a VLAN sub-interface (`bond0.104`), a bond or a NIC |
| `NET_VLAN[net]` | VLAN ID the interface must carry. Empty or `0`: the interface is not a VLAN device, and the ID is not checked |
| `NET_CIDR[net]` | The network, as a canonical CIDR (network address, not a host address) |
| `NET_MTU[net]` | Optional expected MTU. Above 1500, a do-not-fragment ping checks it end to end |
| `NET_INTERNET` | The only network allowed to reach the internet (default `mgmt`) |
| `OPTIONAL_NETWORKS` | Networks whose absence is a WARN or INFO, not a FAIL (e.g. a storage VLAN) |

The network names have a meaning to the checks:

| Name | Used for |
|---|---|
| `mgmt` | SSH target, internet egress, the `loadBalancer.management` MetalLB range |
| `tenant` | The `loadBalancer.tenantControlPlanes` MetalLB range |
| `overlay` | The Kube-OVN tunnel; required on workers, optional on control planes |

### Provider networks

Provider networks carry tenant egress and EIPs. They exist on **workers only** and their
interface carries **no IP address**. Declare the default ones here; additional ones created by
the platform are found in the `KMetal` resource (see [Topology model](topology-model.md#provider-networks)).

| Key | Meaning |
|---|---|
| `PROVIDER_NETWORKS` | Space-separated names, one or more |
| `PROV_IFACE[name]` | Interface name on the workers |
| `PROV_VLAN[name]` | Expected VLAN ID; empty or `0` when not a VLAN device |

### Nodes

`NODES` is a multi-line table, one row per node:

```
name   role   <one address per NETWORKS entry>
```

- `role` is `cp` or `worker`.
- An address may carry a prefix (`10.0.0.5/24`). Without one, the prefix of `NET_CIDR` is
  expected on the interface.
- `-` means the node has no address on that network (e.g. no overlay on a control plane).
- `#` starts a comment; blank lines are ignored.
- The `mgmt` column is required on every node: it is the SSH target.

### Kube-OVN central nodes

| Key | Meaning |
|---|---|
| `CENTRAL_NODES` | Space-separated node names. Read from `spec.networking.kubeOVN.centralNodes` when a kubeconfig works; set it here only to describe a cluster where kMetal is not yet installed. `undercluster` uses it for context messages |

### Probes

| Key | Default | Meaning |
|---|---|---|
| `INTERNET_PROBE_URL` | `https://ghcr.io` | URL fetched to prove internet egress (nodes and tenant pods) |
| `INTERNET_PROBE_IP` | `1.1.1.1` | Address pinged per network |
| `DNS_PROBE` | `ghcr.io` | Name resolved on every node |
| `ENCAP_TEST_PORT` | `6090` | UDP port of the temporary test tunnel (Geneve); VXLAN uses the next port. Kept away from Kube-OVN's own `6081` |

### End-to-end test

| Key | Default | Meaning |
|---|---|---|
| `E2E_SUBNET_CIDR` | `10.250.0.0/24` | Subnet given to **every** test environment, in both scenarios; the overlap is intentional |
| `E2E_CLUSTERCLASS` | auto | ClusterClass to use. Auto: `kubevirt-standard`, then `kubevirt-expert`, then `kubevirt-kubeadm`, then the first one found |
| `E2E_K8S_VERSION` | auto | Kubernetes version; must be one of `osArtifact.tags`. Auto: the first tag |
| `E2E_MACHINE_SIZE` | `small` | `machineSize` variable |
| `E2E_DATASTORE` | `default` | `controlPlane.dataStoreName` variable |
| `E2E_WORKERS_A` / `E2E_WORKERS_B` | `2` / `1` | Workers in the two clusters of the `e2e` scenario (one tenant, two environments) |
| `E2E_TENANT1_WORKERS` / `E2E_TENANT2_WORKERS` | `1` / `2` | Workers in the two clusters of the `e2e-tenants` scenario (two tenants). Different counts let the isolation probe find an address used by only one tenant |
| `E2E_POD_CIDR` / `E2E_SVC_CIDR` | `10.93.0.0/16` / `10.96.0.0/16` | Tenant cluster networks |
| `TEST_IMAGE` | `nginx:alpine` | HTTP backend pods |
| `PROBE_IMAGE` | `busybox:1.36` | Storage writer pods |
| `CURL_IMAGE` | `curlimages/curl:8.10.1` | Egress and reachability probes |
| `TENANT_ACCESS` | `auto` | How to reach tenant API servers: `direct`, `ssh` (through a control plane), or `auto` (direct when it answers) |
| `TENANT_KUBECTL_NODE` | first `cp` | Node that runs tenant `kubectl` in `ssh` mode |
| `EIP_PROBE_FROM` | `local` | Where an EIP is fetched from: `local` or a node name |

On air-gapped sites, point the three image keys and `INTERNET_PROBE_URL` at internal mirrors.

### Platform names

| Key | Default | Meaning |
|---|---|---|
| `KMETAL_NAMESPACE` | `kmetal-operator-system` | Namespace of the operator's Helm release |
| `KMETAL_RELEASE` | `kmetal-operator` | Helm release, or Flux HelmRelease, name |

## Validation

`check-env`, and every command that loads the file, rejects it before contacting anything if:

- `NETWORKS` lacks `mgmt`, `tenant` or `overlay`;
- a network has no `NET_IFACE` or `NET_CIDR`, or the CIDR is invalid or not a network address;
- a `NET_VLAN` is not a number;
- `NET_INTERNET` is not in `NETWORKS`;
- a provider network has no `PROV_IFACE`;
- a `NODES` row has the wrong number of columns, an unknown role, a duplicate name, or no `mgmt`
  address;
- an address is not IPv4, falls outside its network, or is used twice;
- `CP_COUNT` or `WORKER_COUNT` disagree with the table.

All errors are listed at once; the exit code is `3`.

## Template

```bash
# --- SSH -------------------------------------------------------------------------
SSH_USER=ubuntu
SSH_OPTS="-o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new"
# SSH_OPTS="$SSH_OPTS -J jump@bastion.example"   # through a jump host
# SSH_SUDO=""                                     # when SSH_USER is root

# --- Size ------------------------------------------------------------------------
# Minimum lab: 1 control plane + 2 workers. Production: 3 control planes + 3 or more workers.
CP_COUNT=3
WORKER_COUNT=2

# --- Networks carrying a node address ---------------------------------------------
NETWORKS="mgmt tenant overlay storage"
NET_IFACE=( [mgmt]=bond0.100 [tenant]=bond0.200 [overlay]=bond0.300 [storage]=bond0.400 )
NET_VLAN=(  [mgmt]=100 [tenant]=200 [overlay]=300 [storage]=400 )
NET_CIDR=(  [mgmt]=192.0.2.0/25 [tenant]=198.51.100.0/27 [overlay]=198.51.100.32/27 [storage]=203.0.113.0/24 )
NET_MTU=(   [overlay]=9000 )
NET_INTERNET=mgmt
OPTIONAL_NETWORKS="storage"

# --- Provider networks: workers only, no IP ----------------------------------------
PROVIDER_NETWORKS="provider"
PROV_IFACE=( [provider]=bond0.500 )
PROV_VLAN=(  [provider]=500 )

# --- Nodes -----------------------------------------------------------------------
# name        role    mgmt          tenant          overlay         storage
NODES="
cp-01         cp      192.0.2.10    198.51.100.10   -               203.0.113.101
cp-02         cp      192.0.2.11    198.51.100.11   -               203.0.113.102
cp-03         cp      192.0.2.12    198.51.100.12   -               203.0.113.103
worker-01     worker  192.0.2.13    198.51.100.13   198.51.100.40   203.0.113.104
worker-02     worker  192.0.2.14    198.51.100.14   198.51.100.41   203.0.113.105
"

# Only before kMetal is installed; otherwise read from the KMetal resource.
# CENTRAL_NODES="cp-01 cp-02 cp-03"

# --- Probes ----------------------------------------------------------------------
INTERNET_PROBE_URL=https://ghcr.io
INTERNET_PROBE_IP=1.1.1.1
DNS_PROBE=ghcr.io
ENCAP_TEST_PORT=6090

# --- End-to-end test -------------------------------------------------------------
E2E_SUBNET_CIDR=10.250.0.0/24
E2E_CLUSTERCLASS=""
E2E_K8S_VERSION=""
E2E_MACHINE_SIZE=small
E2E_WORKERS_A=2
E2E_WORKERS_B=1
E2E_TENANT1_WORKERS=1
E2E_TENANT2_WORKERS=2
TEST_IMAGE=nginx:alpine
PROBE_IMAGE=busybox:1.36
CURL_IMAGE=curlimages/curl:8.10.1
TENANT_ACCESS=auto
EIP_PROBE_FROM=local
```

The addresses use documentation ranges (RFC 5737); replace every one of them.
