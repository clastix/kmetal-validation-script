# Interpreting results

[← Index](README.md)

The most frequent FAIL and WARN messages, what usually causes them, and how to fix them. Each
group's full rules are in [Under cluster checks](undercluster-checks.md) and
[Platform checks](kmetal-checks.md).

## Under cluster

| Message (abridged) | Likely cause | Fix |
|---|---|---|
| `cannot run 'sudo -n bash' over SSH` | Key not authorised, wrong `SSH_USER`, sudo asks for a password, or the host key changed | Test `ssh <user>@<mgmt ip> sudo -n true`; adjust `SSH_OPTS` (jump host, key) or the sudoers rule |
| `<net> interface <if> not found` | `NET_IFACE` misspelt, or the VLAN not configured on that node | Compare with `ip -br link`; fix netplan or `setup.env` |
| `expected VLAN <id>, found …` | Wrong VLAN on the sub-interface, or the interface is not a VLAN device | Correct the netplan `vlans:` entry, or leave `NET_VLAN` empty for a non-VLAN interface |
| `expected <ip>/<len>, has: …` | Address or prefix differs from the plan | Fix the address, or the `NODES` / `NET_CIDR` entry |
| `provider … carries IPv4` | An address left on the provider interface | Remove it from netplan; Kube-OVN takes the interface whole |
| `node networks not declared in netplan` | Interface created by hand; lost at reboot | Declare it in netplan |
| `provider interfaces … not in netplan` (INFO) | kMetal manages the provider network | Nothing to do, unless kMetal is not installed |
| `-> <peer> on <net>: unreachable` | Switch port not trunking the VLAN, wrong address, or a firewall | Check the switch configuration for that VLAN on both ports |
| `MTU … does not pass end to end` | Switch or peer below the declared MTU | Raise the MTU along the path, or lower `NET_MTU` and the interface MTU |
| `<net> reaches the internet; only mgmt should` | A default route or policy route on a non-management network | Remove the route; tenant egress must leave through OVN only |
| `kernel modules not available: geneve …` | Minimal kernel without the module package | Install the distribution's extra modules package (e.g. `linux-modules-extra-$(uname -r)`) |
| `… tunnel … no traffic` | UDP between overlay addresses filtered, or overlay routing broken | Allow UDP 6081 (and the test port) between overlay addresses |
| `swap is on` / `net.ipv4.ip_forward=0` | Host not prepared for Kubernetes | `swapoff -a` and remove swap from fstab; set the sysctl persistently |
| `/dev/kvm missing` | Virtualisation disabled in BIOS, or the kvm module not loaded | Enable VT-x/AMD-V; `modprobe kvm_intel` (or `kvm_amd`) |
| `fs.inotify.max_user_instances … < 8192` | Kernel default (128) | `sysctl fs.inotify.max_user_instances=8192` and persist it in `/etc/sysctl.d/` |

## Platform

