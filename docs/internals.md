# Internals

[← Index](README.md)

For maintainers. `kmetal-validate` is a single bash file organised in sections, top to bottom.

## Layout

| Section | Contents |
|---|---|
| Defaults | Every `setup.env` key with its default; `setup.env` overrides them |
| Output | `section`, `pass`, `warn`, `fail`, `info`, `detail`, `summary`, `exit_code`, `usage` |
| Generic helpers | `require`, `to_seconds`, `poll`, `in_list`, `joinc`, `want`, `run_group` |
| IPv4 math | `valid_ip`, `valid_cidr`, `ip2int`, `int2ip`, `cidr_range`, `range_lohi`, `cidr_contains`, `range_contains`, `ranges_overlap`, `range_within`, `cidr_is_canonical` |
| `setup.env` parsing | `load_env` (validation, `NODE_LIST`, `NODE_ROLE`, `NODE_ADDR["node\|net"]`), `print_env`, `nodes_with_role`, `mgmt_ip` |
| SSH | `node_exec` (root script through stdin), `node_cmd` (command as `SSH_USER`), `run_on_nodes` (parallel fan-out) |
| Cleanup registry | `register_cleanup`, `run_cleanup`, `on_exit` |
| kubectl helpers | `load_km`, `km`/`kmj` (jq on the KMetal resource), `table_col`, `is_ready`, `wait_pod_done`, `pod_json`, `pvc_json`, `ensure_test_ns` |
| undercluster | `FACTS_SCRIPT`, `uc_*` group functions, `cmd_undercluster` |
| kmetal | `km_*` group functions, `resolve_*` helpers, `cmd_kmetal` |
| e2e | `tk`/`tk_apply` (tenant kubectl, direct or over SSH), `kas` (kubectl as a tenant owner), shared `e2e_*` steps, the two scenarios (`e2e_setup_envs`/`e2e_check_envs`, `e2e_setup_tenants`/`e2e_check_tenants`), `km_e2e` |
| cleanup, selftest | `cmd_cleanup`, `cmd_selftest` |
| Group help | `UC_GROUPS`, `KM_GROUPS` (group names in execution order), `group_help` (one help text per `command:group`), `show_help` |
| main | Argument parsing (flags, then the positional words `<command> [help [group]]`), help dispatch before anything is loaded, `setup.env` sourcing, run ID, temporary directory, traps, dispatch |

## Key mechanisms

**Results.**
- `pass`, `warn` and `fail` print a line and update the counters.
- `warn` and `fail` also append to the lists shown in the summary, prefixed with the current
  group (`CUR_GROUP`, set by `section`).
- `exit_code` derives `0`, `1` or `2` from the counters.
- The script uses `set -o pipefail`, but not `set -e`: a failing command inside a check must
  never abort the run.

**Group selection.** `run_group NAME FUNCTION` runs the function under a section header when
`want NAME` allows it (`--only` / `--skip`).

**`setup.env` loading.** The file is sourced at top level, not inside a function, so that
`declare -A` in the file creates global arrays. The defaults section pre-declares the arrays,
so plain `NET_IFACE=([mgmt]=…)` assignments work as well.

**Node facts.**
1. `FACTS_SCRIPT` is written to `$WORK/facts.<node>.sh`.
2. `run_on_nodes facts …` pipes the script to `$SSH_SUDO bash -s` on every node, in parallel;
   output goes to `$WORK/facts.<node>.out`.
3. Each `key=value` line is stored in `FACT["node|key"]` and read back with `fact NODE KEY`.
4. JSON blobs (`ip -j`, `netplan get`) are base64-encoded so they fit on one line.

Active probes (`mesh`, `internet`) use the same fan-out with a generated per-node script, and
print one result line per probe.

**KMetal spec access.**
- `km '<jq expr>'` prints raw values from the cached `KMetal` resource; `kmj` prints compact
  JSON.
- Both return nothing when the field is absent (`// empty`).

