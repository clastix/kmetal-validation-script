# Internals

[← Index](README.md)

For maintainers. If Ansible is new to you, read the [Ansible primer](ansible-primer.md) first.

## Layout

| Path | Contents |
|---|---|
| `playbooks/` | The playbooks: `check-env.yml`, `undercluster.yml`, `kmetal.yml`, `site.yml`, `cleanup.yml`, `help.yml`, `selftest.yml`. Run them from the repository root (`ansible-playbook playbooks/<name>.yml`): `ansible.cfg` there points Ansible at `roles/`, the plugins and `collections/`. `help.yml` loads its texts with a path relative to itself (`../roles/common/vars/help.yml`). Each play imports role task files with `import_role` + `tasks_from`, one per check group, tagged with the group name |
| `roles/common/defaults/main.yml` | Every variable with its default. Every play lists `roles: [common]`, which makes these defaults visible; `common` has no `tasks/main.yml`, so listing it runs nothing |
| `roles/common/tasks/` | `validate.yml` (the inventory checks and `kmv_nodes`), `prepare.yml` (run ID, inventory, cluster access, `kmv_km`), `summary.yml` |
| `roles/common/vars/help.yml` | The help text of every check group, read by `playbooks/help.yml` |
| `roles/undercluster/tasks/` | `connectivity.yml` (facts), then one file per group: `topology`, `addressing`, `hardware`, `os`, `interfaces`, `netplan`, `mesh`, `internet`, `encap` |
| `roles/kmetal/tasks/` | One file per group (`platform` … `crds`), with helper files: `test_ns.yml`, `metallb_pool.yml`, `storage_smoke.yml`, `storage_snapshot.yml`, `pod_diag.yml`, `resolve_cc.yml`, `resolve_images.yml` |
| `roles/e2e/tasks/` | `main.yml` (scenario selection, gating, `always` cleanup of tenant objects), `prepare.yml`, the scenario files and the shared steps (`tenant`, `env`, `wait_ready`, `subnets`, `rbac`, `cluster_apply`, `wait_clusters`, `access`, `inside`, `crossnode`, `eip`, `worker_ips`, `overlap`, `isolation`) |
| `roles/cleanup/tasks/main.yml` | Label-driven deletion of a run, used by `kmetal.yml` and `cleanup.yml` |
| `filter_plugins/kmv.py` | Jinja filters: IPv4 arithmetic (`kmv_overlaps`, `kmv_within`, `kmv_contains`, `kmv_same_range`, `kmv_cidr_canonical`, `kmv_host`…), Kubernetes helpers (`kmv_ready`, `kmv_condition`, `kmv_pod_ok`, `kmv_table_col`, `kmv_clusters_up`), node helpers (`kmv_link`, `kmv_link_parent`, `kmv_ipv4`, `kmv_ping_loss`, `kmv_netplan_has`), and `kmv_version_status`, `kmv_artifact_for`, `kmv_seconds`, `kmv_joinc` |
| `test_plugins/kmv_tests.py` | The same helpers as Jinja tests, for `select()`/`reject()`: `kmv_contains`, `kmv_in`, `kmv_pod_ok`… |
| `action_plugins/kmv_record.py`, `library/kmv_record.py` | The `kmv_record` task and its documentation |
| `callback_plugins/kmv_output.py` | The output plugin (`stdout_callback` in `ansible.cfg`): group headers, step lines, verdicts, tallies, result. With `-v` it falls back to Ansible's standard output |
| `ansible.cfg` | Paths of roles, plugins and collections; YAML output; SSH options; `inject_facts_as_vars = false` |

## Key mechanisms

**Verdicts.**
- A check group gathers data with tasks that never fail (`failed_when: false`, or
  `ignore_errors: true` on object creation, which keeps the `failed` flag for later tests).
- Its last task is `kmv_record`, which receives the group name and a list of
  `{level, msg}` built by a Jinja block. The block starts with `{%- set v = [] -%}`, appends
  with `{%- set _ = v.append({...}) -%}`, and ends with `{{ v }}`, the only output, so the result
  is a real list.
- `kmv_record` (an action plugin: it runs on the controller and never contacts the host)
  appends the verdicts, tagged with the group, to the host fact `kmv_results`, and returns them
  in its result. The output plugin prints them; with any other output plugin, `kmv_record`
  prints them itself.
- Do not call `kmv_record` in a `loop`: each iteration starts from the same previous facts, so
  only the last iteration's verdicts would be kept. Build one list instead.
