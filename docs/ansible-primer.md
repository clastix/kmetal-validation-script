# Ansible primer

[← Index](README.md)

The Ansible concepts this project uses, each shown on this project. It is enough to run the
playbooks, read their output and make small changes. The official reference is the
[Ansible documentation](https://docs.ansible.com/).

## The big picture

Ansible runs on **one machine**, the controller: here, the bootstrap machine. It connects to
the other machines over SSH and runs small programs, called **modules**, on them. Nothing has to
be installed on the nodes except Python, which Ubuntu ships.

```
bootstrap machine (controller)            nodes
  ansible-playbook undercluster.yml  --SSH-->  run a module, return JSON
  evaluate the JSON, print verdicts  <-------
```

`kmetal.yml` mostly runs on the controller itself (`localhost`), calling `kubectl` against the
under cluster API. It reaches into the nodes only for the few checks that need them.

## Inventory: the machines and their data

The **inventory** lists the machines and the variables that describe them. It replaces the old
`setup.env`. It is a directory:

```
inventory/mysite/
  hosts.yml                 the nodes, grouped
  group_vars/all.yml        variables that apply to everything: networks, probes, e2e settings
  group_vars/kmetal_nodes.yml   variables for every node: how to reach it
```

In `hosts.yml`, **groups** organise the hosts. This project uses two groups, `control_plane`
and `workers`, both inside `kmetal_nodes`. A host's group is its role. Each host has its own
variables, here `kmv_addresses`:

```yaml
control_plane:
  hosts:
    cp-01:
      kmv_addresses: {mgmt: 10.0.0.11, tenant: 10.0.1.11}
```

`group_vars/kmetal_nodes.yml` sets `ansible_host`, the address Ansible connects to, from the
`mgmt` address. `ansible_user` is the SSH user. Variables whose name starts with `ansible_`
configure Ansible itself; the project's own variables start with `kmv_`.

Select an inventory with `-i`: `ansible-playbook -i inventory/mysite undercluster.yml`.

## Playbook, play, task

A **playbook** is a YAML file with one or more **plays**. A play says *which hosts* and *which
tasks*:

```yaml
- name: undercluster | nodes
  hosts: kmetal_nodes        # run on every node of the inventory
  become: true               # as root, through sudo
  tasks: ...
```

A **task** calls one module with arguments:

```yaml
- name: connectivity | links and addresses
  ansible.builtin.command: ip -d -j link show
  register: _uc_ip           # keep the result in a variable
  changed_when: false        # reading changes nothing
```

Ansible runs a task on all hosts of the play **in parallel**, waits for all of them, then
moves to the next task. That is how the node checks run on every node at once.

`undercluster.yml` has four plays:
1. preparation on `localhost` (validate the inventory, read the cluster);
2. the checks on the nodes;
3. the summary on `localhost`.

## Roles: where the tasks live

A **role** is a directory of tasks and default variables that playbooks reuse. This project has
five:

| Role | Contents |
|---|---|
| `common` | Defaults of every variable, inventory validation, preparation, summary, help texts |
| `undercluster` | One tasks file per under cluster check group |
| `kmetal` | One tasks file per platform check group |
| `e2e` | The end-to-end tests |
| `cleanup` | Deletion of a run's objects |

A playbook loads one file of a role with `import_role` and `tasks_from`:

```yaml
- name: Interfaces
  ansible.builtin.import_role:
    name: undercluster
    tasks_from: interfaces     # roles/undercluster/tasks/interfaces.yml
  tags: [interfaces]
```

## Variables and their precedence

A variable can be set in several places. The more specific wins:

1. `roles/common/defaults/main.yml`: the defaults (lowest);
2. `inventory/<site>/group_vars/...`: the site description;
3. host variables in `hosts.yml`;
4. `-e name=value` on the command line: always wins.

So `-e kmv_keep=true` overrides everything, for one run.

Facts are variables Ansible gathers from a host, such as its CPU count and memory, read as
`ansible_facts.<name>`.

## Tags: running part of a playbook

Every check group is a **tag**:

```bash
ansible-playbook -i inventory/mysite undercluster.yml --tags interfaces,mesh
ansible-playbook -i inventory/mysite kmetal.yml --skip-tags e2e,e2e-tenants
ansible-playbook -i inventory/mysite undercluster.yml --list-tags     # what exists
```

Tasks tagged `always` (preparation, connectivity, summary, cleanup) run whatever you select.

## Templates: Jinja

Values between `{{ }}` are **Jinja** expressions, evaluated when the task runs:

```yaml
msg: "{{ inventory_hostname }}: {{ ansible_facts.processor_nproc }} CPU"
```

`|` applies a **filter**: `cidr | kmv_contains(ip)` asks the project's filter whether the CIDR
contains the address. The checks build their verdicts with longer Jinja blocks
(`{%- for ... -%}`); each block ends with `{{ v }}`, the list of verdicts.

## Conditions, loops, retries

| Keyword | Meaning | Example in this project |
|---|---|---|
| `when:` | Run the task only if the condition is true | the tunnel test runs only on the two chosen nodes |
| `loop:` | Run the task once per item; the item is `item`, or the name set in `loop_control.loop_var` | one `can-i` probe per action |
| `until:` + `retries:` + `delay:` | Repeat the task until the condition is true, at most `retries` times, `delay` seconds apart | wait for a pod to finish, a claim to be Ready, a cluster to come up |
| `failed_when: false` | Never mark the task failed: the check decides with a verdict instead | every probe |
| `ignore_errors: true` | Keep going after a failure, but keep the `failed` flag for later tests | creating test objects |

## Running on another host: `delegate_to`

A task can run on a host other than the play's own:

```yaml
- name: nodes | tunnel interface on the network nodes (SSH)
  ansible.builtin.command: ip link show dev {{ _nd_tif }}
  delegate_to: "{{ item }}"            # a node, while the play runs on localhost
  loop: "{{ network_nodes }}"
```

`kmetal.yml` uses this for its few SSH checks, and to run tenant `kubectl` on a control plane
when the tenant API is not reachable from the bootstrap machine.

## Blocks: grouping and always-run steps

```yaml
- block:
    - ...create the tunnel, ping across...
  always:
    - ...delete the tunnel...
```

The `always` part runs even when a task in the block fails. It does **not** run when you press
Ctrl-C: then use `cleanup.yml` with the run ID printed at the start.

## `become`: root on the nodes

`become: true` runs the tasks through `sudo -n` (`ansible.cfg` sets the method). The SSH user
needs passwordless sudo, or `ansible_user: root`.

## Reading the output

```
TASK [undercluster : interfaces | verdicts] **********************************
  PASS worker-01: mgmt bond0.104 VLAN 104 MTU 9100 10.0.0.12/24 (on bond0)
  FAIL worker-02: provider provider (bond0.106): carries IPv4 10.0.6.13: ...
ok: [worker-01]
ok: [worker-02]
```

- `TASK [role : name]` is the step being run.
- The indented `PASS`, `WARN`, `FAIL` and `INFO` lines are the verdicts.
- `ok`, `changed`, `skipping` and `failed` describe the task itself, not the check: a probe that
  finds a problem still reports `ok`, and the verdict says FAIL.
- `PLAY RECAP` at the end counts tasks per host. The project's own summary, just before it,
  counts verdicts.

`-v` adds detail for each task, and `-vvv` shows the SSH connections, which helps when a node is
unreachable.

## Glossary

| Term | Meaning |
|---|---|
| Controller | The machine running `ansible-playbook` (the bootstrap machine) |
| Inventory | Hosts, groups and their variables |
| Play | Hosts plus tasks, inside a playbook |
| Task | One module call |
| Module | A small program Ansible runs on a host (`command`, `setup`, `kubernetes.core.k8s`) |
| Role | A reusable directory of tasks and defaults |
| Collection | A package of modules and plugins (`kubernetes.core`) |
| Fact | A variable gathered from a host |
| Tag | A label used to run or skip tasks |
| `become` | Privilege escalation (sudo) |
| `delegate_to` | Run one task on another host |
| `register` | Store a task's result in a variable |
