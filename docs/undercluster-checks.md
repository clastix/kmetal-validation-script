# Under cluster checks (`undercluster.yml`)

[← Index](README.md)

```bash
ansible-playbook -i inventory/<site> playbooks/undercluster.yml [--tags g1,g2] [--skip-tags g1,g2]
```

The playbook compares the real nodes with the inventory. It needs SSH and `sudo -n` on every
node. A kubeconfig is optional: when the under cluster API answers, the node list and the
address plan are also checked against the cluster and the `KMetal` resource.

A short version of each group's section is built in:
`ansible-playbook playbooks/help.yml -e cmd=undercluster [-e group=<group>]`.

## How it works

The playbook has four plays:

1. **Prepare, on the bootstrap machine** (`roles/common/tasks/prepare.yml`):
   - validate the inventory ([Configuration](configuration.md#validation)) and print the node
     table;
   - read the `KMetal` resource with `kubectl get km` when the API answers;
   - run the `topology` and `addressing` groups, which need no SSH.
2. **Check the nodes**, all in parallel, as root through `become` (`sudo -n`). The first group,
   `connectivity`, gathers the facts every later group evaluates:
   - Ansible's own facts (`setup` module, `min` and `hardware` subsets): OS, kernel, CPU count,
     memory, mounts, swap;
   - `ip -d -j link show` and `ip -j addr show`, parsed as JSON;
   - one shell task printing `key=value` lines: sysctls (`fs.inotify.max_user_instances`,
     `net.ipv4.ip_forward`), whether `br_netfilter` is loaded, presence of `conntrack`, `socat`,
     `curl`, `ping` and `netplan`, NTP state, `/dev/kvm` and the kvm module, availability of
     the `geneve`, `vxlan` and `openvswitch` modules, and every link speed;
   - `netplan get`.

   Most groups evaluate these facts with Jinja on the controller. `mesh`, `internet` and
   `encap` run active probes on the nodes.
3. **Summary**, on the bootstrap machine.

A node that fails SSH or sudo is reported once by `connectivity` and dropped from the rest of the
play (`meta: end_host`); the other nodes go on.

## Groups

### connectivity (always runs)

| Check | How | Severity |
|---|---|---|
| SSH and root access | The `setup` module runs through `sudo -n`; an unreachable node or a sudo password prompt fails it | FAIL; the node is dropped afterwards |
| Hostname | Compared with the inventory name | INFO when different |

### topology

| Check | How | Severity |
|---|---|---|
| Minimum lab | Counts the `control_plane` and `workers` hosts: at least 1 and 2 | FAIL |
| Recommended size | Fewer than 3 control planes, or an even number (etcd quorum) | WARN |
| Registered nodes | When a kubeconfig works: each node exists in `kubectl get nodes` and its InternalIP equals the `mgmt` address; cluster nodes missing from the inventory are reported | WARN |
| MetalLB exclusion label | When a kubeconfig works: no control plane carries `node.kubernetes.io/exclude-from-external-load-balancers`, so MetalLB speakers can announce from it. kMetal 1.0.1 removes it, so its presence means the operator did not | FAIL |

### addressing

| Check | How | Severity |
|---|---|---|
| Node networks overlap | pairwise comparison of every `kmv_networks` CIDR | FAIL |
| Cluster networks | when the `KMetal` resource is reachable, every node network is compared with `kubeOVN.podCIDR`, `serviceCIDR`, `100.64.0.0/16` and every provider subnet | FAIL |
| MetalLB ranges | `loadBalancer.tenantControlPlanes` must lie inside `tenant` and `loadBalancer.management` inside `mgmt`, and neither may contain a node address | FAIL |

### hardware

| Check | How | Severity |
|---|---|---|
| Lab minimum | CPUs ≥ 8, memory ≥ 16 GiB, root filesystem ≥ 100 GB, link speed ≥ 1 Gb/s. The speed is read from the physical parent of the `mgmt` interface, following VLAN links | WARN |
| Production profile | Below 16 CPU, 64 GB RAM, 500 GB or 10 Gb/s | INFO |
| Unknown speed | `/sys/class/net/<if>/speed` not readable | INFO |

### os

| Check | How | Severity |
|---|---|---|
| Swap off | no active swap (`SwapTotal` is 0) | FAIL |
| IP forwarding | `net.ipv4.ip_forward=1` | FAIL |
| `ping` present | needed by the mesh checks | FAIL |
| Virtualisation (workers) | `/dev/kvm` exists and `kvm_intel` or `kvm_amd` is loaded | FAIL |
| inotify | `fs.inotify.max_user_instances` ≥ 8192: the platform plus one control plane per tenant exceed the default, and controllers crash-loop without a clear error | WARN |
| `br_netfilter` | `/proc/sys/net/bridge/bridge-nf-call-iptables` exists | WARN |
| `conntrack`, `socat` | installed (kubeadm prerequisites) | WARN |
| Time | `timedatectl` reports NTP synchronised | WARN |
| `curl` | installed (needed by the internet checks) | WARN |

### interfaces

For every node and every network of `kmv_networks`, from the gathered `ip` JSON:

| Check | How | Severity |
|---|---|---|
| Declared address but no interface | `ifname` not found | FAIL; WARN for an optional network |
| Link state | flags include `UP` and `LOWER_UP` | FAIL |
| VLAN | `linkinfo.info_kind == vlan` and `info_data.id` equals `vlan` (skipped when absent or 0) | FAIL |
| MTU | equals `mtu` when set | FAIL |
| Address | the expected `ip/prefix` is among the interface's IPv4 addresses | FAIL |
| Extra addresses | e.g. a kube-vip VIP on `mgmt` | INFO |
| Network not in the node's `kmv_addresses` | `overlay` on a control plane: INFO (expected). Optional network: INFO. Anything else: FAIL | as stated |

For every provider network, on workers:

| Check | How | Severity |
|---|---|---|
| Present and up | as above | FAIL; INFO when absent and the `KMetal` resource sets `autoCreateVLANSubinterface` for it |
| VLAN | equals the provider's `vlan` | FAIL |
| No address | no IPv4 on the interface | FAIL |
| On control planes | present: reported so it can be listed in `excludeNodes` | INFO |

### netplan

Reads the `netplan get` output and looks for each interface name as a key.

| Check | Severity |
|---|---|
| Node-network interface (`mgmt`, `tenant`, `overlay`, …) not declared: it is lost at reboot | WARN |
| Provider interface not declared, and the `KMetal` resource names it: created and managed by the platform | INFO |
| Provider interface not declared, other cases: expected when kMetal is already installed | INFO |
| netplan not installed | INFO |

### mesh

Each node pings every other reachable node's address on each network both have, binding to that
network's interface. The nodes run in parallel; one shell task per node runs all its pings:

```bash
ping -c3 -i0.2 -W1 -q -I <iface> <peer>                     # loss
ping -c2 -i0.2 -W1 -q -M do -s <MTU-28> -I <iface> <peer>   # when mtu > 1500
```

| Result | Severity |
|---|---|
| 100% loss | FAIL |
| Partial loss | WARN |
| Jumbo frame does not pass | WARN |

### internet

Per node, for each network the node has an address on:

```bash
curl -sS -o /dev/null --max-time 6 --interface <iface> <kmv_internet_probe_url>
ping -c2 -W2 -q -I <iface> <kmv_internet_probe_ip>
getent hosts <kmv_dns_probe>
```

Binding to the interface means the probe only succeeds if that network has its own route out.

| Check | Severity |
|---|---|
| DNS resolution fails | FAIL |
| `kmv_internet_network` cannot fetch the URL | FAIL |
| `kmv_internet_network` gets no ICMP reply (often filtered) | INFO |
| Any other network reaches the internet | WARN |

### encap

| Check | How | Severity |
|---|---|---|
| Kernel modules | `geneve`, `vxlan` and `openvswitch` loaded or loadable (`modprobe -n`). The tunnel type comes from `kubeOVN.tunnelType` (default Geneve) | FAIL for the tunnel type or `openvswitch` on an overlay node; WARN for the other; INFO on nodes without overlay |
| Real tunnel | See below | FAIL |

The tunnel test uses the first two reachable nodes with an overlay address. Both ends are built
in the same task, in parallel:

```bash
# on node A (node B mirrors it with .2 and A's address)
ip link add kvtest0 type geneve id 4242 remote <B overlay IP> dstport 6090
ip addr add 169.254.250.1/30 dev kvtest0 && ip link set kvtest0 up
ping -c3 169.254.250.2      # on node A only
ip link del kvtest0         # always, on both
```

It proves that the kernel encapsulates, and that UDP traffic between the overlay addresses is
not filtered. It uses a separate port, `kmv_encap_test_port`, so it never collides with
Kube-OVN's own tunnel on 6081. The device is deleted in an `always` block; after Ctrl-C,
`cleanup.yml` deletes it on every node.
