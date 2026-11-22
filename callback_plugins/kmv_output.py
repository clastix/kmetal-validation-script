# -*- coding: utf-8 -*-
"""Output of the kmetal-validate playbooks (stdout callback `kmv_output`, set in ansible.cfg).

It prints what a support engineer needs to follow a run:
  - a title per playbook and per play;
  - for each check group (= tag): a header with its purpose, how it checks and what its
    FAIL / WARN / INFO mean (the text of roles/common/vars/help.yml);
  - one line per real step of the group, saying what it reads, creates or deletes;
  - the verdicts (printed by the kmv_record task), then a tally of the group;
  - progress lines while waiting, diagnostics, the summary and the result.

Internal tasks (facts, evaluation, includes) are not shown. With -v or more, the standard
Ansible output is used instead, with every task and result.
"""

import os
import re

import yaml

from ansible import constants as C
from ansible import context
from ansible.plugins.callback.default import CallbackModule as DefaultCallback

DOCUMENTATION = r'''
name: kmv_output
type: stdout
short_description: kmetal-validate output, organised by check group
description:
  - Prints a header per check group (purpose, method, outcomes), one line per step, the
    verdicts and a tally. Falls back to the default output with -v.
extends_documentation_fragment:
  - default_callback
  - result_format_callback
'''

# tasks that never get a step line: their result is shown another way, or not at all
INTERNAL = ('set_fact', 'kmv_record', 'meta', 'include_tasks', 'import_tasks', 'include_role',
            'import_role', 'debug', 'fail', 'assert')

COLORS = {'title': C.COLOR_HIGHLIGHT, 'header': 'bright blue', 'step': None, 'dim': 'dark gray',
          'error': C.COLOR_ERROR, 'ok': C.COLOR_OK, 'warn': C.COLOR_WARN}


