# Getting started

[← Index](README.md)

## Requirements

**Bootstrap machine** (where Ansible runs):

| Tool | Used by |
|---|---|
| Python 3.10 or later | Ansible |
| `ansible-core`, the `kubernetes` Python client (`requirements.txt`) | every playbook; the client is used by `kubernetes.core` |
| the `kubernetes.core` collection (`requirements.yml`) | creating and reading test objects |
| `ssh` | `undercluster.yml`, and the SSH checks of `kmetal.yml` |
| `kubectl`, `helm` | `kmetal.yml`, `cleanup.yml`, and the cluster cross-checks of `undercluster.yml` |

**Nodes:**
- reachable over SSH on their management address, as `ansible_user`;
- passwordless `sudo -n` for that user, or `ansible_user: root`;
- Python 3 (standard on Ubuntu), `ip` (iproute2), `ping` and `curl`;
- `kubectl` on the control planes, only when the tenant API must be reached through a control
  plane (see [End-to-end tests](e2e-test.md#tenant-api-access)).

**Cluster access:** an admin kubeconfig of the under cluster for `kmetal.yml`. The end-to-end
tests impersonate tenant users, which needs the `impersonate` verb that cluster-admin has.

## Installation

From the repository root:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
ansible-galaxy collection install -r requirements.yml -p ./collections
```

`.venv/` and `collections/` are gitignored. Activate the venv (`. .venv/bin/activate`) in every
new shell, and run every playbook **from the repository root**: Ansible reads `ansible.cfg` from
the current directory, and `ansible.cfg` points at the roles, plugins and collections.

## First run

```bash
# 1. Describe the site
cp -r inventory/example inventory/mysite
$EDITOR inventory/mysite/hosts.yml inventory/mysite/group_vars/all.yml   # docs/configuration.md

# 2. Validate the description, contacting nothing
ansible-playbook -i inventory/mysite playbooks/check-env.yml

# 3. Check the nodes (before or after installing kMetal)
ansible-playbook -i inventory/mysite playbooks/undercluster.yml

# 4. Check the platform, without the end-to-end tests
export KUBECONFIG=$PWD/admin.conf
ansible-playbook -i inventory/mysite playbooks/kmetal.yml --skip-tags e2e,e2e-tenants

# 5. Run the end-to-end tests (3 tenants, 4 clusters, 6 VMs; about 25 to 45 minutes)
ansible-playbook -i inventory/mysite playbooks/kmetal.yml --tags e2e,e2e-tenants
```

Agree on step 5 with the customer first: it consumes addresses and capacity. See
[Resources and cleanup](resources-and-cleanup.md).

## Playbooks

| Playbook | Does |
|---|---|
| `playbooks/check-env.yml` | Validates the inventory and prints the node table. Contacts nothing |
| `playbooks/undercluster.yml` | Under cluster checks over SSH ([details](undercluster-checks.md)) |
| `playbooks/kmetal.yml` | Platform checks and end-to-end tests ([details](kmetal-checks.md), [e2e](e2e-test.md)). The inventory is optional |
| `playbooks/site.yml` | `undercluster.yml`, then `kmetal.yml`, with a single final summary |
| `playbooks/cleanup.yml -e kmv_run_id=ID` | Deletes everything a run left behind ([details](resources-and-cleanup.md#cleanup)) |
| `playbooks/help.yml` | Usage; `-e cmd=undercluster` or `-e cmd=kmetal` lists the check groups; add `-e group=<g>` for one group ([details](#help-on-check-groups)) |
| `playbooks/selftest.yml` | Tests the IP arithmetic and parsing filters ([Internals](internals.md#testing)) |

## Help on check groups

Every check group has a built-in help text. It needs no inventory, kubeconfig or network
access.

```bash
ansible-playbook playbooks/help.yml -e cmd=undercluster              # list the undercluster groups
ansible-playbook playbooks/help.yml -e cmd=kmetal                    # list the kmetal groups
ansible-playbook playbooks/help.yml -e cmd=kmetal -e group=nodes     # explain one group
```

An unknown group fails and lists the valid names.

```
$ ansible-playbook playbooks/help.yml -e cmd=undercluster -e group=mesh
    msg:
    - mesh - full-mesh reachability on every node network
    - ''
    - '  Each node pings every peer address on each network both have, bound to that'
    - '  network''s interface, all nodes in parallel:'
    - '    ping -c3 -i0.2 -W1 -q -I <iface> <peer>'
    ...
```

Each text gives a summary line, then how the check is performed, then its FAIL, WARN and INFO
conditions, then what it needs. The full rules are in
[Under cluster checks](undercluster-checks.md) and [Platform checks](kmetal-checks.md).

## Selecting check groups: tags

Every check group is a tag. Ansible's `--tags` runs only the listed groups, `--skip-tags`
skips them. Preparation, connectivity, the summary and cleanup always run.

| Playbook | Tags, in execution order |
|---|---|
| `playbooks/undercluster.yml` | `topology` `addressing` (on the bootstrap machine), then `hardware` `os` `interfaces` `netplan` `mesh` `internet` `encap` (on the nodes; `connectivity` always runs first) |
| `playbooks/kmetal.yml` | `platform` `operator` `metallb` `storage` `nodes` `providers` `tenancy` `capi` `kubevirt` `crds` `e2e` `e2e-tenants` |

`ansible-playbook <playbook> --list-tags` prints them too.

## Options

Options are variables set with `-e name=value`. They override the inventory.

| Option | Applies to | Effect |
|---|---|---|
| `-i inventory/<site>` | all | The site description. Required by `check-env.yml` and `undercluster.yml`; optional for `kmetal.yml` |
| `-e kmv_kubeconfig=FILE` | all | Under cluster kubeconfig (default `$KUBECONFIG`, else `~/.kube/config`) |
| `--tags g1,g2` / `--skip-tags g1,g2` | `undercluster.yml`, `kmetal.yml` | Run only, or skip, these check groups |
| `--skip-tags e2e,e2e-tenants` | `kmetal.yml` | Platform checks only |
| `--tags e2e,e2e-tenants` | `kmetal.yml` | End-to-end tests only. For a single scenario use `--tags e2e` or `--tags e2e-tenants` |
| `-e kmv_keep=true` | `kmetal.yml` | Do not delete test resources; the summary prints the cleanup command |
| `-e kmv_force_e2e=true` | `kmetal.yml` | Run the end-to-end groups even when earlier groups failed |
| `-e kmv_timeout_cluster=45m` | `kmetal.yml` | How long to wait for tenant clusters (default `30m`; `s`, `m`, `h` suffixes) |
| `-e kmv_run_id=ID` | `cleanup.yml` (required); any playbook | The run to clean up; on other playbooks, a fixed run ID instead of a random one |
| `-v`, `-vvv` | all | Ansible's standard output, every task with its result; `-vvv` also shows the SSH connections |

## Output

The output is organised by check group (the tags), by the project's output plugin
(`callback_plugins/kmv_output.py`). An excerpt of `undercluster.yml`:

```
kmetal-validate  playbooks/undercluster.yml  -  compare every node with the inventory over SSH; read-only, ...

== Under cluster 2/3 - on every node, in parallel, over SSH with sudo ==

>> interfaces - VLAN interfaces, MTU and addresses as declared

  Reads `ip -d -j link` and `ip -j addr` on every node. For each network of
  kmv_networks: the interface exists, is UP with carrier, is a VLAN device with the
  declared vlan, has the declared mtu, and carries the node's kmv_addresses entry. ...

  FAIL  missing or down interface, wrong VLAN, MTU or address; IPv4 on a provider
  INFO  control plane without overlay (expected: the tunnel runs on network nodes); ...
  Needs inventory, SSH

  PASS worker-01: overlay bond0.105 VLAN 105 MTU 9000 172.22.105.12/24 (on bond0)
  FAIL worker-02: provider provider (bond0.106): carries IPv4 172.22.106.13: a provider interface must have no address
  INFO cp-01: control plane without overlay interface: expected, Kube-OVN's tunnel runs on the network nodes ...
  => interfaces: 6 passed, 1 failures, 1 info
...
== Under cluster 3/3 - summary ==

>> summary - outcome of the run
    41 passed, 2 warnings, 1 failures
    FAIL [interfaces] worker-02: provider provider (bond0.106): carries IPv4 ...
    WARN [...] ...

RESULT: FAILED - 1 check(s) failed (exit code 2)
```

| Line | Meaning |
|---|---|
| `kmetal-validate  playbooks/<name>.yml  -  …` | The playbook and what it is for |
| `== … ==` | A play: where it runs (this machine, or every node over SSH) and what it does |
| `>> <group> - <summary>` | A check group, named like its tag. The text under it says how the group checks, what its FAIL, WARN and INFO mean, what it needs and whether it creates anything. It is the same text as `playbooks/help.yml -e cmd=<playbook> -e group=<group>`. The steps that always run (`prepare`, `connectivity`, `summary`, `cleanup`) have such a header too |
| `  > …` | A step: what the group reads, creates or deletes. Steps that change something say so, and say when the object is deleted |
| `    ... still waiting (attempt N of M)` | A step polling for something (a pod, a claim, a cluster); M attempts, a few seconds apart |
| `  PASS` / `WARN` / `FAIL` / `INFO` | The verdicts, coloured by level |
| `  => <group>: …` | The tally of the group |
| `  ERROR on <host>, step "…"` | A step failed in a way no check expected (not a verdict); the playbook stops there |
| `RESULT: …` | The outcome: `FAILED` with exit code 2 when a check failed, `no failures` otherwise |

- The `prepare` section prints the **run ID**. Every Kubernetes object the run creates carries
  it, and `playbooks/cleanup.yml` uses it.
- A group whose steps were all skipped prints nothing.
- Internal steps (reading facts, evaluating results) are not shown. **`-v`** switches to
  Ansible's standard output, with every task and its result (the verdicts are still printed);
  `-vvv` also shows the SSH connections. See the [Ansible primer](ansible-primer.md#reading-the-output).

## Exit codes

| Code | Meaning |
|---|---|
| `0` | No FAIL (warnings, if any, are in the summary) |
| `2` | At least one FAIL; or the inventory is invalid; or the under cluster API is unreachable for `kmetal.yml` |
| `4` | A host could not be reached outside a check (rare: unreachable nodes are reported as FAIL verdicts instead) |
| `99` | Interrupted (Ctrl-C); run `cleanup.yml` with the run ID |

These differ from the former bash tool, which had a separate code for warnings only. Read the
summary line to tell a clean run from a run with warnings.

## Typical sequences

| Situation | Command |
|---|---|
| Nodes installed, kMetal not yet | `undercluster.yml` (set `kmv_central_nodes` in the inventory, since no `KMetal` resource can supply it) |
| kMetal installed, quick health check | `playbooks/kmetal.yml --skip-tags e2e,e2e-tenants` |
| Acceptance of a new site | `site.yml` |
| Re-test only networking after a fix | `playbooks/undercluster.yml --tags interfaces,mesh` |
| Check multi-tenancy segregation only | `playbooks/kmetal.yml --tags e2e-tenants` |
| Debug a failing tenant cluster | `playbooks/kmetal.yml --tags e2e,e2e-tenants -e kmv_keep=true`, inspect, then `playbooks/cleanup.yml -e kmv_run_id=ID` |
