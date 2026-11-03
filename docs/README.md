# kmetal-validate documentation

`kmetal-validate` checks that a bare-metal under cluster is wired correctly for kMetal
**1.0.0**, and that a kMetal installation works end to end. This index lists every page.

## Using the tool

| Page | Contents |
|---|---|
| [Overview](overview.md) | What the tool is for, the two validation phases, design principles |
| [Getting started](getting-started.md) | Requirements, first run, commands, flags, output, exit codes |
| [Configuration](configuration.md) | Every `setup.env` key, how the file is validated, a complete template |
| [Topology model](topology-model.md) | Networks, node roles, labels, central nodes and provider networks the checks expect |

## What is checked, and how

| Page | Contents |
|---|---|
| [Under cluster checks](undercluster-checks.md) | `undercluster`: each check group, the commands it runs on the nodes, its severity |
| [Platform checks](kmetal-checks.md) | `kmetal`: each check group against the under cluster API |
| [End-to-end tests](e2e-test.md) | Two scenarios: one tenant with two environments (storage, egress, EIP), and two tenants for multi-tenancy segregation |

## Operating it safely

| Page | Contents |
|---|---|
| [Resources and cleanup](resources-and-cleanup.md) | What the tool creates or changes, run IDs, cleanup, how to agree a run with the customer |
| [Interpreting results](interpreting-results.md) | Common FAIL and WARN messages, their cause and the fix |

## Maintaining the tool

| Page | Contents |
|---|---|
| [Internals](internals.md) | Script layout, helpers, how to add a check, how to test offline |

## Reading order

- **First run on a new site:** [Getting started](getting-started.md), then
  [Configuration](configuration.md), then [Resources and cleanup](resources-and-cleanup.md).
- **Understanding a result:** [Interpreting results](interpreting-results.md), then the group's
  section in [Under cluster checks](undercluster-checks.md) or [Platform checks](kmetal-checks.md).
- **Changing the script:** [Internals](internals.md).