class CallbackModule(DefaultCallback):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'stdout'
    CALLBACK_NAME = 'kmv_output'

    def __init__(self, *args, **kwargs):
        super(CallbackModule, self).__init__(*args, **kwargs)
        self._help = self._load_help()
        self._group = None            # check group (tag) of the current task
        self._pending = None          # group whose header is not printed yet
        self._tally = {}              # level -> count, for the current group
        self._shown_steps = set()     # task uuids that already have a step line
        self._retry_seen = {}         # task uuid -> retries printed
        self._errors = 0              # unexpected task failures (not verdicts)
        self._summary_seen = False
        self._result_failed = False

    # --- helpers -------------------------------------------------------------------------

    @staticmethod
    def _load_help():
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            '..', 'roles', 'common', 'vars', 'help.yml')
        try:
            with open(path) as f:
                return yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError):
            return {}

    def _verbose(self):
        return self._display.verbosity > 0

    def _out(self, msg='', kind=None):
        self._display.display(msg, color=COLORS.get(kind))

    def _group_of(self, task):
        """The check group or section a task belongs to, from its tags."""
        tags = [t for t in (task.tags or []) if t != 'always']
        if 'e2e' in tags or 'e2e-tenants' in tags:
            return 'e2e'
        return tags[0] if tags else None

    def _help_text(self, group):
        texts = self._help.get('kmv_help', {})
        for cmd in ('undercluster', 'kmetal'):
            if '%s:%s' % (cmd, group) in texts:
                return texts['%s:%s' % (cmd, group)].rstrip().splitlines()
        section = self._help.get('kmv_help_sections', {}).get(group)
        return section.rstrip().splitlines() if section else None

    def _selected(self, tag):
        tags = context.CLIARGS.get('tags') or ['all']
        skip = context.CLIARGS.get('skip_tags') or []
        flat = [t for item in tags for t in str(item).split(',')]
        flat_skip = [t for item in skip for t in str(item).split(',')]
        return ('all' in flat or tag in flat) and tag not in flat_skip

    def _close_group(self):
        self._pending = None
        if self._group and sum(self._tally.values()):
            parts = []
            for level, word in (('PASS', 'passed'), ('WARN', 'warnings'), ('FAIL', 'failures'), ('INFO', 'info')):
                if self._tally.get(level):
                    parts.append('%d %s' % (self._tally[level], word))
            kind = 'error' if self._tally.get('FAIL') else ('warn' if self._tally.get('WARN') else 'ok')
            self._out('  => %s: %s' % (self._group, ', '.join(parts)), kind)
        self._tally = {}

    def _open_group(self, group):
        """Remember the new group; its header is printed with its first output."""
        self._close_group()
        self._group = group
        self._pending = group

    def _header(self):
        if not self._pending:
            return
        group, self._pending = self._pending, None
        self._out()
        if group == 'e2e':
            names = [g for g in ('e2e', 'e2e-tenants') if self._selected(g)] or ['e2e', 'e2e-tenants']
            first = True
            for g in names:
                lines = self._help_text(g) or [g]
                self._out(('>> ' if first else '   ') + lines[0], 'header')
                for line in lines[1:]:
                    self._out(line, 'dim')
                first = False
            self._out()
            return
        lines = self._help_text(group)
        if not lines:
            self._out('>> %s' % group, 'header')
            return
        self._out('>> ' + lines[0], 'header')
        for line in lines[1:]:
            self._out(line, 'dim')
        self._out()

    @staticmethod
    def _name(task):
        """Task name without Ansible's 'role : ' prefix."""
        return re.sub(r'^[\w.-]+ : ', '', task.get_name().strip())

    def _step_text(self, task):
        name = self._name(task)
        if ' | ' in name:
            prefix, rest = name.split(' | ', 1)
            if prefix.strip() == self._group:
                return rest
            return '%s: %s' % (prefix.strip(), rest)
        return name

    def _step(self, task):
        if task._uuid in self._shown_steps:
            return
        self._shown_steps.add(task._uuid)
        if task.action.split('.')[-1] in INTERNAL:
            return
        self._header()
        self._out('  > ' + self._step_text(task), 'step')

    def _verdicts(self, res):
        verdicts = res.get('verdicts', [])
        if verdicts:
            self._header()
        for v in verdicts:
            self._tally[v['level']] = self._tally.get(v['level'], 0) + 1
            self._out('  %-4s %s' % (v['level'], v['msg']),
                      {'PASS': 'ok', 'WARN': 'warn', 'FAIL': 'error'}.get(v['level']))

    def _msg_lines(self, msg):
        if isinstance(msg, (list, tuple)):
            return [str(m) for m in msg]
        return str(msg).splitlines() or ['']

    # --- playbook and plays --------------------------------------------------------------

    def v2_playbook_on_start(self, playbook):
        if self._verbose():
            return super(CallbackModule, self).v2_playbook_on_start(playbook)
        name = os.path.basename(playbook._file_name)
        purpose = self._help.get('kmv_help_playbooks', {}).get(name, '')
        self._out('kmetal-validate  playbooks/%s%s' % (name, ('  -  ' + purpose) if purpose else ''), 'title')

    def v2_playbook_on_play_start(self, play):
        if self._verbose():
            return super(CallbackModule, self).v2_playbook_on_play_start(play)
        self._close_group()
        self._group = None
        self._out()
        self._out('== %s ==' % play.get_name().strip(), 'title')

    def v2_playbook_on_task_start(self, task, is_conditional):
        if self._verbose():
            return super(CallbackModule, self).v2_playbook_on_task_start(task, is_conditional)
        group = self._group_of(task)
        if group and group != self._group:
            self._open_group(group)
        if group == 'summary':
            self._summary_seen = True

    def v2_playbook_on_include(self, included_file):
        if self._verbose():
            return super(CallbackModule, self).v2_playbook_on_include(included_file)

    def v2_playbook_on_no_hosts_matched(self):
        if self._verbose():
            return super(CallbackModule, self).v2_playbook_on_no_hosts_matched()
        self._out('  (no host matches this play: skipped)', 'dim')

    def v2_playbook_on_no_hosts_remaining(self):
        if self._verbose():
            return super(CallbackModule, self).v2_playbook_on_no_hosts_remaining()

    # --- results -------------------------------------------------------------------------

    def v2_runner_on_ok(self, result):
        task, res = result.task, result.result
        action = task.action.split('.')[-1]
        if self._verbose():
            super(CallbackModule, self).v2_runner_on_ok(result)
            if action == 'kmv_record':
                self._verdicts(res)
            return
        if action == 'kmv_record':
            self._verdicts(res)
            return
        self._step(task)
        if action == 'debug' and 'msg' in res:
            self._header()
            for line in self._msg_lines(res['msg']):
                self._out('    ' + line)
        elif action == 'assert' and res.get('msg') and task.args.get('success_msg'):
            self._out('  PASS ' + str(res['msg']), 'ok')

    def v2_runner_item_on_ok(self, result):
        if self._verbose():
            return super(CallbackModule, self).v2_runner_item_on_ok(result)
        self._step(result.task)

    def v2_runner_on_skipped(self, result):
        if self._verbose():
            return super(CallbackModule, self).v2_runner_on_skipped(result)

    def v2_runner_item_on_skipped(self, result):
        if self._verbose():
            return super(CallbackModule, self).v2_runner_item_on_skipped(result)

    def v2_runner_on_failed(self, result, ignore_errors=False):
        if self._verbose():
            return super(CallbackModule, self).v2_runner_on_failed(result, ignore_errors)
        task, res = result.task, result.result
        self._step(task)
        if ignore_errors:
            return            # handled by the check: its verdict reports it
        self._header()
        if self._group == 'summary' and task.action.split('.')[-1] == 'fail':
            self._result_failed = True
            self._close_group()
            self._group = None
            self._out()
            self._out('RESULT: FAILED - %s (exit code 2)' % res.get('msg', ''), 'error')
            return
        self._errors += 1
        msg = res.get('msg') or res.get('stderr') or res.get('reason') or 'failed'
        lines = self._msg_lines(msg)
        self._out('  ERROR on %s, step "%s": %s' % (result.host.get_name(), self._name(task), lines[0]), 'error')
        for line in lines[1:]:
            self._out('    ' + line, 'error')

    def v2_runner_item_on_failed(self, result):
        if self._verbose():
            return super(CallbackModule, self).v2_runner_item_on_failed(result)
        self._step(result.task)
        if result.task.ignore_errors:
            return
        self._header()
        self._errors += 1
        self._out('  ERROR on %s, step "%s": %s' % (result.host.get_name(), self._name(result.task),
                                                 result.result.get('msg', 'failed')), 'error')

    def v2_runner_on_unreachable(self, result):
        if self._verbose():
            return super(CallbackModule, self).v2_runner_on_unreachable(result)
        self._step(result.task)
        if result.task.ignore_unreachable:
            return            # the check records a FAIL verdict for the node
        self._header()
        self._errors += 1
        self._out('  UNREACHABLE %s: %s' % (result.host.get_name(), result.result.get('msg', '')), 'error')

    def v2_runner_retry(self, result):
        if self._verbose():
            return super(CallbackModule, self).v2_runner_retry(result)
        task, res = result.task, result.result
        self._step(task)
        seen = self._retry_seen.get(task._uuid, 0)
        attempts, retries = res.get('attempts', 0), res.get('retries', 0)
        if seen == 0 or attempts % 10 == 0:
            self._out('    ... still waiting (attempt %d of %d)' % (attempts, retries), 'dim')
        self._retry_seen[task._uuid] = seen + 1

    def v2_on_file_diff(self, result):
        if self._verbose():
            return super(CallbackModule, self).v2_on_file_diff(result)

    # --- end -----------------------------------------------------------------------------

    def v2_playbook_on_stats(self, stats):
        if self._verbose():
            return super(CallbackModule, self).v2_playbook_on_stats(stats)
        self._close_group()
        if self._summary_seen and not self._result_failed and not self._errors:
            self._out()
            self._out('RESULT: no failures (warnings, if any, are listed in the summary)', 'ok')
        if self._errors:
            self._out()
            self._out('STOPPED: %d step(s) failed outside the checks (ERROR lines above). '
                      'Rerun with -v for the full Ansible output.' % self._errors, 'error')
