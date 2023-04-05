

import collections
import difflib
import json
import re
import logging

import unified_diff


class MemoryDiffer(object):
    # TODO: Inherit from a shared "Differ" class
    diff_type = "process"

    def __init__(self, from_pslist, to_pslist, from_envars=None, to_envars=None, from_cmdline=None, to_cmdline=None, ignore_regex=""):

        self.ignore_regex = ignore_regex
        self.from_procs = self._list_by_id(from_pslist)
        self.to_procs = self._list_by_id(to_pslist)

        self.add_envars(from_envars, to_envars)
        self.add_cmdline(from_cmdline, to_cmdline)

        self.all_pids = set(self.from_procs.keys()) | set(self.to_procs.keys())
        self.diffs = {}

    def diff_all(self):
        if self.diffs:
            return self.diffs

        for pid in self.all_pids:
            diff = self.diff(pid)
            if diff:
                self.diffs[pid] = diff
        return self.diffs

    def diff(self, pid):

        if pid in self.diffs:
            return self.diffs[pid]

        from_proc = self.from_procs.get(pid, "")
        to_proc = self.to_procs.get(pid, "")

        # Ignore "Required memory <address> is not valid (process exited?)" errors.
        if to_proc and "is not valid (process exited?)" in to_proc["CommandLine"]:
            to_proc = ""
        if from_proc and "is not valid (process exited?)" in from_proc["CommandLine"]:
            from_proc = ""

        kwargs = {}
        fromfile = self._make_title(from_proc)
        tofile = self._make_title(to_proc)

        from_name = fromfile.split("-")[0] if fromfile else ""
        to_name = tofile.split("-")[0] if tofile else ""

        if self.ignore_regex:
            # Ignore this proceses if the to or from process name matches the supplied regex.
            if (from_name and re.search(self.ignore_regex, from_name)):
                logging.info(
                    f"Ignoring due to filter regex: {from_name}")
                from_proc = ""
            if (to_name and re.search(self.ignore_regex, to_name)):
                logging.info(
                    f"Ignoring due to filter regex: {to_name}")
                to_proc = ""

        # Use the other filename if one of the filenames is empty (because this is an added or deleted file)

        fromfile = fromfile or tofile
        tofile = tofile or fromfile

        kwargs["fromfile"] = fromfile
        kwargs["tofile"] = tofile

        # Number of lines of context to show (show the entire process)
        kwargs["n"] = 999

        result = list(difflib.unified_diff(
            self._to_string(from_proc),
            self._to_string(to_proc),
            **kwargs
        ))

        if not result:
            return None
        # Add headers to conform with git diff format and look pretty for diff2html
        init_header = f"diff --git {fromfile} {tofile}"

        is_added = not from_proc and to_proc
        is_removed = not to_proc and from_proc

        added_removed_header = ""
        if is_added:
            added_removed_header = "new file"

        if is_removed:
            added_removed_header = "deleted file"

        self.add_header(result, added_removed_header)
        self.add_header(result, init_header)

        ppid = self.get_ppid(pid)
        title = self._make_title(to_proc or from_proc)
        diff = unified_diff.UnifiedDiff(result, ppid=ppid, title=title)
        return diff

    def add_envars(self, from_envars, to_envars):

        if not from_envars and to_envars:
            return

        def _add_envars_to_procs(envars, procs):

            # Group vars by PID
            pid_vars = collections.defaultdict(dict)
            for var in envars:
                key = var["Variable"]
                value = var["Value"]
                pid = str(var["PID"])
                pid_vars[pid][key] = value

            # Add vars dict to PID in procs
            for pid in pid_vars:
                procs[pid]["EnvironmentVariables"] = pid_vars[pid]

        _add_envars_to_procs(from_envars, self.from_procs)
        _add_envars_to_procs(to_envars, self.to_procs)

    def add_cmdline(self, from_cmdline, to_cmdline):

        if not from_cmdline and to_cmdline:
            return

        def _add_cmdline_to_procs(cmdlines, procs):

            # Group vars by PID
            for cmdline in cmdlines:
                args = cmdline["Args"]
                pid = str(cmdline["PID"])

                # Add "Args" field to existing processes by PID
                procs[pid]["CommandLine"] = args

        _add_cmdline_to_procs(from_cmdline, self.from_procs)
        _add_cmdline_to_procs(to_cmdline, self.to_procs)

    def _make_id(self, proc):
        if not proc:
            return ""
        pid = str(proc["PID"])
        return pid

    def _make_title(self, proc):
        if not proc:
            return ""
        pid = proc["PID"]
        name = proc["ImageFileName"]
        return f"{name}-{pid}"

    def _list_by_id(self, pslist):
        procs = {}
        for proc in pslist:
            process_id = self._make_id(proc)
            # Ignore "Threads" value, since it changes a lot and isn't worth diffing on.

            del proc["Threads"]

            procs[process_id] = proc
        return procs

    def _to_string(self, proc):
        if not proc:
            return ""
        return [line + "\n" for line in json.dumps(proc,
                                                   separators=(',', ': '),
                                                   sort_keys=True,
                                                   indent=4).split("\n")]

    def get_ppid(self, pid):
        from_proc = self.from_procs.get(pid)
        to_proc = self.to_procs.get(pid)

        # Select whichever one isn't none, defaulting to to_proc.
        proc = to_proc or from_proc

        ppid = str(proc.get("PPID", ""))
        return ppid

    def add_header(self, delta, header):
        """Add an arbitrary header to a delta (sequence of diff lines)"""

        if not delta or not header:
            return

        header_line = f"{header}\n"

        delta.insert(0, header_line)
