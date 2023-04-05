
class UnifiedDiff(object):

    def __init__(self, diff_lines, is_dir=None, ppid=None, title=None):
        self.diff_lines = diff_lines
        self._iter = iter(diff_lines)
        self.is_dir = is_dir

        self.title = title

        # Parent PID if this is a process node.
        self.ppid = ppid

        header = diff_lines[1]
        if header.startswith("new"):
            self.status = "added"
        elif header.startswith("deleted"):
            self.status = "removed"
        else:
            self.status = "modified"

        self.lines_added = 0
        self.lines_removed = 0
        for line in diff_lines:
            # Ignore --- and +++ lines
            if line.startswith("+") and not line.startswith("++"):
                self.lines_added += 1
            if line.startswith("-") and not line.startswith("--"):
                self.lines_removed += 1

    def __next__(self):
        return next(self._iter)