- The summary play gathers `kmv_results` from every host, prints counts, FAILs and WARNs, and
  fails when there is a FAIL, unless `kmv_summary_fail` is false (`site.yml` sets this for the
  under cluster part).

**Output.** `callback_plugins/kmv_output.py` turns the run into what a reader needs:
- **Playbook and play titles**: the playbook's purpose comes from `kmv_help_playbooks` in
  `roles/common/vars/help.yml`; a play's title is its `name` (write it as
  "<Phase> N/M - where it runs - what it does").
- **Group headers**: a task's group is its first tag other than `always` (`e2e` and
  `e2e-tenants` share one header, showing the selected scenarios). The header text is the
  group's help text (`kmv_help`), or for the steps that always run, `kmv_help_sections`:
  `prepare`, `inventory`, `connectivity`, `summary`, `cleanup`. A header is printed with the
  group's first output, so fully skipped groups print nothing.
- **Step lines**: one per task, at its first result, except internal actions (`set_fact`,
  `kmv_record`, `debug`, `fail`, `assert`, `meta`, includes and imports). The line is the task
  name without the `<group> | ` prefix, so **name every visible task as a plain sentence about
  what it does**, and say when it creates or deletes something and when that is undone:
  `metallb | Create a LoadBalancer Service on pool {{ _pool.value }}`. A prefix different from
  the group stays, as `env a: …`.
- **Verdicts and tally**: printed from `kmv_record`'s result; the tally closes the group.
- **Waits**: `until` retries print `... still waiting (attempt N of M)` at the first attempt and
  every tenth.
- **Errors**: a failed task that is not ignored prints an `ERROR` line; ignored failures and
  unreachable delegated hosts print nothing, since a verdict reports them. The `summary` group's
  `fail` task prints the `RESULT` line.
- With `-v` or more, every method calls Ansible's default output instead, and still prints the
  verdicts.

**Group selection.** Each group's `import_role` carries the group's tag. `import_role` is static,
so the tag reaches every task inside. Files included dynamically (`include_tasks`, e.g. the
storage smoke test per class) pass the tag on with `apply: {tags: [...]}`. Preparation,
connectivity, summary and cleanup are tagged `always` plus a section tag (`prepare`,
`connectivity`, `summary`, `cleanup`) that names their output header. The e2e role reads `ansible_run_tags` and
`ansible_skip_tags` to know which scenarios were selected.

**Inventory data.** `validate.yml` builds `kmv_nodes` (`[{name, role, addr}]`) on localhost
from the `control_plane` and `workers` groups and each host's `kmv_addresses`. Node plays read
their own `kmv_addresses` and `kmv_role`, and read cluster data (`kmv_km`, `kmv_central`,
`kmv_tunnel_type`) from `hostvars['localhost']`.

**Node facts.** `connectivity.yml` runs `setup` (ignoring unreachable hosts and errors, so the
node can get a FAIL verdict and be dropped with `meta: end_host`), the `ip -j` commands, a
`key=value` shell probe and `netplan get`, and stores everything in the host fact `kmv_n`:
`{links, addrs, misc, netplan}`.

**Active node probes.** `mesh.yml` and `internet.yml` render one shell script per node with
Jinja (one line per probe, printing `kind net peer result`) and parse its output. The tunnel
test in `encap.yml` runs on the two chosen nodes in the same task, so both ends are built in
parallel; the ping runs on the first, and the device is deleted in `always`.

**KMetal spec access.** `kmv_km` is the `KMetal` object. Read fields with dots and a
`default`: `kmv_km.spec.networking.kubeOVN.centralNodes | default([], true)`. Use brackets for
keys that clash with Python dict methods: `clusterClass['values']`, `(json)['items']`.

**Printer columns.** `kmv_table_col` reads a column from `kubectl get` table output by the
header's character offset, up to the next header. It is used where a status field path is not
documented (`READY`, `VERSION`, `V4`, `BOUND`, `SUBNET`).

**Object creation.** `kubernetes.core.k8s` with a YAML `definition`; every object carries
`{{ {kmv_label_key: kmv_rid} }}` as labels. The play sets `module_defaults` for
`group/kubernetes.core.k8s` (kubeconfig) and `environment: KUBECONFIG` for `kubectl` and `helm`.

**Waiting.** `until` + `retries` + `delay`. `wait_ready.yml` waits for a Ready condition, a
`status.ready`, or a `READY` column; `wait_clusters.yml` waits for every tenant cluster at once
with the `kmv_clusters_up` filter.

