# -*- coding: utf-8 -*-
# Documentation only: the work is done on the controller by action_plugins/kmv_record.py.

DOCUMENTATION = r'''
---
module: kmv_record
short_description: Print and record the verdicts of a kmetal-validate check
description:
  - Prints one line per verdict (C(PASS), C(WARN), C(FAIL) or C(INFO)) and appends the
    verdicts, tagged with the check group, to the host fact C(kmv_results).
  - The summary (roles/common/tasks/summary.yml) reads C(kmv_results) from every host.
  - Never contacts the host and never reports a change.
options:
  group:
    description: Check group the verdicts belong to (also the group's tag).
    type: str
    required: true
  verdicts:
    description: List of C({level, msg}) dictionaries.
    type: list
    elements: dict
    required: true
'''

EXAMPLES = r'''
- name: hardware | verdicts
  kmv_record:
    group: hardware
    verdicts:
      - {level: PASS, msg: "worker-01: 16 CPU"}
      - {level: WARN, msg: "worker-02 below the lab minimum: 4 CPU < 8"}
'''

RETURN = r'''
msg:
  description: The printed lines.
  type: list
  returned: always
'''
