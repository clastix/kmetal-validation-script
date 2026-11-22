# Platform checks (`kmetal.yml`)

[← Index](README.md)

```bash
ansible-playbook [-i inventory/<site>] playbooks/kmetal.yml [-e kmv_kubeconfig=admin.conf] \
    [--skip-tags e2e,e2e-tenants | --tags e2e,e2e-tenants] [--tags …] [--skip-tags …]
```

The playbook follows the kMetal *platform validation* procedure and extends it with functional
smoke tests and [end-to-end tests](e2e-test.md).

A short version of each group's section is built in:
`ansible-playbook playbooks/help.yml -e cmd=kmetal [-e group=<group>]`.

## How it works

- **Where it runs.** On the bootstrap machine (`localhost`). `kubectl` and `helm` run there
  with `KUBECONFIG` set to `kmv_kubeconfig`; the `kubernetes.core` modules use the same file.
- **Source of truth.** The live `KMetal` resource (`kubectl get km -o json`; there is one per
  cluster). Every expected value comes from its `.spec`:
  - storage class names, MetalLB ranges, central nodes, provider networks;
  - `tunnelInterface`, image tags, `multiTenancy.users`, `placement`.
- **Read-only groups** read objects with `kubectl get … -o json` and compare them with Jinja.
  Printer columns that have no documented field path (`READY`, `VERSION`, `V4`, `BOUND`,
  `SUBNET`) are read from `kubectl get` table output.
- **Smoke tests** create small objects with `kubernetes.core.k8s` in a temporary namespace
  `kmetal-validate-<run-id>`, which the run deletes at the end:
  - a LoadBalancer Service per MetalLB pool;
  - a PVC and a writer pod per storage class;
  - a VolumeSnapshot and a restore.
- **SSH probes** run only when the inventory lists nodes, with `delegate_to`: interfaces on
  network nodes, and pool addresses fetched from a control plane. An unreachable node gives a
  FAIL verdict, not an aborted run.
- **Ordering.** The two end-to-end groups, `e2e` and `e2e-tenants`, run last. They are
  skipped when an earlier platform group failed, unless `-e kmv_force_e2e=true`.
- **Cleanup.** An `always` block at the end deletes everything labelled with the run ID
  ([Resources and cleanup](resources-and-cleanup.md)).

Namespaces used: `kmetal-operator-system`, `kmetal-flux`, `kmetal-metallb`, `system-kubevirt`,
`kmetal-capi-providers`, `kmetal-image-builder`.

## Groups

### platform

| Check | How | Severity |
|---|---|---|
| Resource present | `kubectl get km` returns an item | FAIL |
| Ready | the `READY` printer column is `True`; the `VERSION` column is shown | FAIL |
| Components | every `.status.components[]` has `phase: Ready`; each other one is listed with its phase and message | FAIL; WARN when no components are reported |

### operator

