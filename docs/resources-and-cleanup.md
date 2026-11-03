# Resources and cleanup

[← Index](README.md)

`kmetal-validate` runs against customer infrastructure. This page lists everything it touches,
so a run can be agreed with the customer in advance.

## What each command changes

| Command | On the nodes | In the under cluster |
|---|---|---|
| `check-env` | nothing | nothing |
| `undercluster` | Read-only, except a `kvtest0` tunnel device (Geneve/VXLAN, link-local `169.254.250.0/30`) that exists for a few seconds on two overlay nodes | nothing |
| `kmetal --no-e2e` | nothing (read-only SSH commands) | Namespace `kmetal-validate-<id>` with an nginx Deployment, one LoadBalancer Service per MetalLB pool, a 1 Gi PVC and writer pod per storage class, one VolumeSnapshot and one restored PVC. A probe namespace attempt (normally rejected) |
| `kmetal` (with `e2e`) | nothing | Everything above, plus one Tenant with its ServiceAccount, two environments with VPC and subnet claims, an EipClaim, and two tenant clusters (3 worker VMs) |
| `kmetal` (with `e2e-tenants`) | nothing | Two more Tenants with their ServiceAccounts, one environment each with VPC and subnet claims, and two tenant clusters (3 worker VMs) |

**Capacity consumed** while the end-to-end tests run (both scenarios; `e2e` alone in brackets):

| Resource | Amount |
|---|---|
| MetalLB tenant pool | 4 (2) addresses for the tenant API servers, + 1 during the metallb smoke test |
| MetalLB management pool | 1 address during the metallb smoke test |
| Provider network | 5 (3) addresses: one router port per environment, one EIP |
| Storage | about 1 Gi per class, plus one root disk per worker VM |
| Compute | 6 (3) worker VMs of `E2E_MACHINE_SIZE` and 4 (2) hosted control planes |

Pods pull `TEST_IMAGE`, `PROBE_IMAGE` and `CURL_IMAGE`; worker VMs boot from the platform's own
golden image.

## Run IDs

- Every run prints a five-digit run ID in its header.
- Every Kubernetes object the run creates carries the label `kmetal-validate/run-id=<id>`.
- Objects are named after the run:
  - platform checks: `kmetal-validate-<id>`, `kmetal-validate-probe-<id>`;
  - `e2e`: `kv-<id>`, `kv-<id>-a`, `kv-<id>-b`;
  - `e2e-tenants`: `kv-<id>-t1`, `kv-<id>-t2`, `kv-<id>-t1-env`, `kv-<id>-t2-env`.

## Automatic cleanup

Each creation step registers its own undo step on a stack. When the script exits, the stack runs
in reverse order: after success, after a failure, and after Ctrl-C or SIGTERM. Deletions wait
for completion, with bounded timeouts (up to 20 minutes for tenant clusters). The first
cluster deletion starts the deletion of every test cluster of the run, so all clusters go down
in parallel. Any step that fails is reported as a WARN in a final `cleanup` section.

The temporary directory on the bootstrap machine, which holds node facts and tenant
kubeconfigs (mode 700), is removed on exit.

## Keeping resources

`--keep` skips the cleanup and prints the command to run later:

```bash
./kmetal-validate kmetal --e2e-only --keep
# ... inspect the environments kv-<id>-a / kv-<id>-b ...
./kmetal-validate cleanup --run-id <id>
```

## Cleanup

`cleanup --run-id ID` removes everything labelled with that run ID, even without the original
session (for example after a lost SSH connection). It deletes, in this order:
1. Clusters, waiting up to 20 minutes for them to disappear;
2. EipClaims, SubnetClaims and VpcClaims;
3. namespaces;
4. Tenants;
5. ServiceAccounts;
6. with `setup.env`: the `kvtest0` device on every node.

It ends with PASS when nothing labelled with the run ID remains, and FAIL with the list of what
is left otherwise.

## Before running on a customer site

- Agree on the e2e window. It creates up to 6 VMs and consumes the addresses listed above;
  `--only e2e` or `--only e2e-tenants` runs a single scenario.
- Confirm a free tenant-pool and provider address budget.
- On air-gapped sites, set the image keys and `INTERNET_PROBE_URL` to mirrors.
- Use an account with passwordless sudo that the customer accepts for read-only inspection.
- Keep the run ID from the output until the run has cleaned up.