**Printer columns.** `table_col COLUMN <kubectl get args>` reads a value from
`kubectl get` table output by the column's character offset. This handles multi-word headers
such as `NAMESPACE QUOTA` and empty cells. It is used where a status field path is not
documented (`READY`, `VERSION`, `V4`, `BOUND`, `SUBNET`).

**Manifests.** Every manifest is built as JSON with `jq -n` and piped to `kubectl apply -f -`.
This avoids YAML quoting issues and makes adding the run ID label (`labels`) uniform.

**Tenant kubectl.**
- `tk ENV args…` runs `kubectl` against a tenant cluster.
- In `ssh` mode, the kubeconfig is sent base64-encoded on the first line of stdin. The remote
  side decodes it into a `mktemp` file, runs `kubectl`, and removes the file.
- `tk_apply` appends a manifest after that first line.

**End-to-end engine.**
- Every environment has a short key (`a`, `b`, `t1`, `t2`) indexing `ENV_TENANT`, `ENV_NS`,
  `ENV_CLUSTER` and `ENV_WORKERS`.
- The shared steps (`e2e_tenant`, `e2e_env`, `e2e_subnets`, `e2e_rbac`, `e2e_cluster_apply`,
  `e2e_access`, `e2e_inside`, `e2e_overlap`) take keys.
- `km_e2e` runs the setup of each selected scenario, then waits for all their clusters at once
  (`e2e_wait_clusters` sets `CLUSTER_UP[key]`), then runs each scenario's checks.
- A new scenario is a pair of `e2e_setup_*` / `e2e_check_*` functions plus a group name.

**Cleanup.**
- `register_cleanup "<command>"` pushes a command string.
- `run_cleanup` evaluates the strings in reverse order; it runs once, either at the end of
  `main` or from the `EXIT` trap.
- An `INT`/`TERM` trap exits with 130, which triggers the `EXIT` trap.

## Adding a check

1. Choose the command and an existing group, or write a new `uc_<name>` or `km_<name>`
   function.
2. Read expected values from `setup.env` variables or from `km '.spec…'`, never from literals.
3. Emit exactly one verdict per item: `pass` when met, `fail` when it breaks tenants, `warn`
   for deviations, `info` for context.
4. For objects you create, label them with `$(labels)`, create them in `ensure_test_ns` or
   under a `kv-$RUN_ID` name, and `register_cleanup` the deletion immediately after creation.
5. For a new group:
   - add a `run_group` line in `cmd_undercluster` or `cmd_kmetal`;
   - add the name to `UC_GROUPS` or `KM_GROUPS`, in execution order, and to the group list in
     `usage`;
   - add its help text as a `command:group` case in `group_help`. The first line must be
     `group - summary`, which `show_help` uses for the group list. Keep the body short: how the
     check is performed, the FAIL/WARN/INFO conditions, and a `Needs` line.
6. When a check's behaviour changes, update its `group_help` text and the matching page of this
   directory.

## Testing

- **Syntax:** `bash -n kmetal-validate`. Run `shellcheck kmetal-validate` when available.
- **IP arithmetic:** `./kmetal-validate selftest`.
- **Configuration parsing:** `./kmetal-validate -e FILE check-env`, including deliberately
  broken files.
- **undercluster without real nodes:** put a stub `ssh` first in `PATH` that drops the options
  and the host and runs the command locally. Describe local interfaces (`lo`, the default
  route device) in a test `setup.env`. Every group then runs against the local machine.
- **kmetal logic without a cluster:**
  1. Load the functions without running `main`:
     `source <(sed -n '1,/^# main$/p' kmetal-validate | sed '$d')`.
  2. Set `KM_JSON` to a `KMetal` object, for example converted from Helm values with
     `python3 -c 'import yaml,json…'`.
  3. Define a `kubectl` shell function that returns canned JSON, and a `node_cmd` function for
     SSH answers.
  4. Call a single `km_*` function.
- **Live:** run `kmetal --no-e2e` first, then the end-to-end tests with `--keep` while developing, and
  finish with `cleanup --run-id`.