| Check | How | Severity |
|---|---|---|
| Installation | `helm list` (every release state, with flags Helm 3 and Helm 4 both accept) in `kmetal-operator-system`, then in `kmetal-flux`: the first release named `kmetal-operator`, named `<namespace>-kmetal-operator` (the name Flux's helm-controller gives it), or installing the `kmetal-operator` chart. Its status must be `deployed`; the operator pods are then looked for in the release's namespace. If no release is visible, a Flux HelmRelease object in `kmetal-flux` (matched by name, `releaseName` or chart name) is accepted: GitOps install | PASS if a deployed release or a HelmRelease is found; FAIL if the release is not `deployed`, or if nothing is found |
| Version | The chart version, from Helm or from the HelmRelease history, is `1.0.1`. A pre-release of 1.0.1 (`1.0.1-rc10`) also passes, with an INFO | WARN otherwise |
| Operator pods | Every pod in the release's target namespace is Running with all containers ready, or Succeeded | FAIL |
| Flux objects | Every HelmRelease, Kustomization and OCIRepository in `kmetal-flux` has `Ready=True`; failing ones are listed with their message | FAIL |
| Cluster-wide pods | Pods anywhere neither Running-and-ready nor Completed (the run's own namespaces excluded) | WARN, with up to 15 listed |

### metallb

| Check | How | Severity |
|---|---|---|
| Ranges set | `loadBalancer.tenantControlPlanes` is not empty | FAIL. An empty `management` is a WARN: Services requesting it (the console) stay Pending |
| Fixed pool names | `tenant-cp-pool` exists (tenant control planes take their address from it); `mgmt-pool` exists when `management` is set | FAIL for `tenant-cp-pool`; WARN for `mgmt-pool` |
| Ranges served | Each address of `tenantControlPlanes` and `management` equals an address entry of an `IPAddressPool` in `kmetal-metallb` (ranges and CIDRs compared numerically) | FAIL |
| Advertised | An `L2Advertisement` exists and selects each matched pool (empty selection means all pools) | FAIL |
| Speakers | A Ready speaker pod (`app.kubernetes.io/component=speaker`) on every `spec.placement` node (control planes by default) | WARN; INFO for speakers outside the placement, and when no speaker pods are found by that label |
| Allocation | A `LoadBalancer` Service pinned to each pool (`metallb.io/address-pool`) gets an address within 120 s, inside the configured range | FAIL |
| Reachability | `http://<ip>/` against an nginx backend: first from the bootstrap machine (PASS), otherwise from the first control plane over SSH (PASS) | WARN if neither answers |

### storage

| Check | How | Severity |
|---|---|---|
| Classes named | `spec.storage.underclusterClassName` and `tenantClassName` are set | FAIL |
| Classes distinct | the two names differ: tenant quotas count by class name | WARN |
| Classes exist | each named class, including `etcdClassName` when set, exists; provisioner, binding mode and expansion are shown | FAIL |
| Expansion | `allowVolumeExpansion: true` on the platform and tenant classes | WARN |
| Snapshot class | Required for `underclusterClassName` only; the tenant and etcd classes need none. The class serving it is the one named in `clusterClass.values.dataVolume.volumeSnapshotClass` when that exists on the platform class's driver, else the driver's default VolumeSnapshotClass, else any class of that driver | FAIL when none serves the platform class: golden images cannot be snapshotted and no tenant machine boots |
| Snapshot class named in the spec | `clusterClass.values.dataVolume.volumeSnapshotClass`, when set, exists and uses the platform class's driver | FAIL, naming the class that does serve the platform class; the snapshot test still runs with that one |
| CDI profile | the `underclusterClassName` StorageProfile has a non-empty `status.snapshotClass`; its `cloneStrategy` is shown. When it is empty although a class serves the platform class, the message explains it: CDI watches VolumeSnapshotClasses only if the snapshot CRDs existed when it started | FAIL when empty; WARN when it names a class other than the one serving the platform class |
| Write/read per class | 1 Gi PVC plus a pod that writes, syncs and reads a file; it must finish within 300 s | FAIL, with pod logs, events and PVC events |
| Snapshot | a `VolumeSnapshot` of the platform-class PVC, with the class serving it, is `readyToUse` within 300 s | FAIL |
| Restore | a PVC restored from that snapshot must contain the data and **accept writes** | FAIL when the StorageProfile clones by `snapshot` (tenant root disks would fail); WARN otherwise |

Each test pod runs where the real consumer of its class runs:
- **platform and tenant classes:** nodes with `node-role.kubernetes.io/compute`, through node
  affinity on the key, whatever its value;
- **etcd class:** `spec.placement.nodeSelector` and `tolerations`, defaulting to the control
  planes, which is where Kamaji's etcd runs. A node-local class therefore binds where it is
  provisioned.

### nodes

Checks the node labels and the Kube-OVN central nodes described in
[Topology model](topology-model.md#node-labels), with the kMetal 1.0.1 rules.

| Check | How | Severity |
|---|---|---|
| MetalLB exclusion label | no control plane carries `node.kubernetes.io/exclude-from-external-load-balancers`. kubeadm sets it; the 1.0.1 operator removes it | FAIL, with the `kubectl label … -` fix |
| Compute nodes | at least one node has `node-role.kubernetes.io/compute` | FAIL |
| virt-handler | a Ready `virt-handler` pod (`system-kubevirt`) on every compute node | FAIL |
| Network nodes | at least one node has `node-role.kubernetes.io/network` | FAIL |
| Network label value | the value is empty; `=true` does not match Kube-OVN's DaemonSets | FAIL, with the `--overwrite …=` fix |
| Network label on control plane | a control plane carries `node-role.kubernetes.io/network` | WARN |
| Gateway label | every network node has `ovn.kubernetes.io/external-gw=true` (set by the operator) | FAIL |
| kube-ovn-cni | a Ready `app=kube-ovn-cni` pod on every network node | FAIL |
| Tunnel interface | with an inventory: `ip link show dev <tunnelInterface>` succeeds on every network node, over SSH | FAIL |
| Networking agent label | every network node carries the labels of the kmetal-networking agent DaemonSet's `nodeSelector` (found by `app.kubernetes.io/name=kmetal-networking`, `component=agent`), today `kmetal.io/ovn=true`; `kmetal.io/ovn=true` is assumed when the DaemonSet is not found | FAIL, with the `kubectl label` fix: tenant workers never join without the agent |
| Networking agent | a Ready agent pod on every network node; the DaemonSet is scheduled on at least one node | FAIL |
| `kmetal.io/ovn` on a control plane | | WARN |
| Central nodes listed | `centralNodes` is not empty and each entry is a node | FAIL |
| Central label | each central node has `kube-ovn/role=master` (set by the operator) | FAIL |
| Worker as central | a central node that is not a control plane | WARN |
| Unused control planes | three or more control planes exist but fewer than three are central | WARN |
| Raft size | fewer than three central nodes, or an even number | WARN; PASS shows how many losses Raft tolerates |
| Stray master label | `kube-ovn/role=master` on a node outside `centralNodes` | WARN |

### providers

Validates every `spec.networking.providerNetworks[]`, separating the default networks declared in
the inventory from the additional ones the platform manages. The rules and their severities are
in [Topology model → Provider networks](topology-model.md#provider-networks).

How it is performed:
1. **Classify.** Compare the KMetal interfaces with the inventory's `kmv_provider_networks`;
   report each network as *default* or *additional* (and whether the networking daemon creates
   its interface).
2. **Validate subnets.** Check `defaultProviderSubnet`, the presence of a subnet named
   `external`, each subnet's CIDR, gateway and `excludeIPs`, and overlaps against pod, service,
   join, node and the other provider networks, using the project's IP filters.
3. **List target nodes.** Compute the network nodes (`node-role.kubernetes.io/network`) that
   are not in `excludeNodes`.
4. **Inspect each target node over SSH** (only with an inventory). Run
   `ip -d -j link show dev <if>` and `ip -j -4 addr show dev <if>`, then check: present,
   carrier, no IPv4. The report shows VLAN ID and OVS master, and flags double tagging and a VLAN
   mismatch with the inventory.
5. **Reverse diff.** Report inventory provider networks absent from the KMetal resource.

### tenancy

| Check | How | Severity |
|---|---|---|
| Subjects set | `spec.multiTenancy.users` is not empty | WARN: tenancy installed but inactive |
| Capsule | a `CapsuleConfiguration` exists | FAIL |
| Admission | `kubectl create namespace kmetal-validate-probe-<id>` impersonating a member of the first subject. For a `system:serviceaccounts:<ns>` group, the user is a ServiceAccount of that namespace, with the group added. The namespace is deleted right after | PASS when rejected, since the probe user owns no Tenant. FAIL when the namespace is created without the `capsule.clastix.io/tenant` label: Capsule does not know the subject |

### capi

| Check | How | Severity |
|---|---|---|
| Providers | one each of core (`cluster-api`), bootstrap (`kubeadm`), infrastructure (`kubevirt`) and control plane (`kamaji`) in `kmetal-capi-providers`, each `Ready=True`; installed version shown | FAIL |
| ClusterClasses | at least one in `kmetal-capi-providers`; the one the end-to-end tests will use is shown | FAIL; also when `kmv_e2e_clusterclass` names a missing class |

### kubevirt

| Check | How | Severity |
|---|---|---|
| KubeVirt | `status.phase: Deployed` in `system-kubevirt` | FAIL |
| CDI | `status.phase: Deployed` | WARN |

### crds

| Check | How | Severity |
|---|---|---|
| CRDs | `clusters.cluster.x-k8s.io`, `kamajicontrolplanes.controlplane.cluster.x-k8s.io`, `virtualmachines.kubevirt.io`, `vpcclaims`, `subnetclaims`, `eipclaims` and `providernetworks` (`network.kmetal.io`), `tenants.capsule.clastix.io`, `volumesnapshots.snapshot.storage.k8s.io`, `osartifacts.build.kairos.io` | FAIL |
| Image tags | `spec.clusterClass.values.osArtifact.tags` is not empty | FAIL: no OS image to boot tenant workers |
| Golden images | for each tag, an `OSArtifact` in `kmetal-image-builder` whose name contains the version (`v1.36.4` matches `…-v1364-…` and `…-v1-36-4-…`) is `Ready`, and its `<name>-golden` PVC is `Bound` | FAIL: that version cannot be offered to tenants |

### e2e and e2e-tenants

The two end-to-end scenarios: one tenant with two environments, and two tenants for
multi-tenancy segregation. See [End-to-end tests](e2e-test.md).
