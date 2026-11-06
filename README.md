# kmetal-validate

Ansible playbooks that validate a **kMetal 1.0.1** installation: first the bare-metal under
cluster it runs on, then the platform itself, up to working tenant clusters.

## Why

kMetal installs and reports healthy on an under cluster that is subtly wrong:
- a VLAN missing on one node;
- a provider interface carrying an address;
- a node label nobody applied;
- a storage class that cannot snapshot.

The problems surface later, when the first tenant cluster does not boot or has no egress.

`kmetal-validate` turns the kMetal installation requirements and the platform validation
procedure into repeatable playbooks, run by a support engineer from a bootstrap machine. It
gives a PASS / WARN / FAIL verdict for every requirement, with the reason.

## What it does

| Playbook | Purpose | Needs |
|---|---|---|
| `undercluster.yml` | Proves the nodes match the declared topology: hardware, OS prerequisites, VLAN interfaces and addresses, MTU, full-mesh reachability, internet egress only on the management network, and working kernel encapsulation | SSH with passwordless sudo, and an inventory |
| `kmetal.yml` | Proves the platform is healthy and usable: KMetal and operator status, MetalLB, storage and snapshots, node labels and Kube-OVN central nodes, provider networks, tenancy, Cluster API, KubeVirt, CRDs and golden images. Then two end-to-end tests: one tenant with two environments on the same CIDR (storage, egress, EIP), and two tenants on the same CIDR to prove multi-tenancy segregation (permissions and traffic) | Admin kubeconfig; inventory optional |
| `site.yml` | Both of the above | Both |
| `cleanup.yml` | Removes everything a run created, by run ID | Admin kubeconfig |
| `check-env.yml` | Validates the inventory and prints the node table | Inventory |
| `help.yml` | What each check group tests | Nothing |

Principles:
- **Data-driven.** Expected values come from the inventory and from the live `KMetal`
  resource, never from hard-coded site data.
- **Self-cleaning.** Every object carries a run ID label and is deleted at the end of the run.
- **Plain Ansible.** Standard inventory, roles and tags; one small filter plugin for IP
  arithmetic and one action plugin that prints the verdicts.

## Quick start

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
ansible-galaxy collection install -r requirements.yml -p ./collections

cp -r inventory/example inventory/mysite && $EDITOR inventory/mysite/hosts.yml inventory/mysite/group_vars/all.yml
ansible-playbook -i inventory/mysite check-env.yml                  # validate the description
ansible-playbook -i inventory/mysite undercluster.yml               # node checks over SSH
export KUBECONFIG=admin.conf
ansible-playbook -i inventory/mysite kmetal.yml --skip-tags e2e,e2e-tenants   # platform checks
ansible-playbook -i inventory/mysite kmetal.yml --tags e2e,e2e-tenants        # end-to-end tests (25 to 45 minutes)
ansible-playbook help.yml -e cmd=kmetal -e group=nodes              # what a check group tests
```

Run every command from the repository root: Ansible reads `ansible.cfg` from the current
directory.

Exit codes: `0` no failure (warnings are listed in the summary), `2` at least one FAIL or an
invalid inventory, `99` interrupted (then run `cleanup.yml` with the run ID).

New to Ansible? Start with the [Ansible primer](docs/ansible-primer.md).

## Documentation

The full documentation is in [`docs/`](docs/README.md):

- [Overview](docs/overview.md): purpose, phases, design principles
- [Ansible primer](docs/ansible-primer.md): the Ansible concepts this project uses
- [Getting started](docs/getting-started.md): requirements, installation, playbooks, tags, options, output
- [Configuration](docs/configuration.md): inventory reference and template
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
| `*.yml` (root) | The playbooks |
| `roles/` | `common` (defaults, inventory validation, summary, help texts), `undercluster`, `kmetal`, `e2e`, `cleanup` |
| `inventory/example/` | Example site description with random addresses, VLANs and CIDRs |
| `filter_plugins/`, `test_plugins/` | IPv4 arithmetic and parsing helpers for Jinja |
| `action_plugins/`, `library/` | `kmv_record`, which prints and stores verdicts |
| `ansible.cfg`, `requirements.txt`, `requirements.yml`, `.ansible-lint` | Ansible configuration and dependencies |
| `docs/` | Documentation |
