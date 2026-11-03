# Platform checks (`kmetal`)

[← Index](README.md)

```bash
./kmetal-validate [-e setup.env] --kubeconfig admin.conf kmetal [--no-e2e | --e2e-only] [--only …] [--skip …]
```

The command follows the kMetal *platform validation* procedure and extends it with functional
smoke tests and [end-to-end tests](e2e-test.md).

A short version of each group's section is built into the script:
`./kmetal-validate kmetal help [group]`.

## How it works

- **Source of truth.** The live `KMetal` resource (`kubectl get km -o json`; there is one per
  cluster). Every expected value comes from its `.spec`:
  - storage class names, MetalLB ranges, central nodes, provider networks;
  - `tunnelInterface`, image tags, `multiTenancy.users`, `placement`.
- **Read-only groups** query the API and compare.
- **Smoke tests** create small objects in a temporary namespace `kmetal-validate-<run-id>`,
  which the run deletes on exit:
  - a LoadBalancer Service per MetalLB pool;
  - a PVC and a writer pod per storage class;
  - a VolumeSnapshot and a restore.
- **SSH probes** run only when `setup.env` is loaded: interfaces on network nodes, and pool
  addresses fetched from a control plane.
- **Ordering.** The two end-to-end groups, `e2e` and `e2e-tenants`, run last. They are
  skipped when an earlier group failed, unless `--force-e2e` is given.

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
| Installation | Helm release `kmetal-operator` in `kmetal-operator-system` with status `deployed`. If it is absent, a Flux HelmRelease in `kmetal-flux` (matched by name, `releaseName` or chart name) is accepted: GitOps install | PASS if either is found; FAIL if neither is |
| Version | The chart version, from Helm or from the HelmRelease history, is `1.0.x` | WARN otherwise |
| Operator pods | Every pod in the release's target namespace is Running with all containers ready, or Succeeded | FAIL |
| Flux objects | Every HelmRelease, Kustomization and OCIRepository in `kmetal-flux` has `Ready=True`; failing ones are listed with their message | FAIL |
| Cluster-wide pods | Pods anywhere neither Running-and-ready nor Completed (the tool's own namespaces excluded) | WARN, with up to 15 listed |

### metallb

| Check | How | Severity |
|---|---|---|
| Ranges served | Each address of `loadBalancer.tenantControlPlanes` and `loadBalancer.management` equals an address entry of an `IPAddressPool` in `kmetal-metallb` (ranges and CIDRs compared numerically) | FAIL |
| Ranges set | Neither list is empty | FAIL |
| Advertised | An `L2Advertisement` exists and selects each matched pool (empty selection means all pools) | FAIL |
| Speakers | A Ready speaker pod (`app.kubernetes.io/component=speaker` in `kmetal-metallb`) on every control plane | WARN; INFO when no speaker pods are found by that label |
| Allocation | A `LoadBalancer` Service pinned to each pool (`metallb.io/address-pool`) gets an address within 120 s, inside the configured range | FAIL |
| Reachability | `curl http://<ip>/` against an nginx backend: first from the bootstrap machine (PASS), otherwise from the first control plane over SSH (PASS) | WARN if neither answers |

### storage

| Check | How | Severity |
|---|---|---|
| Classes named | `spec.storage.underclusterClassName` and `tenantClassName` are set | FAIL |
| Classes distinct | the two names differ: tenant quotas count by class name | WARN |
| Classes exist | each named class, including `etcdClassName` when set, exists; provisioner, binding mode and expansion are shown | FAIL |
| Expansion | `allowVolumeExpansion: true` on the platform and tenant classes | WARN |
| Snapshot class | `clusterClass.values.dataVolume.volumeSnapshotClass` exists, and its driver equals the platform class's provisioner. When unset, a class of that driver is searched for (default class first) | FAIL: golden images cannot be snapshotted and no tenant machine boots |
| CDI profile | the platform class's StorageProfile has a non-empty `status.snapshotClass`; its `cloneStrategy` is shown | FAIL |
| Write/read per class | 1 Gi PVC plus a pod that writes, syncs and reads a file; it must finish within 300 s | FAIL, with pod logs, events and PVC events |
| Snapshot | a `VolumeSnapshot` of the platform-class PVC is `readyToUse` within 300 s | FAIL |
| Restore | a PVC restored from that snapshot must contain the data and **accept writes** | FAIL when the StorageProfile clones by `snapshot` (tenant root disks would fail); WARN otherwise |

Each test pod runs where the real consumer of its class runs:
- **platform and tenant classes:** nodes with `node-role.kubernetes.io/compute`, through node
  affinity on the key, whatever its value;
- **etcd class:** `spec.placement.nodeSelector` and `tolerations`, defaulting to the control
  planes, which is where Kamaji's etcd runs. A node-local class therefore binds where it is
  provisioned.

### nodes

Checks the node labels and the Kube-OVN central nodes described in
[Topology model](topology-model.md#node-labels).

| Check | How | Severity |
|---|---|---|
| MetalLB exclusion label | no control plane carries `node.kubernetes.io/exclude-from-external-load-balancers` (kubeadm sets it); the MetalLB speakers must announce from the control planes | FAIL, with the `kubectl label … -` fix |
| Compute nodes | at least one node has `node-role.kubernetes.io/compute` | FAIL |
| virt-handler | a Ready `virt-handler` pod (`system-kubevirt`) on every compute node | FAIL |
| Network nodes | at least one node has `kmetal.io/ovn` | FAIL |
| Label on control plane | a control plane carries `kmetal.io/ovn` | WARN, with the `kubectl label … kmetal.io/ovn-` fix |
| Gateway label | every network node has `ovn.kubernetes.io/external-gw=true` | FAIL |
| kube-ovn-cni | a Ready `app=kube-ovn-cni` pod on every network node | FAIL |
| Tunnel interface | with `setup.env`: `ip link show dev <tunnelInterface>` succeeds on every network node | FAIL |
| Central nodes listed | `centralNodes` is not empty and each entry is a node | FAIL |
| Central label | each central node has `kube-ovn/role=master` | FAIL |
| Worker as central | a central node that is not a control plane | WARN |
| Unused control planes | three or more control planes exist but fewer than three are central | WARN |
| Raft size | fewer than three central nodes, or an even number | WARN; PASS shows how many losses Raft tolerates |
| Stray master label | `kube-ovn/role=master` on a node outside `centralNodes` | WARN |
| Legacy label | `node-role.kubernetes.io/network` present | INFO |

### providers

Validates every `spec.networking.providerNetworks[]`, separating the default networks declared in
`setup.env` from the additional ones the platform manages. The rules and their severities are in
[Topology model → Provider networks](topology-model.md#provider-networks).

How it is performed:
1. **Classify.** Compare the KMetal interfaces with `PROV_IFACE` from `setup.env`; report each
   network as *default* or *additional*.
2. **Validate subnets.** Check each subnet's CIDR, gateway and `excludeIPs`, and check for
   overlaps against pod, service, join, node and the other provider networks, using the
   tool's own IP arithmetic.
3. **List target nodes.** Compute the network nodes (`kmetal.io/ovn`) that are not in
   `excludeNodes`.
4. **Inspect each target node over SSH** (only with `setup.env`). Run
   `ip -d -j link show dev <if>` and `ip -j -4 addr show dev <if>`, then check: present,
   carrier, no IPv4. The report shows VLAN ID and OVS master, and flags double tagging and a VLAN
   mismatch with `PROV_VLAN`.
5. **Reverse diff.** Report `setup.env` provider networks absent from the KMetal resource.

### tenancy

| Check | How | Severity |
|---|---|---|
| Subjects set | `spec.multiTenancy.users` is not empty | WARN: tenancy installed but inactive |
| Capsule | a `CapsuleConfiguration` exists | FAIL |
| Admission | `kubectl create namespace kmetal-validate-probe-<id>` impersonating a member of the first subject. For a `system:serviceaccounts:<ns>` group, the user is a ServiceAccount of that namespace, with the group added | PASS when rejected, since the probe user owns no Tenant. FAIL when the namespace is created without the `capsule.clastix.io/tenant` label: Capsule does not know the subject |

### capi

| Check | How | Severity |
|---|---|---|
| Providers | one each of core (`cluster-api`), bootstrap (`kubeadm`), infrastructure (`kubevirt`) and control plane (`kamaji`) in `kmetal-capi-providers`, each `Ready=True`; installed version shown | FAIL |
| ClusterClasses | at least one in `kmetal-capi-providers`; the one the end-to-end tests will use is shown | FAIL; also when `E2E_CLUSTERCLASS` names a missing class |

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
