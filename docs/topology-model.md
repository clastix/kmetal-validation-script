# Topology model

[← Index](README.md)

This page describes the under cluster layout that the checks expect, following the kMetal 1.0.0
documentation. Each rule names the check that enforces it.

## Node roles

| Role | Identified by | Hosts |
|---|---|---|
| Control plane | `cp` in `setup.env`; `node-role.kubernetes.io/control-plane` in the cluster | The under cluster control plane, platform controllers, ovn-central (the Kube-OVN central nodes), Kamaji tenant control planes and their etcd by default |
| Compute | `node-role.kubernetes.io/compute` | Tenant VMs (`virt-handler`), image-builder VMs |
| Network | `kmetal.io/ovn` | Kube-OVN's per-node components (`kube-ovn-cni`, `ovs-ovn`), the overlay tunnel, the OVN gateways and provider bridges |

On small sites, workers are both compute and network nodes.

**Size** (`undercluster` → `topology`):
- Fewer than 1 control plane or 2 workers is a FAIL.
- Fewer than 3 control planes, or an even number, is a WARN.

## Networks

| Network | Control plane | Worker | Address | Internet |
|---|---|---|---|---|
| `mgmt` | required | required | yes | **the only network that reaches it** |
| `tenant` | required | required | yes | no |
| `overlay` | not needed (INFO when absent) | required | yes | no |
| provider (one or more) | absent (INFO if present) | required on network nodes | **none** | only through OVN, for tenants |
| optional (e.g. `storage`) | as declared | as declared | yes | no |

Rules and the checks that enforce them:

| Rule | Check |
|---|---|
| Each interface exists, is up, and carries the declared VLAN ID, MTU and address | `undercluster` → `interfaces` |
| A provider interface carries no IPv4 address | `undercluster` → `interfaces`; `kmetal` → `providers` |
| Node networks do not overlap each other | `undercluster` → `addressing` |
| Node networks do not overlap `kubeOVN.podCIDR`, `serviceCIDR`, `100.64.0.0/16` (Kube-OVN join) or any provider subnet | `undercluster` → `addressing`; `kmetal` → `providers` |
| Every node reaches every other node on each shared network, without loss | `undercluster` → `mesh` |
| A jumbo MTU passes end to end | `undercluster` → `mesh` |
| Only `mgmt` reaches the internet | `undercluster` → `internet` |
| Geneve/VXLAN encapsulation works between overlay nodes | `undercluster` → `encap` |
| Interfaces of node networks persist in netplan | `undercluster` → `netplan` |

### Why control planes need no overlay

Kube-OVN's tunnel and per-node components run only where `kmetal.io/ovn` is set, and that label
belongs on network nodes. ovn-central, which runs on the control planes, uses the node's own
address for OVSDB Raft, not the tunnel. A control plane without an overlay interface is
therefore the expected layout and reported as INFO.

## Node labels

Operator 1.0.0 sets **no** node label: the administrator applies all of them before installing.
Checked by `kmetal` → `nodes`.

| Label | Where | If missing or misplaced |
|---|---|---|
| `node-role.kubernetes.io/compute` | At least one node, normally the workers | FAIL: no tenant machine or image-builder VM can start, while the install still reports healthy |
| `kmetal.io/ovn` (any value) | Network nodes only | FAIL if no node has it. WARN on a control plane |
| `ovn.kubernetes.io/external-gw=true` | Every network node | FAIL: VPCs with external access have no gateway |
| `kube-ovn/role=master` | Every node in `spec.networking.kubeOVN.centralNodes` | FAIL on a central node without it. WARN on a node that has it but is not central |
| `node.kubernetes.io/exclude-from-external-load-balancers` | **No control plane** (kubeadm sets it by default) | FAIL: MetalLB speakers must announce from the control planes, and this label stops them. Remove it with `kubectl label node <n> node.kubernetes.io/exclude-from-external-load-balancers-` |

`node-role.kubernetes.io/network` is not used by 1.0.0 and is reported as INFO.

## Kube-OVN central nodes

`spec.networking.kubeOVN.centralNodes` lists the nodes running ovn-central, whose databases
form an OVSDB Raft cluster. Raft needs a majority: three members tolerate the loss of one.

| Situation | Result |
|---|---|
| The three control planes, labelled `kube-ovn/role=master` | PASS |
| A worker in the list | WARN: ovn-central belongs on the control planes |
| Three or more control planes exist, but fewer than three are listed | WARN, naming the unused control planes |
| Fewer than three central nodes, or an even number | WARN: fill the list to three, with control planes, or workers when there are fewer than three control planes |
| A listed name that is not a node | FAIL |

## Provider networks

A provider network maps an interface on the network nodes to an OVN bridge. Its subnets provide:
- the VPC router-port address for tenants with external access (one address per tenant);
- the EIPs for published services (one address per service).

There are two kinds:

| Kind | Declared in | Checked by |
|---|---|---|
| **Default** | `setup.env` `PROVIDER_NETWORKS`, and the `KMetal` resource | `undercluster` (interface, VLAN, no IP); `kmetal` → `providers` (subnets, interface on each node) |
| **Additional** | The `KMetal` resource only; created and managed by the platform | `kmetal` → `providers` |

`kmetal` → `providers` compares the two lists by interface name. A network found only in
`setup.env` is a WARN, because the platform does not use it.

Rules for every provider network:

| Rule | Result if broken |
|---|---|
| `defaultProviderSubnet` names an existing subnet | FAIL |
| `excludeNodes` entries are nodes | WARN |
| At least one network node remains after `excludeNodes` | FAIL |
| Subnet CIDR is canonical, gateway inside it | FAIL |
| `excludeIPs` inside the CIDR | WARN |
| No overlap with pod, service, join, node or other provider networks | FAIL |
| Interface present on each target node, with carrier and no IPv4 | FAIL: list the node in `excludeNodes` if it has no such NIC |
| Kernel VLAN device combined with a subnet `vlanID` other than 0 | WARN: frames would be tagged twice |
| Default network's VLAN equals `PROV_VLAN` | FAIL |

Interfaces of provider networks are often absent from netplan once kMetal is installed, because
the platform manages them. `undercluster` → `netplan` reports this as INFO, not WARN.

## Load balancer ranges

`spec.networking.loadBalancer` defines two MetalLB ranges:

| Range | Network | Serves |
|---|---|---|
| `tenantControlPlanes` | `tenant` | Kamaji tenant API servers |
| `management` | `mgmt` | The console and platform services |

Each range must lie inside its network and contain no node address (`undercluster` →
`addressing`). It must also be served by an `IPAddressPool` and an `L2Advertisement`, and hand
out working addresses (`kmetal` → `metallb`).

The MetalLB speakers announce these addresses from the **control planes**:
- No control plane may carry `node.kubernetes.io/exclude-from-external-load-balancers` (FAIL in
  `kmetal` → `nodes`, and in `undercluster` → `topology` when a kubeconfig works).
- Each control plane should run a Ready speaker (WARN in `kmetal` → `metallb`).
