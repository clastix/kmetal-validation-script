# Topology model

[← Index](README.md)

This page describes the under cluster layout that the checks expect, following the kMetal 1.0.1
documentation. Each rule names the check that enforces it.

## Node roles

| Role | Identified by | Hosts |
|---|---|---|
| Control plane | inventory group `control_plane`; `node-role.kubernetes.io/control-plane` in the cluster | The under cluster control plane, platform controllers, ovn-central (the Kube-OVN central nodes), the MetalLB speakers (`spec.placement`), Kamaji tenant control planes and their etcd by default |
| Compute | `node-role.kubernetes.io/compute` | Tenant VMs (`virt-handler`), image-builder VMs |
| Network | `node-role.kubernetes.io/network` with an **empty** value | Kube-OVN's per-node components (`kube-ovn-cni`, `ovs-ovn`, `kube-ovn-pinger`), the overlay tunnel, the OVN gateways and provider bridges |

On small sites, workers are both compute and network nodes.

**Size** (`undercluster.yml` → `topology`):
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

Kube-OVN's tunnel and per-node components run only on network nodes
(`node-role.kubernetes.io/network`), and that label belongs on workers. ovn-central, which runs
on the control planes, uses the node's own address for OVSDB Raft, not the tunnel. A control
plane without an overlay interface is therefore the expected layout and reported as INFO. The
kMetal documentation also asks for the tunnel interface on every central node; the INFO message
says so when the control plane is a central node.

## Node labels

kMetal 1.0.1 adds a **node labelling controller** to the operator. The administrator still
applies the role labels; the operator derives the others. Checked by `kmetal` → `nodes`.

| Label | Set by | Where | If missing or misplaced |
|---|---|---|---|
| `node-role.kubernetes.io/compute` | administrator | At least one node, normally the workers | FAIL: no tenant machine or image-builder VM can start, while the install still reports healthy |
| `node-role.kubernetes.io/network=` (empty value) | administrator | Network nodes only | FAIL if no node has it, or if its value is not empty (`=true` does not match the DaemonSets). WARN on a control plane |
| `ovn.kubernetes.io/external-gw=true` | operator, on every network node | Every network node | FAIL: the node labelling controller did not apply it; VPCs with external access have no gateway |
| `kube-ovn/role=master` | operator, from `spec.networking.kubeOVN.centralNodes` | Every central node | FAIL on a central node without it. WARN on a node that has it but is not central |
| `node.kubernetes.io/exclude-from-external-load-balancers` | kubeadm sets it; the operator **removes** it from control planes | **No control plane** | FAIL: MetalLB speakers must announce from the control planes, and this label stops them. The operator should have removed it |
| `kmetal.io/ovn` | (before 1.0.1) | Nowhere | No longer read. INFO on a network node ("can be removed"). WARN on a node that has it but lacks the network label: it was not relabelled before the upgrade, and Kube-OVN no longer runs there |

Before upgrading to 1.0.1, every node carrying the overlay must be labelled
`node-role.kubernetes.io/network=`; otherwise the Kube-OVN DaemonSets leave those nodes.

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
| **Default** | The inventory's `kmv_provider_networks`, and the `KMetal` resource | `undercluster` (interface, VLAN, no IP); `kmetal` → `providers` (subnets, interface on each node) |
| **Additional** | The `KMetal` resource only; created and managed by the platform | `kmetal` → `providers` |

`kmetal` → `providers` compares the two lists by interface name. A network found only in the
inventory is a WARN, because the platform does not use it.

Rules for every provider network:

| Rule | Result if broken |
|---|---|
| `defaultProviderSubnet` names an existing subnet | FAIL |
| A subnet is literally named `external` (VPC external access needs it) | FAIL |
| `excludeNodes` entries are nodes | WARN |
| At least one network node remains after `excludeNodes` | FAIL |
| Subnet CIDR is canonical, gateway inside it | FAIL |
| `excludeIPs` inside the CIDR (single addresses or `first..last` ranges) | WARN |
| No overlap with pod, service, join, node or other provider networks | FAIL |
| Interface present on each target node, with carrier and no IPv4 | FAIL: list the node in `excludeNodes` if it has no such NIC |
| Kernel VLAN device combined with a subnet `vlanID` other than 0 | WARN: frames would be tagged twice and dropped |
| Default network's VLAN equals the inventory's `vlan` | FAIL |

With `autoCreateVLANSubinterface: true`, the kMetal networking daemon creates the interface on
each participating node. `undercluster` → `interfaces` then reports a missing interface as INFO.

Interfaces of provider networks are often absent from netplan once kMetal is installed, because
the platform manages them. `undercluster` → `netplan` reports this as INFO, not WARN.

## Load balancer ranges

`spec.networking.loadBalancer` defines two MetalLB ranges. The operator creates a pool with a
fixed name for each:

| Range | Pool | Network | Serves |
|---|---|---|---|
| `tenantControlPlanes` | `tenant-cp-pool` | `tenant` | Kamaji tenant API servers |
| `management` (optional) | `mgmt-pool` | `mgmt` | The console and platform services |

Each range must lie inside its network and contain no node address (`undercluster` →
`addressing`). It must also be served by an `IPAddressPool` and an `L2Advertisement`, and hand
out working addresses (`kmetal` → `metallb`). Without a `management` range, Services requesting
it, the console included, stay Pending (WARN).

In kMetal 1.0.1 the MetalLB speakers run on the `spec.placement` nodes, the **control planes**
by default:
- No control plane may carry `node.kubernetes.io/exclude-from-external-load-balancers` (FAIL in
  `kmetal` → `nodes`, and in `undercluster` → `topology` when a kubeconfig works).
- Each placement node should run a Ready speaker (WARN in `kmetal` → `metallb`).
- The placement nodes must be attached to the network of every pool: the control planes need
  `tenant` and `mgmt` addresses (`undercluster` → `interfaces`).
