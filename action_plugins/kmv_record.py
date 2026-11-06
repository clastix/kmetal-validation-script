# -*- coding: utf-8 -*-
"""Action plugin behind the `kmv_record` task (documentation: library/kmv_record.py).

Prints the verdicts of a check and appends them to the host fact `kmv_results`, which the
summary play reads. Runs on the controller only and never contacts the host.
"""

from ansible import constants as C
from ansible.errors import AnsibleActionFail
from ansible.plugins.action import ActionBase
from ansible.utils.display import Display

display = Display()

LEVELS = ('PASS', 'WARN', 'FAIL', 'INFO')
COLORS = {'PASS': C.COLOR_OK, 'WARN': C.COLOR_WARN, 'FAIL': C.COLOR_ERROR, 'INFO': None}


class ActionModule(ActionBase):
    TRANSFERS_FILES = False
    _requires_connection = False

    def run(self, tmp=None, task_vars=None):
        result = super(ActionModule, self).run(tmp, task_vars)
        task_vars = task_vars or {}
        group = self._task.args.get('group')
        verdicts = self._task.args.get('verdicts') or []
        if not group:
            raise AnsibleActionFail('kmv_record: group is required')
        if not isinstance(verdicts, list):
            raise AnsibleActionFail('kmv_record: verdicts must be a list')

        clean = []
        for v in verdicts:
            if not isinstance(v, dict) or v.get('level') not in LEVELS:
                raise AnsibleActionFail('kmv_record: invalid verdict %r' % (v,))
            clean.append({'group': group, 'level': v['level'], 'msg': str(v.get('msg', ''))})

        previous = (task_vars.get('ansible_facts') or {}).get('kmv_results') or []
        # one coloured line per verdict, printed as the task runs
        for v in clean:
            display.display('  %-4s %s' % (v['level'], v['msg']), color=COLORS[v['level']])
        result['changed'] = False
        result['msg'] = '%d verdict(s)' % len(clean)
        result['ansible_facts'] = {'kmv_results': list(previous) + clean}
        return result
