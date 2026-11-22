# -*- coding: utf-8 -*-
"""Jinja tests (for select/reject) backed by the filters in filter_plugins/kmv.py.

    ranges | select('kmv_contains', ip)      ips | select('kmv_in', cidr)
    pods | select('kmv_pod_ok')
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'filter_plugins'))
import kmv as _f  # noqa: E402


class TestModule(object):
    def tests(self):
        return {
            'kmv_contains': _f.kmv_contains,
            'kmv_in': lambda ip, rng: _f.kmv_contains(rng, ip),
            'kmv_overlaps': _f.kmv_overlaps,
            'kmv_within': _f.kmv_within,
            'kmv_valid_ip': _f.kmv_valid_ip,
            'kmv_ready': _f.kmv_ready,
            'kmv_pod_ok': _f.kmv_pod_ok,
        }
