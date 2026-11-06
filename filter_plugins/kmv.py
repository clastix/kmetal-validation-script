# -*- coding: utf-8 -*-
"""Jinja filters used by the kmetal-validate playbooks.

IPv4 arithmetic (CIDRs, MetalLB "a-b" ranges, Kube-OVN "a..b" ranges, single addresses)
and a few parsers that would be unreadable in Jinja. Each filter is a short plain function;
selftest.yml shows examples.
"""

import ipaddress
import json
import re


# --- IPv4 ------------------------------------------------------------------------------

def _lohi(r):
    """(lo, hi) integers for 'a-b', 'a..b', 'a/len' or 'a'. Raises ValueError if invalid."""
    r = str(r).replace(' ', '').replace('..', '-')
    if '-' in r:
        a, b = r.split('-', 1)
        return int(ipaddress.IPv4Address(a)), int(ipaddress.IPv4Address(b))
    if '/' in r:
        net = ipaddress.IPv4Network(r, strict=False)
        return int(net.network_address), int(net.broadcast_address)
    n = int(ipaddress.IPv4Address(r))
    return n, n


def kmv_valid_ip(s):
    """True for a dotted IPv4 address."""
    try:
        ipaddress.IPv4Address(str(s))
        return True
    except ValueError:
        return False


def kmv_valid_cidr(s):
    """True for a.b.c.d/len (host bits may be set)."""
    s = str(s)
    if '/' not in s:
        return False
    try:
        ipaddress.IPv4Network(s, strict=False)
        return True
    except ValueError:
        return False


def kmv_cidr_canonical(s):
    """True when the CIDR is a network address (no host bits set)."""
    try:
        ipaddress.IPv4Network(str(s), strict=True)
        return '/' in str(s)
    except ValueError:
        return False


def kmv_overlaps(a, b):
    """True when two ranges, CIDRs or addresses share at least one address."""
    try:
        a1, a2 = _lohi(a)
        b1, b2 = _lohi(b)
    except ValueError:
        return False
    return a1 <= b2 and b1 <= a2


def kmv_within(inner, outer):
    """True when every address of inner lies inside outer."""
    try:
        a1, a2 = _lohi(inner)
        b1, b2 = _lohi(outer)
    except ValueError:
        return False
    return a1 >= b1 and a2 <= b2


def kmv_contains(rng, ip):
    """True when the range or CIDR contains the address."""
    return kmv_within(kmv_ip(ip), rng)


def kmv_same_range(a, b):
    """True when two ranges cover the same addresses (10.0.0.0/30 == 10.0.0.0-10.0.0.3)."""
    try:
        return _lohi(a) == _lohi(b)
    except ValueError:
        return False


def kmv_host(cidr, offset=1):
    """Address at offset from the network address: '10.0.0.0/24' | kmv_host(1) -> 10.0.0.1."""
    net = ipaddress.IPv4Network(str(cidr), strict=False)
    return str(net.network_address + int(offset))


def kmv_ip(addr):
    """Address part of 'a.b.c.d/len'."""
    return str(addr).split('/')[0]


def kmv_prefix(addr, cidr):
    """Prefix length of a node address: its own /len, else the network's."""
    addr = str(addr)
    return addr.split('/')[1] if '/' in addr else str(cidr).split('/')[1]


# --- Kubernetes objects ------------------------------------------------------------------

def kmv_condition(obj, ctype='Ready'):
    """Status of the first condition of that type: 'True', 'False', 'Unknown' or ''."""
    for c in ((obj or {}).get('status') or {}).get('conditions') or []:
        if c.get('type') == ctype:
            return str(c.get('status', ''))
    return ''


def kmv_condition_message(obj, ctype='Ready'):
    """Message of the first condition of that type, or ''."""
    for c in ((obj or {}).get('status') or {}).get('conditions') or []:
        if c.get('type') == ctype:
            return str(c.get('message', ''))
    return ''


def kmv_ready(obj):
    """Ready condition True, or .status.ready true."""
    st = (obj or {}).get('status') or {}
    return kmv_condition(obj, 'Ready') == 'True' or st.get('ready') is True


def kmv_pod_ok(pod):
    """Succeeded, or Running with every container ready."""
    st = (pod or {}).get('status') or {}
    if st.get('phase') == 'Succeeded':
        return True
    return st.get('phase') == 'Running' and all(
        c.get('ready') for c in st.get('containerStatuses') or [])


