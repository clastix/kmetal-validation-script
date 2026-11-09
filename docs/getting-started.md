# Getting started

[← Index](README.md)

## Requirements

**Bootstrap machine** (where the script runs):

| Tool | Used by |
|---|---|
| bash ≥ 4 | everything (associative arrays) |
| `ssh` | `undercluster`, and the SSH-based probes of `kmetal` |
| `jq`, `awk`, `base64` | parsing node facts and Kubernetes JSON |
| `kubectl`, `helm`, `curl` | `kmetal` |

**Nodes:**
- reachable over SSH on their management address, as `SSH_USER`;
- `sudo -n` (passwordless) for that user, or `SSH_USER=root` with `SSH_SUDO=""`;
- `ip` (iproute2), `ping` and `curl` installed (standard on Ubuntu);
- `kubectl` on the control planes, only when the tenant API must be reached through a control
  plane (see [End-to-end tests](e2e-test.md#tenant-api-access)).

**Cluster access:** an admin kubeconfig of the under cluster for `kmetal`. The end-to-end test
impersonates tenant users, which requires the `impersonate` verb that cluster-admin has.

## First run

```bash
# 1. Describe the site
$EDITOR setup.env                      # template: docs/configuration.md

# 2. Validate the description, contacting nothing
./kmetal-validate check-env

# 3. Check the nodes (before or after installing kMetal)
./kmetal-validate undercluster

# 4. Check the platform, without the end-to-end test
./kmetal-validate kmetal --kubeconfig admin.conf --no-e2e

# 5. Run the end-to-end tests (3 tenants, 4 clusters, 6 VMs; about 25 to 45 minutes)
./kmetal-validate kmetal --kubeconfig admin.conf --e2e-only
```

Agree on step 5 with the customer first: it consumes addresses and capacity. See
[Resources and cleanup](resources-and-cleanup.md).

## Commands

| Command | Does |
|---|---|
| `undercluster` | Under cluster checks over SSH ([details](undercluster-checks.md)) |
| `kmetal` | Platform checks and end-to-end tests ([details](kmetal-checks.md), [e2e](e2e-test.md)) |
| `cleanup --run-id ID` | Deletes everything a run left behind ([details](resources-and-cleanup.md#cleanup)) |
| `check-env` | Parses and validates `setup.env`, prints the node table, contacts nothing |
| `help` | Usage |
| `undercluster help [group]`, `kmetal help [group]` | Without a group: the command's check groups, each with a one-line summary. With a group: a short explanation of what it tests, how, its FAIL/WARN conditions and what it needs ([details](#help-on-check-groups)) |
| `version` | Script version and the kMetal version it validates |
| `selftest` | Hidden: tests the IP arithmetic helpers ([Internals](internals.md#testing)) |

## Help on check groups

Every check group has a built-in help text. It needs no `setup.env`, kubeconfig or network
access.

```bash
./kmetal-validate undercluster help          # list the undercluster groups with a summary
./kmetal-validate kmetal help                # list the kmetal groups with a summary
./kmetal-validate kmetal help e2e-tenants    # explain one group
```

Equivalent spellings: `kmetal-validate help kmetal e2e-tenants` and
`kmetal-validate kmetal --help e2e-tenants`. An unknown group name exits with code `3` and
lists the valid names.

```
$ ./kmetal-validate undercluster help mesh
mesh - full-mesh reachability on every node network

  Each node pings every peer address on each network both have, bound to that
  network's interface, all nodes in parallel:
    ping -c3 -i0.2 -W1 -q -I <iface> <peer>
  When NET_MTU > 1500, a do-not-fragment ping of MTU-28 bytes checks jumbo frames.

  FAIL  peer unreachable (100% loss)
  WARN  partial loss; jumbo frame does not pass end to end
  Needs setup.env, SSH
```

Each text gives a summary line, then how the check is performed, then its FAIL, WARN and INFO
conditions, then what it needs. The full rules are in
[Under cluster checks](undercluster-checks.md) and [Platform checks](kmetal-checks.md).

## Flags

Flags may come before or after the command.

| Flag | Applies to | Effect |
|---|---|---|
| `-e, --env FILE` | all | `setup.env` to load. Default `./setup.env`; required by `undercluster`, optional for `kmetal` |
| `--kubeconfig FILE` | all | Under cluster kubeconfig (default `$KUBECONFIG`) |
| `--only g1,g2` | `undercluster`, `kmetal` | Run only these check groups |
| `--skip g1,g2` | `undercluster`, `kmetal` | Skip these check groups |
| `--keep` | all | Do not delete test resources; print the cleanup command instead |
| `-v, --verbose` | all | Trace every command (`set -x`); `DEBUG=true` does the same |
| `--no-e2e` | `kmetal` | Skip both end-to-end groups (`e2e`, `e2e-tenants`) |
| `--e2e-only` | `kmetal` | Run only the end-to-end groups. For a single scenario use `--only e2e` or `--only e2e-tenants` instead |
| `--force-e2e` | `kmetal` | Run the end-to-end groups even when earlier groups failed |
| `--timeout-cluster D` | `kmetal` | How long to wait for tenant clusters (default `30m`; `s`, `m`, `h` suffixes) |
| `--run-id ID` | `cleanup` | The run to clean up |

**Check group names:**

| Command | Groups, in execution order |
|---|---|
| `undercluster` | `topology` `hardware` `os` `interfaces` `netplan` `addressing` `mesh` `internet` `encap` (connectivity always runs first) |
| `kmetal` | `platform` `operator` `metallb` `storage` `nodes` `providers` `tenancy` `capi` `kubevirt` `crds` `e2e` `e2e-tenants` |

## Output

```
kmetal-validate 0.1.0  command=undercluster  run=40213  env=./setup.env

== interfaces ==
  PASS worker-01: overlay bond0.105 VLAN 105 MTU 9000 172.22.105.12/24 (on bond0)
  FAIL worker-02: provider provider (bond0.106): carries IPv4 172.22.106.13: a provider interface must have no address
  INFO cp-01: control plane without overlay interface: expected, Kube-OVN's tunnel runs on the network nodes (node-role.kubernetes.io/network) only

== summary ==
  41 passed, 2 warnings, 1 failures
  FAIL [interfaces] worker-02: provider provider (bond0.106): carries IPv4 ...
  WARN [...] ...
```

- The header shows the **run ID**. Every Kubernetes object the run creates carries it, and
  `cleanup --run-id` uses it.
- Each section is one check group. Indented lines below a result are diagnostics: logs, events
  or the list of failing items.
- The summary repeats every FAIL and WARN with its group.
- Set `NO_COLOR=1` to disable colours; they are also off when output is not a terminal.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Every check passed |
| `1` | At least one FAIL |
| `2` | WARNs, but no FAIL |
| `3` | Usage error, invalid `setup.env`, missing tool, or unreachable cluster API |
| `130` | Interrupted (cleanup still runs) |

## Typical sequences

| Situation | Command |
|---|---|
| Nodes installed, kMetal not yet | `undercluster` (set `CENTRAL_NODES` in `setup.env`, since no `KMetal` resource can supply it) |
| kMetal installed, quick health check | `kmetal --no-e2e` |
| Acceptance of a new site | `undercluster`, then `kmetal` |
| Re-test only networking after a fix | `undercluster --only interfaces,mesh` |
| Check multi-tenancy segregation only | `kmetal --only e2e-tenants` |
| Debug a failing tenant cluster | `kmetal --e2e-only --keep`, inspect, then `cleanup --run-id ID` |