| Message (abridged) | Likely cause | Fix |
|---|---|---|
| `… exclude-from-external-load-balancers is set …` | kubeadm labels control planes this way by default; MetalLB speakers then do not announce from them | `kubectl label node <n> node.kubernetes.io/exclude-from-external-load-balancers-` |
| `no Ready MetalLB speaker on this control plane` (WARN) | Speaker DaemonSet not scheduled there (label, taint or node selector) | `kubectl get ds -n kmetal-metallb`; check tolerations and the exclusion label |
| `component X is Pending/Failed: …` | The first non-Ready component blocks the ones after it | Read the message; check the Flux object of that component in `kmetal-flux` |
| `operator not found` | Installed under another release or namespace | Set `KMETAL_RELEASE` / `KMETAL_NAMESPACE` in `setup.env` |
| `operator chart is X; this script validates 1.0.x` (WARN) | Different kMetal version | Results may not match that version's rules; interpret them with care |
| `loadBalancer.<role> … is not in any IPAddressPool` | Spec and MetalLB pools drifted | Let the operator reconcile, or fix the spec |
| `Service from pool … got no EXTERNAL-IP` | Pool exhausted, or the MetalLB controller is unhealthy | `kubectl get ipaddresspool -n kmetal-metallb -o yaml`; free addresses |
| `no VolumeSnapshotClass for driver …` | CSI driver without snapshot support, or the class is missing | Install the snapshot class for the platform storage driver |
| `StorageProfile … has no snapshotClass` | CDI does not recognise the provisioner | Patch the StorageProfile with the snapshot class and the clone strategy |
| `volume restored from a … snapshot is not usable` | The driver restores snapshots read-only | FAIL when the StorageProfile clones by snapshot: use another backend for the platform class, or a `copy` clone strategy |
| `<class>: PVC/pod smoke test did not complete` | Provisioning failure, or the pod cannot be scheduled (e.g. a node-local class on nodes without its path) | Read the PVC events printed under the message |
| `no node labelled node-role.kubernetes.io/compute` | Labels not applied; the platform still reports healthy | `kubectl label node <n> node-role.kubernetes.io/compute=` |
| `ovn.kubernetes.io/external-gw=true missing` | Operator 1.0.0 does not set it | `kubectl label node <n> ovn.kubernetes.io/external-gw=true` |
| `kube-ovn/role=master missing on a central node` | Operator 1.0.0 does not set it | `kubectl label node <n> kube-ovn/role=master` |
| `control plane labelled kmetal.io/ovn` (WARN) | Kube-OVN per-node components scheduled on a control plane without overlay | `kubectl label node <n> kmetal.io/ovn-` |
| `worker listed in centralNodes` (WARN) | ovn-central placed on workers | Prefer the three control planes in `centralNodes` |
| `N central node(s): fill centralNodes to three` (WARN) | Raft cannot tolerate a failure | List three nodes |
| `provider … interface … missing` | That network node lacks the NIC/VLAN | Configure it, or add the node to `excludeNodes` |
| `… overlaps provider subnet …` | Two provider networks share addresses | Give each provider network its own block |
| `frames would be tagged twice` (WARN) | Kernel VLAN device plus a `vlanID` in the subnet | Set `vlanID: 0` for kernel VLAN sub-interfaces |
| `a … member created a namespace with no capsule.clastix.io/tenant label` | `multiTenancy.users` does not match Capsule's configuration | Align `spec.multiTenancy.users` |
| `osArtifact tag X: OSArtifact … Error` | Golden image build failed | Rebuild the OSArtifact; that version is unusable until it is Ready with a Bound golden PVC |

## End-to-end

| Message (abridged) | Likely cause | Fix |
|---|---|---|
| `end-to-end tests skipped: N failures above` | An earlier group failed | Fix those first, or use `--force-e2e` |
| `the owner of <t1> is allowed on tenant <t2>: …` | A ClusterRole or RoleBinding grants tenant owners rights beyond their own tenant (e.g. a broad aggregated role, or a binding to the whole tenant group) | Find the binding with `kubectl auth can-i --list --as <owner>`; scope it to the tenant's own namespaces. Multi-tenancy is broken until fixed |
| `the owner of <t> cannot read pods in its own environment` (WARN) | Capsule does not grant the owner's admin role in its namespaces | Check the Tenant's `owners` and Capsule's additional role bindings |
| `isolation <x> -> <y> not probed` (INFO) | Both clusters use the same worker addresses | Expected for one direction; keep different worker counts so the other direction is probed |
| `e2e needs a multiTenancy Group system:serviceaccounts:<namespace>` | Tenancy uses users or another group form | Add such a group to `spec.multiTenancy.users` |
| `owner of <t> cannot create environment` | Capsule rejected the owner, e.g. a forced namespace prefix or a namespace quota | Check the Tenant and the CapsuleConfiguration users |
| `subnetclaim primary not Ready` | VPC not ready, or no provider subnet capacity | `kubectl get vpcclaim,subnetclaim -n <environment> -o yaml` |
| `Cluster … not available` | Image, storage, network or capacity problem | The printed machines, VMIs and events point to the stage: VMI Pending means scheduling or storage; Running without a node means network or bootstrap |
| `tenant API … unreachable from <node>` | Tenant VLAN or the MetalLB L2 advertisement | Check the tenant pool's L2Advertisement and the tenant VLAN on the control planes |
| `nodes not Ready … (no CNI?)` | The tenant CNI was not delivered | `kubectl get clustersummaries -n <environment>` |
| `no egress from the tenant cluster` | SNAT, provider gateway or upstream routing | Check the `external` EipClaim, the provider gateway, and upstream NAT for the provider subnet |
| `Service … got no EXTERNAL-IP` (EIP) | Missing `loadBalancerClass: kmetal`, or the claim is not Ready | `kubectl get eipclaims -n kv-<id>-a` |
| `… reaches …'s worker …: VPCs are not isolated` | VPC isolation broken, between environments (`e2e`) or between tenants (`e2e-tenants`) | Escalate: tenant traffic crosses VPCs |