def kmv_table_col(text, column):
    """Value of a printer column in the first row of `kubectl get` table output.

    The column is located by its header's character offset, so multi-word headers and
    empty cells read the way the eye reads them.
    """
    lines = [ln for ln in str(text or '').splitlines() if ln.strip()]
    if len(lines) < 2:
        return ''
    head = lines[0]
    start = (' ' + head + ' ').find(' ' + column + ' ')
    if start < 0:
        return ''
    # the column ends where the next header starts (kubectl pads every column)
    end = len(lines[1])
    for i in range(start + len(column), len(head)):
        if head[i] != ' ' and head[i - 1] == ' ':
            end = i
            break
    cell = lines[1][start:end].strip()
    return cell.split(' ')[0] if cell else ''


# --- nodes -------------------------------------------------------------------------------

def kmv_link(links, iface):
    """The entry of `ip -d -j link` for an interface, or {}."""
    for l in links or []:
        if l.get('ifname') == iface:
            return l
    return {}


def kmv_link_parent(links, iface):
    """Physical parent of an interface in `ip -d -j link` output, following VLAN links."""
    name = iface
    for _ in range(4):
        nxt = kmv_link(links, name).get('link')
        if not nxt:
            break
        name = nxt
    return name


def kmv_ipv4(addrs, iface, with_prefix=True):
    """IPv4 addresses of an interface in `ip -j addr` output."""
    out = []
    for a in addrs or []:
        if a.get('ifname') != iface:
            continue
        for i in a.get('addr_info') or []:
            if i.get('family') == 'inet':
                out.append('%s/%s' % (i['local'], i['prefixlen']) if with_prefix else i['local'])
    return out


def kmv_ping_loss(text):
    """Packet loss percentage from ping output, as a string; '100' when unreadable."""
    m = re.search(r'([0-9.]+)% packet loss', str(text or ''))
    return m.group(1) if m else '100'


def kmv_netplan_has(yaml_text, iface):
    """True when an interface appears as a key in `netplan get` output."""
    rx = re.compile(r'^\s+"?%s"?:' % re.escape(iface), re.M)
    return bool(rx.search(str(yaml_text or '')))


def kmv_clusters_up(text, envs, keys):
    """Keys whose tenant Cluster is up, from `kubectl get clusters -o json`, a '---' line and
    `kubectl get machines -o json`.

    Up means: an Available or Ready condition is True, and at least `workers` Machines of
    the cluster are Running. envs: {key: {ns, cluster, workers}}.
    """
    parts = str(text or '').split('\n---\n')
    if len(parts) != 2:
        return []
    try:
        clusters = json.loads(parts[0]).get('items') or []
        machines = json.loads(parts[1]).get('items') or []
    except ValueError:
        return []
    up = []
    for k in keys or []:
        e = envs[k]
        c = next((c for c in clusters if c['metadata']['name'] == e['cluster']
                  and c['metadata']['namespace'] == e['ns']), None)
        if not c:
            continue
        if not any(kmv_condition(c, t) == 'True' for t in ('Available', 'Ready')):
            continue
        running = [m for m in machines if m['metadata']['namespace'] == e['ns']
                   and (m['metadata'].get('labels') or {}).get('cluster.x-k8s.io/cluster-name') == e['cluster']
                   and (m.get('status') or {}).get('phase') == 'Running']
        if len(running) >= int(e['workers']):
            up.append(k)
    return up


# --- misc --------------------------------------------------------------------------------

def kmv_seconds(v):
    """'30m' -> 1800, '1h' -> 3600, '90s' -> 90, '120' -> 120."""
    v = str(v).strip()
    mult = {'h': 3600, 'm': 60, 's': 1}.get(v[-1:])
    return int(v[:-1]) * mult if mult else int(v)


def kmv_joinc(items):
    """Comma-separated list."""
    return ', '.join(str(i) for i in items or [])


def kmv_version_status(version, target):
    """'match', 'prerelease' or 'other' for a chart version against the target release.

    target 1.0.1: '1.0.1' -> match, 'v1.0.1-rc10' or '1.0.1-rc10+abc' -> prerelease,
    anything else -> other.
    """
    v = str(version or '').lstrip('v').split('+')[0]
    if v == target:
        return 'match'
    if v.startswith(target + '-'):
        return 'prerelease'
    return 'other'


def kmv_artifact_for(names, tag):
    """First OSArtifact name built for a tag: v1.36.4 matches ...-v1364-..., ...-v1-36-4."""
    m = re.match(r'^v?(\d+)\.(\d+)\.(\d+)$', str(tag))
    if not m:
        return ''
    rx = re.compile(r'(^|-)v%s-?%s-?%s(-|$)' % m.groups())
    for n in names or []:
        if rx.search(str(n)):
            return n
    return ''


class FilterModule(object):
    def filters(self):
        return {name: fn for name, fn in globals().items()
                if name.startswith('kmv_') and callable(fn)}