**Tenant kubectl.** `access.yml` writes the tenant kubeconfig (server rewritten to the
LoadBalancer address) to a 0600 temporary file on the host that will run `kubectl`:
`localhost` in direct mode, the tenant-kubectl control plane in ssh mode. It records
`_e2e_tk[key] = {host, kc}`. Tenant commands are `kubectl --kubeconfig <kc> …` with
`delegate_to: <host>`; manifests are passed on `stdin` as JSON. `main.yml` removes the files in
`always`.

**End-to-end state.** Environments are keys (`a`, `b`, `t1`, `t2`) of `_e2e_envs`
(`{tenant, ns, cluster, workers, group}`). Progress lives in `_e2e_ok`, `_e2e_applied`, `_e2e_up`,
`_e2e_tk` and `_e2e_ips`. A new scenario is a pair of `scenario_*_setup.yml` /
`scenario_*_checks.yml` files plus a tag.

**Delegated tasks** carry `ignore_unreachable: true`, so an unreachable node becomes a FAIL
verdict instead of stopping the play on localhost.

**No `connection: local` on plays.** The plays on `localhost` rely on Ansible's implicit
localhost, which always runs locally (with the venv's Python). A play-level `connection: local`
would also apply to every task the play delegates to a node, unless that node sets
`ansible_connection` itself, so `ip link show` and the other node checks would silently run on the
bootstrap machine instead of the node. For the same reason, do not list `localhost` in an
inventory without `ansible_connection: local`.

## Adding a check

1. Choose the playbook and an existing group, or create a new tasks file in
   `roles/undercluster/tasks/` or `roles/kmetal/tasks/`.
2. Read expected values from inventory variables or from `kmv_km.spec…`, never from literals.
3. Gather data with tasks that cannot fail the play (`failed_when: false`), each named as a plain
   sentence (see **Output** above), then build the verdicts in one `kmv_record` task: `PASS` when met, `FAIL` when it breaks tenants, `WARN` for
   deviations, `INFO` for context.
4. For objects you create, label them with `{{ {kmv_label_key: kmv_rid} }}`, create them in
   `test_ns.yml`'s namespace or under a `kv-<run id>` name, and set `kmv_created: true`. The
   cleanup role deletes them by label: if the new object is of a kind it does not know, add the
   kind to `roles/cleanup/tasks/main.yml`.
5. For a new group:
   - add an `import_role` task with the group's tag to the playbook, in execution order;
   - add the group to `kmv_help_groups` and its help text to `kmv_help` in
     `roles/common/vars/help.yml`. The first line must be `group - summary`;
   - if it is a kmetal group that must succeed before the end-to-end tests, add it to the list
     in `roles/e2e/tasks/main.yml` (`_e2e_fails_before`).
6. When a check's behaviour changes, update its help text and the matching page of this
   directory.

## Testing

- **Syntax:** `ansible-playbook -i inventory/example <playbook> --syntax-check` for every
  playbook.
- **Lint:** `ansible-lint --offline` (configuration in `.ansible-lint`).
- **Filters:** `ansible-playbook playbooks/selftest.yml`.
- **Inventory validation:** `ansible-playbook -i <inventory> playbooks/check-env.yml`, including
  deliberately broken copies of `inventory/example`.
- **Help:** `ansible-playbook playbooks/help.yml -e cmd=kmetal -e group=nodes`, and an unknown group.
- **undercluster without real nodes:** an inventory whose hosts use
  `ansible_connection: local` and `ansible_become: false`, with `kmv_networks` describing the
  local interfaces (e.g. the Wi-Fi interface as `mgmt`, `lo` as `tenant`). Several local hosts
  with different addresses exercise `mesh`. `encap` fails without root, as expected. Pass
  `-e kmv_kubeconfig=/nonexistent` so no cluster is contacted.
- **kmetal logic without a cluster:** put a fake `kubectl` (and `helm`) first in `PATH` that
  answers each command line with a canned JSON or table file, and run
  `playbooks/kmetal.yml -e kmv_kubeconfig=/nonexistent` with an empty inventory. Every read-only group
  then runs against the fixtures; object creation fails cleanly and the smoke tests are skipped.
  For the e2e steps, a small playbook can set `_e2e_envs` and the other state variables and
  `include_role` single files (`wait_clusters`, `subnets`, `rbac`, `overlap`) against the same
  fake.
- **Live:** run `playbooks/kmetal.yml --skip-tags e2e,e2e-tenants` first, then the end-to-end tests with
  `-e kmv_keep=true` while developing, and finish with `playbooks/cleanup.yml -e kmv_run_id=<id>`.
