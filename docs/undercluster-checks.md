# Under cluster checks (`undercluster`)

[← Index](README.md)

```bash
./kmetal-validate [-e setup.env] undercluster [--only g1,g2] [--skip g1,g2]
```

The command compares the real nodes with `setup.env`. It needs SSH and `sudo -n` on every node.
A kubeconfig is optional: when the under cluster API answers, the node list and the address plan
are also checked against the cluster and the `KMetal` resource.

A short version of each group's section is built into the script:
`./kmetal-validate undercluster help [group]`.

## How it works

1. **Load and validate `setup.env`** ([Configuration](configuration.md#validation)), then print
   the node table.
2. **Collect facts in parallel.** One SSH session per node runs a read-only script as root. It
   prints `key=value` lines:
   - hostname, kernel, OS;
   - CPU count, memory, root filesystem size, swap;
   - sysctls (`fs.inotify.max_user_instances`, `net.ipv4.ip_forward`);
   - whether `br_netfilter` is loaded;
   - presence of `conntrack`, `socat`, `curl`, `ping` and `netplan`;
   - NTP state, `/dev/kvm` and the kvm module;
   - availability of the `geneve`, `vxlan` and `openvswitch` modules;
   - every link speed;
   - `ip -d -j link show` and `ip -j addr show`, base64-encoded;
   - `netplan get`, base64-encoded.
3. **Evaluate the facts locally** with `jq`. Most groups below need no further contact with the
   nodes.
4. **Run active probes** (`mesh`, `internet`, `encap`), again in parallel, one SSH session per
   node.

A node that fails the SSH and sudo step is reported once and skipped by every later group.

## Groups

### connectivity

| Check | How | Severity |
|---|---|---|
| SSH and root access | The fact script must run through `$SSH_SUDO bash` and report `uid=0` | FAIL; the node is skipped afterwards |
| Hostname | Compared with the `NODES` name | INFO when different |

### topology

| Check | How | Severity |
|---|---|---|
| Minimum lab | Counts the `cp` and `worker` rows: at least 1 and 2 | FAIL |
| Recommended size | Fewer than 3 control planes, or an even number (etcd quorum) | WARN |
| Registered nodes | When a kubeconfig works: each node exists in `kubectl get nodes` and its InternalIP equals the `mgmt` address; cluster nodes missing from `setup.env` are reported | WARN |
| MetalLB exclusion label | When a kubeconfig works: no control plane carries `node.kubernetes.io/exclude-from-external-load-balancers`, so MetalLB speakers can announce from it | FAIL |

### hardware

| Check | How | Severity |
|---|---|---|
| Lab minimum | `nproc` ≥ 8, `MemTotal` ≥ 16 GiB, root filesystem ≥ 100 GB, link speed ≥ 1 Gb/s. The speed is read from the physical parent of the `mgmt` interface, following VLAN links | WARN |
| Production profile | Below 16 CPU, 64 GB RAM, 500 GB or 10 Gb/s | INFO |
| Unknown speed | `/sys/class/net/<if>/speed` not readable | INFO |

### os

| Check | How | Severity |
|---|---|---|
| Swap off | `swapon --show` is empty | FAIL |
| IP forwarding | `net.ipv4.ip_forward=1` | FAIL |
| `ping` present | needed by the mesh checks | FAIL |
| Virtualisation (workers) | `/dev/kvm` exists and `kvm_intel` or `kvm_amd` is loaded | FAIL |
| inotify | `fs.inotify.max_user_instances` ≥ 8192: the platform plus one control plane per tenant exceed the default, and controllers crash-loop without a clear error | WARN |
| `br_netfilter` | `/proc/sys/net/bridge/bridge-nf-call-iptables` exists | WARN |
| `conntrack`, `socat` | installed (kubeadm prerequisites) | WARN |
| Time | `timedatectl` reports NTP synchronised | WARN |
| `curl` | installed (needed by the internet checks) | WARN |

### interfaces

For every node and every network in `NETWORKS`, from the collected `ip` JSON:

| Check | How | Severity |
|---|---|---|
| Declared address but no interface | `ifname` not found | FAIL; WARN for an optional network |
| Link state | flags include `UP` and `LOWER_UP` | FAIL |
| VLAN | `linkinfo.info_kind == vlan` and `info_data.id` equals `NET_VLAN` (skipped when empty or 0) | FAIL |
| MTU | equals `NET_MTU` when set | FAIL |
| Address | the expected `ip/prefix` is among the interface's IPv4 addresses | FAIL |
| Extra addresses | e.g. a kube-vip VIP on `mgmt` | INFO |
| No address declared (`-`) | `overlay` on a control plane: INFO (expected). Optional network: INFO. Anything else: FAIL | as stated |

For every provider network, on workers:

| Check | How | Severity |
|---|---|---|
| Present and up | as above | FAIL |
| VLAN | equals `PROV_VLAN` | FAIL |
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

### addressing

| Check | How | Severity |
|---|---|---|
| Node networks overlap | pairwise comparison of every `NET_CIDR` | FAIL |
| Cluster networks | when the `KMetal` resource is reachable, every node network is compared with `kubeOVN.podCIDR`, `serviceCIDR`, `100.64.0.0/16` and every provider subnet | FAIL |
| MetalLB ranges | `loadBalancer.tenantControlPlanes` must lie inside `tenant` and `loadBalancer.management` inside `mgmt`, and neither may contain a node address | FAIL |

### mesh

Each node pings every other node's address on each network both have, binding to that
network's interface. The nodes run in parallel:

```bash
ping -c3 -i0.2 -W1 -q -I <iface> <peer>               # loss
ping -c2 -i0.2 -W1 -q -M do -s <MTU-28> -I <iface> <peer>   # when NET_MTU > 1500
```

| Result | Severity |
|---|---|
| 100% loss | FAIL |
| Partial loss | WARN |
| Jumbo frame does not pass | WARN |

### internet

Per node, for each network the node has an address on:

```bash
curl -sS -o /dev/null --max-time 6 --interface <iface> $INTERNET_PROBE_URL
ping -c2 -W2 -q -I <iface> $INTERNET_PROBE_IP
getent hosts $DNS_PROBE
```

Binding to the interface means the probe only succeeds if that network has its own route out.

| Check | Severity |
|---|---|
| DNS resolution fails | FAIL |
| `NET_INTERNET` cannot fetch the URL | FAIL |
| `NET_INTERNET` gets no ICMP reply (often filtered) | INFO |
| Any other network reaches the internet | WARN |

### encap

| Check | How | Severity |
|---|---|---|
| Kernel modules | `geneve`, `vxlan` and `openvswitch` loaded or loadable (`modprobe -n`). The tunnel type comes from `kubeOVN.tunnelType` (default Geneve) | FAIL for the tunnel type or `openvswitch` on an overlay node; WARN for the other; INFO on nodes without overlay |
| Real tunnel | See below | FAIL |

The tunnel test uses the first two nodes with an overlay address:

```bash
# on node A (node B mirrors it with .2 and A's address)
ip link add kvtest0 type geneve id 4242 remote <B overlay IP> dstport 6090
ip addr add 169.254.250.1/30 dev kvtest0 && ip link set kvtest0 up
ping -c3 169.254.250.2
ip link del kvtest0
```

It proves that the kernel encapsulates, and that UDP traffic between the overlay addresses is
not filtered. It uses a separate port, `ENCAP_TEST_PORT`, so it never collides with Kube-OVN's
own tunnel on 6081. The device is deleted immediately, and again by the cleanup stack if the run
is interrupted.
