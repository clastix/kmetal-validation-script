# Resources and cleanup

[← Index](README.md)

`kmetal-validate` runs against customer infrastructure. This page lists everything it touches,
so a run can be agreed with the customer in advance.

## What each playbook changes

| Playbook | On the nodes | In the under cluster |
|---|---|---|
| `check-env.yml`, `help.yml`, `selftest.yml` | nothing | nothing |
| `undercluster.yml` | Read-only, except a `kvtest0` tunnel device (Geneve/VXLAN, link-local `169.254.250.0/30`) that exists for a few seconds on two overlay nodes | nothing |
| `playbooks/kmetal.yml --skip-tags e2e,e2e-tenants` | nothing (read-only SSH commands) | Namespace `kmetal-validate-<id>` with an nginx Deployment, one LoadBalancer Service per MetalLB pool, a 1 Gi PVC and writer pod per storage class, one VolumeSnapshot and one restored PVC. A probe namespace attempt (normally rejected; deleted right away otherwise) |
| `kmetal.yml` (tag `e2e`) | a temporary tenant kubeconfig (mode 0600) on the control plane that runs tenant `kubectl`, in `ssh` mode only | Everything above, plus one Tenant with its ServiceAccount, two environments with VPC and subnet claims, an EipClaim, and two tenant clusters (3 worker VMs) |
| `kmetal.yml` (tag `e2e-tenants`) | as above | Two more Tenants with their ServiceAccounts, one environment each with VPC and subnet claims, and two tenant clusters (3 worker VMs) |

**Capacity consumed** while the end-to-end tests run (both scenarios; `e2e` alone in brackets):

| Resource | Amount |
|---|---|
| MetalLB tenant pool | 4 (2) addresses for the tenant API servers, + 1 during the metallb smoke test |
| MetalLB management pool | 1 address during the metallb smoke test |
| Provider network | 5 (3) addresses: one router port per environment, one EIP |
| Storage | about 1 Gi per class, plus one root disk per worker VM |
| Compute | 6 (3) worker VMs of `kmv_e2e_machine_size` and 4 (2) hosted control planes |

Pods pull `kmv_test_image`, `kmv_probe_image` and `kmv_curl_image`; worker VMs boot from the
platform's own golden image.

## Run IDs

- Every run prints a five-digit run ID in its first task (`prepare | run`), together with the
  cleanup command for that run.
- Every Kubernetes object the run creates carries the label `kmetal-validate/run-id=<id>`.
- Objects are named after the run:
  - platform checks: `kmetal-validate-<id>`, `kmetal-validate-probe-<id>`;
  - `e2e`: `kv-<id>`, `kv-<id>-a`, `kv-<id>-b`;
  - `e2e-tenants`: `kv-<id>-t1`, `kv-<id>-t2`, `kv-<id>-t1-env`, `kv-<id>-t2-env`.
- `-e kmv_run_id=<id>` fixes the run ID instead of drawing a random one.

## Automatic cleanup

`kmetal.yml` wraps all its check groups in a `block`. Its `always` part runs the `cleanup` role
for the run ID, after success and after a failed task. The role deletes by label, in an order
that lets every controller finish:
1. the tenant Clusters, all at once so they go down in parallel, waiting up to 20 minutes;
2. EipClaims, SubnetClaims and VpcClaims;
3. namespaces (the temporary namespace, the environments, the tenant-group namespace if the run
   created it);
4. Tenants;
5. ServiceAccounts.

Before that, the `e2e` role deletes the tenant Service `web` (which unbinds the EIP) and the
temporary tenant kubeconfigs.

The cleanup ends with a `cleanup` verdict: PASS when nothing labelled with the run ID remains,
WARN with the list of what is left otherwise.

The `kvtest0` device of `undercluster.yml` is deleted by its own `always` block.

**Ctrl-C** stops Ansible immediately: `always` blocks do **not** run. Use `cleanup.yml` with the
run ID printed at the start.

## Keeping resources

`-e kmv_keep=true` skips the cleanup; the summary prints the command to run later:

```bash
ansible-playbook -i inventory/<site> playbooks/kmetal.yml --tags e2e,e2e-tenants -e kmv_keep=true
# ... inspect the environments kv-<id>-a / kv-<id>-b ...
ansible-playbook -i inventory/<site> playbooks/cleanup.yml -e kmv_run_id=<id>
```

## Cleanup

`playbooks/cleanup.yml -e kmv_run_id=ID` removes everything labelled with that run ID, even without the
original session (for example after Ctrl-C or a lost SSH connection). It runs the same
`cleanup` role as above and, when the inventory lists nodes, deletes `kvtest0` on every node.

It ends with PASS when nothing labelled with the run ID remains, and FAIL with the list of what
is left otherwise (at the end of a `kmetal.yml` run the same leftovers are a WARN).

## Before running on a customer site

- Agree on the e2e window. It creates up to 6 VMs and consumes the addresses listed above;
  `--tags e2e` or `--tags e2e-tenants` runs a single scenario.
- Confirm a free tenant-pool and provider address budget.
- On air-gapped sites, set the image variables and `kmv_internet_probe_url` to mirrors.
- Use an account with passwordless sudo that the customer accepts for read-only inspection.
- Keep the run ID from the output until the run has cleaned up.
