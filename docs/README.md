# kmetal-validate documentation

`kmetal-validate` is a set of Ansible playbooks. They check that a bare-metal under cluster is
wired correctly for kMetal **1.0.1**, and that a kMetal installation works end to end. This
index lists every page.

## Using the playbooks

| Page | Contents |
|---|---|
| [Overview](overview.md) | What the playbooks are for, the two validation phases, design principles |
| [Ansible primer](ansible-primer.md) | Inventory, playbooks, roles, tags and the other Ansible concepts used here, shown on this project |
| [Getting started](getting-started.md) | Requirements, installation, first run, playbooks, tags, options, output, exit codes |
| [Configuration](configuration.md) | Every inventory variable, how the inventory is validated, a complete template |
| [Topology model](topology-model.md) | Networks, node roles, labels, central nodes and provider networks the checks expect |

## What is checked, and how

| Page | Contents |
|---|---|
| [Under cluster checks](undercluster-checks.md) | `undercluster.yml`: each check group, the commands it runs on the nodes, its severity |
| [Platform checks](kmetal-checks.md) | `kmetal.yml`: each check group against the under cluster API |
| [End-to-end tests](e2e-test.md) | Two scenarios: one tenant with two environments (storage, egress, EIP), and two tenants for multi-tenancy segregation |

## Operating it safely

| Page | Contents |
|---|---|
| [Resources and cleanup](resources-and-cleanup.md) | What a run creates or changes, run IDs, cleanup, how to agree a run with the customer |
| [Interpreting results](interpreting-results.md) | Common FAIL and WARN messages, their cause and the fix |

## Maintaining the playbooks

| Page | Contents |
|---|---|
| [Internals](internals.md) | Project layout, the verdict mechanism, how to add a check, how to test offline |

## Reading order

- **New to Ansible:** [Ansible primer](ansible-primer.md) first.
- **First run on a new site:** [Getting started](getting-started.md), then
  [Configuration](configuration.md), then [Resources and cleanup](resources-and-cleanup.md).
- **Understanding a result:** [Interpreting results](interpreting-results.md), then the group's
  section in [Under cluster checks](undercluster-checks.md) or [Platform checks](kmetal-checks.md).
- **Changing the playbooks:** [Internals](internals.md).
