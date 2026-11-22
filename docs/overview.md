# Overview

[← Index](README.md)

## Purpose

A kMetal installation depends on a correctly prepared under cluster: the right VLANs on the
right nodes, non-overlapping address plans, a working overlay, controlled internet egress, the
correct node labels, and storage classes that can snapshot. When one of these is wrong, the
platform often installs and reports healthy, but tenant clusters fail later in ways that are
hard to trace back.

`kmetal-validate` turns the installation requirements and the platform validation procedure of
kMetal 1.0.1 into repeatable Ansible playbooks. A support engineer runs them from a bootstrap
machine:
- before installing kMetal, to prove the under cluster is ready;
- after installing it, to prove the platform works for a real tenant.

## Two phases

```mermaid
flowchart LR
    inv[inventory<br/>declared topology] --> uc
    subgraph uc[undercluster.yml]
        direction TB
        ssh[SSH + sudo to every node] --> facts[gather facts<br/>links, addresses, sysctls, modules]
        facts --> checks1[compare with the inventory<br/>ping, curl, test tunnel]
    end
    kc[admin kubeconfig] --> km
    subgraph km[kmetal.yml]
        direction TB
        spec[read the KMetal resource] --> checks2[platform checks<br/>operator, MetalLB, storage, labels, providers]
        checks2 --> e2e[end-to-end tests<br/>1 tenant x 2 environments<br/>2 tenants x 1 environment]
    end
    uc --> km
```

| Phase | Playbook | Source of truth | Reaches |
|---|---|---|---|
| Under cluster | `undercluster.yml` | The inventory: the topology the customer declared | Every node, over SSH |
| Platform | `kmetal.yml` | The live `KMetal` resource (`kubectl get km`) | The under cluster API; nodes over SSH when the inventory lists them |

The phases are independent:
- `undercluster.yml` needs no kubeconfig. When one works, it also cross-checks the node list and
  the address plan against the cluster.
- `kmetal.yml` needs no inventory. When one is given, it adds the checks that need SSH:
  interfaces on the nodes, the tenant API reached from the tenant VLAN, and EIP reachability.

`site.yml` runs both, one after the other.

## Design principles

- **Data-driven.** Nothing site-specific is hard-coded. Expected values come from the inventory
  (under cluster) or from the `KMetal` resource's `.spec` (platform): class names, address
  pools, central nodes, provider networks, image tags, tenancy subjects, placement.
- **Plain Ansible.** A standard inventory, one role per command, one tag per check group. The
  only custom code is a small filter plugin (IP arithmetic and parsers) and an action plugin
  that stores verdicts, plus an output plugin that organises the run by check group.
- **Every check is a verdict.** Each result is PASS, WARN, FAIL or INFO with a sentence saying
  what was found. A failed check never stops the run; the summary lists every FAIL and WARN.
- **Leave no trace.** Every object a run creates carries a run ID label and is deleted at the
  end of the run. Changes on the nodes are limited to a test tunnel device that lives a few
  seconds. See [Resources and cleanup](resources-and-cleanup.md).
- **Version-scoped.** The rules follow the kMetal **1.0.1** documentation. The operator chart
  version is read: `1.0.1` and its pre-releases pass, anything else is a WARN.

## Severities

| Level | Meaning | Effect on the run |
|---|---|---|
| PASS | The requirement is met | none |
| WARN | Works, but deviates from the recommended setup, or could not be fully verified | listed in the summary |
| FAIL | A requirement is not met; tenant workloads will break or the platform is unhealthy | the summary fails, exit code `2` |
| INFO | Context: a decision the playbook made, or an expected deviation | none |

## Design decisions

Where a requirement could be read more than one way, the playbooks follow the kMetal 1.0.1
documentation:

| Topic | Behaviour | Why |
|---|---|---|
| Network nodes | Identified by `node-role.kubernetes.io/network` with an empty value, and must also carry `kmetal.io/ovn=true` | kMetal 1.0.1 places Kube-OVN's DaemonSets by the network label; the kmetal-networking agent still selects `kmetal.io/ovn=true`, which the operator no longer sets |
| Operator-set labels | `ovn.kubernetes.io/external-gw`, `kube-ovn/role=master` and the removal of `exclude-from-external-load-balancers` are still checked | 1.0.1's node labelling controller sets them; a missing label means the controller is not working |
| Worker OS images | Read from `spec.clusterClass.values.osArtifact.tags` | The field path in the `KMetal` resource |
| `kube-ovn/role=master` | Checked on `spec.networking.kubeOVN.centralNodes`, ideally the three control planes | It is ovn-central's nodeSelector |
| Overlay on control planes | INFO when absent | Control planes are not network nodes; Kube-OVN's tunnel runs on network nodes only |
| Minimum size | Fewer than 1 control plane + 2 workers is a FAIL; fewer than 3 control planes is a WARN | The documented production layout has 3 control planes |
