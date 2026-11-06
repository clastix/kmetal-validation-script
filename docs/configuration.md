# Configuration: the inventory

[← Index](README.md)

The **inventory** describes the under cluster as the customer intends it: nodes, roles,
networks, VLANs and addresses. `undercluster.yml` compares the real nodes against it.
`kmetal.yml` uses it optionally, for the checks that need SSH.

An inventory is a directory, selected with `-i`:

```
inventory/<site>/
  hosts.yml                      nodes, grouped by role, with their addresses
  group_vars/all.yml             networks, provider networks, probes, end-to-end settings
  group_vars/kmetal_nodes.yml    how to reach the nodes (ansible_host from the mgmt address)
```

`inventory/example/` is a complete example to copy. Every variable has a default in
`roles/common/defaults/main.yml`; the inventory overrides it, and `-e name=value` overrides
both. See the [Ansible primer](ansible-primer.md#variables-and-their-precedence).

## Nodes: `hosts.yml`

```yaml
all:
  vars:
    ansible_user: ubuntu                 # SSH user; needs passwordless sudo
  children:
    kmetal_nodes:
      children:
        control_plane:
          hosts:
            cp-01:
              kmv_addresses: {mgmt: 192.0.2.10, tenant: 198.51.100.10}
        workers:
          hosts:
            worker-01:
              kmv_addresses: {mgmt: 192.0.2.13, tenant: 198.51.100.13, overlay: 198.51.100.40}
```

- Every node is in **exactly one** of `control_plane` and `workers`, both inside
  `kmetal_nodes`. The group is the node's role.
- `kmv_addresses` maps a network name of `kmv_networks` to the node's address on it.
  - An address may carry a prefix (`10.0.0.5/24`). Without one, the prefix of the network's
    `cidr` is expected on the interface.
  - A network missing from `kmv_addresses` means the node is not on it (e.g. no overlay on a
    control plane).
  - `mgmt` is required on every node: it is the SSH target.
- The host name is the node name, compared with the Kubernetes node names.
- The number of control planes and workers is the size of each group.

### SSH

| Variable | Default | Meaning |
|---|---|---|
| `ansible_user` | your local user | User on every node; it connects to `ansible_host` |
| `ansible_host` | set from `kmv_addresses.mgmt` in `group_vars/kmetal_nodes.yml` | Address Ansible connects to |
| `ansible_ssh_common_args` | none | Extra `ssh` options, e.g. `-J user@bastion` for a jump host |
| `ansible_ssh_private_key_file` | your SSH agent / default key | Key to use |

`ansible.cfg` already sets `BatchMode=yes`, `ConnectTimeout=5` and
`StrictHostKeyChecking=accept-new`. Root is obtained with `sudo -n` (`become`); with
`ansible_user: root` no sudo is needed.

## Networks carrying a node address

```yaml
kmv_networks:
  mgmt:    {interface: bond0.100, vlan: 100, cidr: 192.0.2.0/25}
  tenant:  {interface: bond0.200, vlan: 200, cidr: 198.51.100.0/27}
  overlay: {interface: bond0.300, vlan: 300, cidr: 198.51.100.32/27, mtu: 9000}
```

| Variable | Meaning |
|---|---|
| `kmv_networks` | One entry per network. `mgmt`, `tenant` and `overlay` are mandatory; others (e.g. `storage`) are allowed. The order is the order of the checks and of the node table |
| `.interface` | Interface name on the nodes: a VLAN sub-interface (`bond0.104`), a bond or a NIC |
| `.vlan` | VLAN ID the interface must carry. Absent or `0`: the interface is not a VLAN device, and the ID is not checked |
| `.cidr` | The network, as a canonical CIDR (network address, not a host address) |
| `.mtu` | Optional expected MTU. Above 1500, a do-not-fragment ping checks it end to end |
| `kmv_internet_network` | The only network allowed to reach the internet (default `mgmt`) |
| `kmv_optional_networks` | Networks whose absence is a WARN or INFO, not a FAIL (e.g. `[storage]`) |

The network names have a meaning to the checks:

| Name | Used for |
|---|---|
| `mgmt` | SSH target, internet egress, the `loadBalancer.management` MetalLB range |
| `tenant` | The `loadBalancer.tenantControlPlanes` MetalLB range |
| `overlay` | The Kube-OVN tunnel; required on workers, not needed on control planes |

## Provider networks

Provider networks carry tenant egress and EIPs. They exist on **workers only** and their
interface carries **no IP address**. Declare the default ones here; additional ones created by
the platform are found in the `KMetal` resource (see
[Topology model](topology-model.md#provider-networks)).

```yaml
kmv_provider_networks:
  provider: {interface: bond0.500, vlan: 500}
```

| Variable | Meaning |
|---|---|
| `kmv_provider_networks` | One entry per provider network, keyed by name |
| `.interface` | Interface name on the workers |
| `.vlan` | Expected VLAN ID; absent or `0` when not a VLAN device |

## Kube-OVN central nodes

| Variable | Meaning |
|---|---|
| `kmv_central_nodes` | List of node names. Read from `spec.networking.kubeOVN.centralNodes` when a kubeconfig works; set it only to describe a cluster where kMetal is not yet installed. `undercluster.yml` uses it for context messages |

## Probes

| Variable | Default | Meaning |
|---|---|---|
| `kmv_internet_probe_url` | `https://ghcr.io` | URL fetched to prove internet egress (nodes and tenant pods) |
| `kmv_internet_probe_ip` | `1.1.1.1` | Address pinged per network |
| `kmv_dns_probe` | `ghcr.io` | Name resolved on every node |
| `kmv_encap_test_port` | `6090` | UDP port of the temporary test tunnel (Geneve); VXLAN uses the next port. Kept away from Kube-OVN's own `6081` |

## End-to-end tests

| Variable | Default | Meaning |
|---|---|---|
| `kmv_e2e_subnet_cidr` | `10.250.0.0/24` | Subnet given to **every** test environment, in both scenarios; the overlap is intentional |
| `kmv_e2e_clusterclass` | auto | ClusterClass to use. Auto: `kubevirt-standard`, then `kubevirt-expert`, then `kubevirt-kubeadm`, then the first one found |
| `kmv_e2e_k8s_version` | auto | Kubernetes version; must be one of `osArtifact.tags`. Auto: the first tag |
| `kmv_e2e_machine_size` | `small` | `machineSize` variable |
| `kmv_e2e_datastore` | `default` | `controlPlane.dataStoreName` variable |
| `kmv_e2e_workers_a` / `kmv_e2e_workers_b` | `2` / `1` | Workers in the two clusters of the `e2e` scenario (one tenant, two environments) |
| `kmv_e2e_tenant1_workers` / `kmv_e2e_tenant2_workers` | `1` / `2` | Workers in the two clusters of the `e2e-tenants` scenario (two tenants). Different counts let the isolation probe find an address used by only one tenant |
| `kmv_e2e_pod_cidr` / `kmv_e2e_svc_cidr` | `10.93.0.0/16` / `10.96.0.0/16` | Tenant cluster networks |
| `kmv_test_image` | `nginx:alpine` | HTTP backend pods |
| `kmv_probe_image` | `busybox:1.36` | Storage writer pods |
| `kmv_curl_image` | `curlimages/curl:8.10.1` | Egress and reachability probes |
| `kmv_tenant_access` | `auto` | How to reach tenant API servers: `direct`, `ssh` (through a control plane), or `auto` (direct when it answers) |
| `kmv_tenant_kubectl_node` | first control plane | Node that runs tenant `kubectl` in `ssh` mode |
| `kmv_eip_probe_from` | `local` | Where an EIP is fetched from: `local` or a node name |

On air-gapped sites, point the three image variables and `kmv_internet_probe_url` at internal
mirrors.

## Run options

Usually given with `-e` on the command line ([Getting started](getting-started.md#options)).

| Variable | Default | Meaning |
|---|---|---|
| `kmv_kubeconfig` | `$KUBECONFIG`, else `~/.kube/config` | Under cluster kubeconfig |
| `kmv_keep` | `false` | Keep the test resources |
| `kmv_force_e2e` | `false` | Run the end-to-end groups after earlier failures |
| `kmv_timeout_cluster` | `30m` | Wait for tenant clusters |
| `kmv_run_id` | random | Run ID; required by `cleanup.yml` |

## Platform names

| Variable | Default | Meaning |
|---|---|---|
| `kmv_target_kmetal` | `1.0.1` | kMetal release the rules follow |
| `kmv_operator_namespace` | `kmetal-operator-system` | Namespace of the operator's Helm release |
| `kmv_operator_release` | `kmetal-operator` | Helm release, or Flux HelmRelease, name |
| `kmv_pool_names` | `tenant-cp-pool`, `mgmt-pool` | MetalLB pool names the operator creates |
| `kmv_ns_flux`, `kmv_ns_metallb`, `kmv_ns_kubevirt`, `kmv_ns_capi`, `kmv_ns_images` | `kmetal-flux`, `kmetal-metallb`, `system-kubevirt`, `kmetal-capi-providers`, `kmetal-image-builder` | Platform namespaces |

## Validation

`check-env.yml`, and every playbook that uses the inventory, reject it before contacting
anything if:

- `kmv_networks` is empty or lacks `mgmt`, `tenant` or `overlay`;
- a network has no `interface` or `cidr`, or the CIDR is invalid or not a network address;
- a `vlan` is not a number;
- `kmv_internet_network` is not in `kmv_networks`;
- a provider network has no `interface`;
- there is no host in `kmetal_nodes`;
- a node is in both or neither of `control_plane` and `workers`;
- a `kmv_addresses` key is not a network of `kmv_networks`;
- an address is not IPv4, falls outside its network, or is used twice;
- a node has no `mgmt` address;
- `kmv_central_nodes` names a node that is not in the inventory.

All errors are listed at once and the playbook fails (exit code `2`). Overlapping networks are
reported by the `addressing` check group of `undercluster.yml`.

## Template

`hosts.yml`:

```yaml
all:
  vars:
    ansible_user: ubuntu
    # ansible_ssh_common_args: "-J jump@bastion.example"   # through a jump host
  children:
    kmetal_nodes:
      children:
        control_plane:
          hosts:
            cp-01: {kmv_addresses: {mgmt: 192.0.2.10, tenant: 198.51.100.10, storage: 203.0.113.101}}
            cp-02: {kmv_addresses: {mgmt: 192.0.2.11, tenant: 198.51.100.11, storage: 203.0.113.102}}
            cp-03: {kmv_addresses: {mgmt: 192.0.2.12, tenant: 198.51.100.12, storage: 203.0.113.103}}
        workers:
          hosts:
            worker-01: {kmv_addresses: {mgmt: 192.0.2.13, tenant: 198.51.100.13, overlay: 198.51.100.40, storage: 203.0.113.104}}
            worker-02: {kmv_addresses: {mgmt: 192.0.2.14, tenant: 198.51.100.14, overlay: 198.51.100.41, storage: 203.0.113.105}}
```

`group_vars/kmetal_nodes.yml`:

```yaml
ansible_host: "{{ kmv_addresses.mgmt | split('/') | first }}"
```

`group_vars/all.yml`:

```yaml
kmv_networks:
  mgmt:    {interface: bond0.100, vlan: 100, cidr: 192.0.2.0/25}
  tenant:  {interface: bond0.200, vlan: 200, cidr: 198.51.100.0/27}
  overlay: {interface: bond0.300, vlan: 300, cidr: 198.51.100.32/27, mtu: 9000}
  storage: {interface: bond0.400, vlan: 400, cidr: 203.0.113.0/24}
kmv_internet_network: mgmt
kmv_optional_networks: [storage]

kmv_provider_networks:
  provider: {interface: bond0.500, vlan: 500}

# Only before kMetal is installed; otherwise read from the KMetal resource.
# kmv_central_nodes: [cp-01, cp-02, cp-03]

kmv_internet_probe_url: https://ghcr.io
kmv_internet_probe_ip: 1.1.1.1
kmv_dns_probe: ghcr.io

kmv_e2e_subnet_cidr: 10.250.0.0/24
kmv_e2e_clusterclass: ""
kmv_e2e_k8s_version: ""
kmv_test_image: nginx:alpine
kmv_probe_image: busybox:1.36
kmv_curl_image: curlimages/curl:8.10.1
kmv_tenant_access: auto
kmv_eip_probe_from: local
```

The addresses use documentation ranges (RFC 5737); replace every one of them.
