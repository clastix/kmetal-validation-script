# kmetal-validate

Validation of a **kMetal 1.0.0** installation: first the bare-metal under cluster it runs on,
then the platform itself, up to a working tenant cluster.

## Why

kMetal installs and reports healthy on an under cluster that is subtly wrong:
- a VLAN missing on one node;
- a provider interface carrying an address;
- a node label nobody applied;
- a storage class that cannot snapshot.

The problems surface later, when the first tenant cluster does not boot or has no egress.

`kmetal-validate` turns the kMetal installation requirements and the platform validation
procedure into one repeatable command, run by a support engineer from a bootstrap machine. It
gives a PASS / WARN / FAIL verdict for every requirement, with the reason.

## What it does

| Command | Purpose | Needs |
|---|---|---|
| `undercluster` | Proves the nodes match the declared topology: hardware, OS prerequisites, VLAN interfaces and addresses, MTU, full-mesh reachability, internet egress only on the management network, and working kernel encapsulation | SSH with passwordless sudo, and `setup.env` |
| `kmetal` | Proves the platform is healthy and usable: KMetal and operator status, MetalLB, storage and snapshots, node labels and Kube-OVN central nodes, provider networks, tenancy, Cluster API, KubeVirt, CRDs and golden images. Then two end-to-end tests: one tenant with two environments on the same CIDR (storage, egress, EIP), and two tenants on the same CIDR to prove multi-tenancy segregation (permissions and traffic) | Admin kubeconfig; `setup.env` optional |
| `cleanup` | Removes everything a run created, by run ID | Admin kubeconfig |

Principles:
- **Data-driven.** Expected values come from `setup.env` and from the live `KMetal` resource,
  never from hard-coded site data.
- **Self-cleaning.** Every object carries a run ID label and is deleted on exit, even after
  Ctrl-C.
- **One file.** A single bash script, depending only on standard tools.

## Quick start

```bash
$EDITOR setup.env                                   # describe nodes and networks
./kmetal-validate check-env                         # validate the description
./kmetal-validate undercluster                      # node checks over SSH
./kmetal-validate kmetal --kubeconfig admin.conf --no-e2e   # platform checks
./kmetal-validate kmetal --kubeconfig admin.conf --e2e-only # end-to-end tests (25 to 45 minutes)
./kmetal-validate kmetal help [group]               # what each check group tests
```

Exit codes: `0` all passed, `1` at least one FAIL, `2` warnings only, `3` usage or
configuration error.

## Documentation

The full documentation is in [`docs/`](docs/README.md):

- [Overview](docs/overview.md): purpose, phases, design principles
- [Getting started](docs/getting-started.md): requirements, commands, flags, output
- [Configuration](docs/configuration.md): `setup.env` reference and template
- [Topology model](docs/topology-model.md): networks, node roles, labels, central nodes,
  provider networks
- [Under cluster checks](docs/undercluster-checks.md)
- [Platform checks](docs/kmetal-checks.md)
- [End-to-end tests](docs/e2e-test.md): environments and multi-tenancy segregation
- [Resources and cleanup](docs/resources-and-cleanup.md): what a run creates and how it is
  removed
- [Interpreting results](docs/interpreting-results.md): common failures and fixes
- [Internals](docs/internals.md): for maintainers

## Repository

| Path | Contents |
|---|---|
| `kmetal-validate` | The script |
| `setup.env` | Site description loaded by default |
| `setup.env.example` | Example site description with random addresses, VLANs and CIDRs |
| `docs/` | Documentation |
