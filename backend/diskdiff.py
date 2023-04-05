
import difflib
import hashlib

import logging
import stat as statlib

import sys
import os
import inspect

import unified_diff


# Hacks to import the config from the parent directory.
currentdir = os.path.dirname(os.path.abspath(
    inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

import config  # noqa


class DiskDiffer(object):
    # Class constant that defines the default read buffer size.
    _READ_BUFFER_SIZE = 16 * 1024 * 1024

    MAX_SIZE = 1024 * 1024 * 2  # 2MB

    _STAT_ATTRIBUTES = set([
        "type",
        "owner_identifier",
        "group_identifier",
        "mode",
    ])

    _TIME_ATTRIBUTES = set([
        "access_time",
        "added_time",
        "change_time",
        "creation_time",
        "modification_time",
    ])

    _ATTRIBUTE_ATTRIBUTES = set([
        "name",
    ])
    diff_type = "disk"

    def __init__(self, a_file_lister, b_file_lister,
                 use_stat=True,
                 use_times=True,
                 use_attributes=True,
                 use_contents=True,
                 ignore_binary=True,
                 ignore_directories=False,
                 ignore_contents_unchanged=False,
                 show_times=False,
                 only_changed_files=False,
                 **kwargs):
        """
        a: { path: str -> file_entry FileEntry }
        b: { path: str -> file_entry FileEntry }
        """
        # Save options for creating unique caches later.
        self.init_options = locals()

        self.a_file_lister = a_file_lister
        self.b_file_lister = b_file_lister

        self.a_file_map = {}
        self.b_file_map = {}

        self.use_stat = use_stat
        self.use_times = use_times
        self.use_attributes = use_attributes
        self.use_contents = use_contents
        self.ignore_binary = ignore_binary
        self.ignore_directories = ignore_directories
        self.ignore_contents_unchanged = ignore_contents_unchanged
        self.show_times = show_times
        self.only_changed_files = only_changed_files

        self.changed_file_paths = set()

        self.diffs = {}

    def get_a_file(self, path):

        file_lister_cache_hit = self.a_file_lister.file_entries.get(path)

        if file_lister_cache_hit:
            return file_lister_cache_hit

        if path in self.a_file_map:
            return self.a_file_map[path]

        file_entry = self.a_file_lister.GetFileEntry(path)

        self.a_file_map[path] = file_entry

        return file_entry

    def get_b_file(self, path):

        file_lister_cache_hit = self.b_file_lister.file_entries.get(path)

        if file_lister_cache_hit:
            return file_lister_cache_hit

        if path in self.b_file_map:
            return self.b_file_map[path]

        file_entry = self.b_file_lister.GetFileEntry(path)

        self.b_file_map[path] = file_entry

        return file_entry

    def get_file(self, path):
        """Just get the file, don't care whether it's from before or after"""
        b_file = self.get_b_file(path)
        if b_file:
            return b_file
        return self.get_a_file(path)

    def diff_all(self):
        # Step 1, find files which are different
        changed_file_paths = self.get_changed_files()
        results = {}

        for path in changed_file_paths:
            if self._should_ignore(path):
                continue

            result = self.diff(path)

            if result is None:
                logging.debug(f"Ignoring diffing (no diff): {path}")
                continue

            virtual_path = path

            results[virtual_path] = result

        return results

    def diff(self, path):
        """
            Returns:
                (virtual_path: str, merged_diff: list) | None
        """
        if path in self.diffs:
            return self.diffs[path]

        if self._should_ignore(path):
            return None

        # Step 2, diff those files
        # (Get diffable attributes, then return diff for each one)
        a_file = self.get_a_file(path)
        b_file = self.get_b_file(path)

        stat_diff = times_diff = attribute_diff = contents_diff = []
        diff_kwargs = self._make_diff_kwargs(path)

        if self.use_stat:
            stat_diff = list(difflib.unified_diff(
                self.get_stat_sequence(
                    a_file), self.get_stat_sequence(b_file),
                **diff_kwargs
            ))

        if self.show_times:
            times_diff = list(difflib.unified_diff(
                self.get_times_sequence(
                    a_file), self.get_times_sequence(b_file),
                **diff_kwargs
            ))

        if self.use_attributes:
            attribute_diff = list(difflib.unified_diff(
                self.get_attribute_sequence(
                    a_file), self.get_attribute_sequence(b_file),
                **diff_kwargs
            ))

        has_contents = a_file is not None and a_file.IsFile(
        ) or b_file is not None and b_file.IsFile()

        # We're not ignoring binary if we're here, so treat the files as if they might be binary.
        if self.use_contents and has_contents:
            # Don't try and diff files larger than MAX_SIZE
            if (a_file and a_file.size > self.MAX_SIZE) or (b_file and b_file.size > self.MAX_SIZE):
                logging.info(f"Generating generic diff: (too big): {path}")
                size = b_file.size if b_file else a_file.size
                contents_diff = [
                    f"--- {path}\n",
                    f"+++ {path}\n",
                    "@@ 0,0 +0,0 @@\n",
                    # Note the extra space for Unified Diff format.
                    f" File too large to diff ({size}B)\n"
                ]

            # If the file is binary, diff it as binary.
            elif not self.ignore_binary:
                files = [a_file, b_file]
                existing_files = [f for f in files if f is not None]
                binary_files = [
                    self._is_binary(f) for f in existing_files
                ]

                # If the files are both binary (or one is None and the other is binary), diff them as binary
                if all(binary_files):
                    if self._compare_binaries(a_file, b_file):
                        contents_diff = [
                            f"--- {path}\n",
                            f"+++ {path}\n",
                            "@@ 0,0 +0,0 @@\n",
                            " Binary files differ\n"
                        ]
            else:
                # If at least one file is not binary, do a real diff.
                # If only one is binary, just consider it the string "Binary File"
                a_contents_sequence = self.get_contents_sequence(
                    a_file)
                b_contents_sequence = self.get_contents_sequence(
                    b_file)

                # If both are nonbinary (😎😎😎) diff them as text
                contents_diff = list(difflib.unified_diff(
                    a_contents_sequence,
                    b_contents_sequence,
                    **self._make_diff_kwargs(path)))

        if not any((stat_diff, times_diff, attribute_diff, contents_diff)):
            logging.debug(f"Ignoring (no diff): {path}")
            return None

        # If it's a file, and the contents are unchanged, ignore it.
        # (Don't ignore directories though, because they don't have contents.)
        if not self.get_file(path).IsDirectory() and not contents_diff and self.ignore_contents_unchanged:
            return None

        merged_diff = self.merge_diffs(
            stat_diff, times_diff, attribute_diff, contents_diff)

        # Add headers to conform with git diff format and look pretty for diff2html
        init_header = f"diff --git {path} {path}"

        added_removed_header = ""
        if a_file is None:
            mode = b_file.GetStatAttribute().mode
            if mode is not None:
                mode = format(mode, "o")
            else:
                mode = "<unknown>"
            added_removed_header = f"new file mode {mode}"

        if b_file is None:
            mode = a_file.GetStatAttribute().mode
            if mode is not None:
                mode = format(mode, "o")
            else:
                mode = "<unknown>"
            added_removed_header = f"deleted file mode {mode}"

        self.add_header(merged_diff, added_removed_header)
        self.add_header(merged_diff, init_header)

        diff = unified_diff.UnifiedDiff(
            merged_diff, is_dir=self.get_file(path).IsDirectory())

        self.diffs[path] = diff
        return diff

    def _should_ignore(self, path):

        if not path:
            return True

        a_file = self.get_a_file(path)
        b_file = self.get_b_file(path)

        if self.ignore_directories and (a_file and a_file.IsDirectory() or b_file and b_file.IsDirectory()):
            logging.info(f"Ignoring (directory): {path}")
            return True

        a_is_binary = self._is_binary(a_file)
        b_is_binary = self._is_binary(b_file)

        # Ignore this file if it is or was binary
        if self.ignore_binary and (a_is_binary or b_is_binary):
            logging.info(f"Ignoring (binary): {path}")
            return True

        return False

    def _make_diff_kwargs(self, path, pseudo_file_type=None):
        kwargs = {
            "n": 0
        }

        from_path = path
        to_path = path

        # Add pseudo file types (e.g. "stat", "attributes")
        if pseudo_file_type:
            from_path = f"{from_path}.{pseudo_file_type}"
            to_path = f"{to_path}.{pseudo_file_type}"

        kwargs["fromfile"] = from_path
        kwargs["tofile"] = to_path

        return kwargs

    def add_header(self, delta, header):
        """Add an arbitrary header to a delta (sequence of diff lines)"""

        if not delta or not header:
            return

        header_line = f"{header}\n"

        delta.insert(0, header_line)

    def merge_diffs(self, stat_diff, times_diff, attribute_diff, contents_diff):
        """Merge all the diffs into one, adding the metadata diffs as their own special hunks"""
        stat_hunk = self.create_hunk_diff(stat_diff, "stat attributes")
        times_hunk = self.create_hunk_diff(times_diff, "file times")
        attribute_hunk = self.create_hunk_diff(
            attribute_diff, "extended file attributes")

        for diff in (stat_diff, times_diff, attribute_diff, contents_diff):
            if diff:
                # --- a/file
                # +++ b/file
                headers = diff[:2]

        if contents_diff:
            contents_diff_hunks = contents_diff[2:]
        else:
            contents_diff_hunks = []

        # Insert the metadata hunks into the content diff, before everything else (even the first hunk in the content diff)
        merged_diff = []
        merged_diff.extend(headers)
        merged_diff.extend(stat_hunk)
        merged_diff.extend(times_hunk)
        merged_diff.extend(attribute_hunk)
        merged_diff.extend(contents_diff_hunks)

        return merged_diff

    def create_hunk_diff(self, diff, name):
        if not diff:
            return []
        headers, content = self.split_diff(diff)

        # --- a/file
        # +++ b/file
        # @@ hunk header @@
        hunk_header = headers[-1].rstrip("\n")
        hunk_header = [f"{hunk_header} {name}\n"]
        hunk_diff = hunk_header + content
        return hunk_diff

    def split_diff(self, diff):
        """Return (headers: list, content: list)"""

        return diff[:3], diff[3:]

    def equal(self, file1, file2):
        """Compares two file_entry objects"""

        if file1.size != file2.size:
            return False

        # Compare stat
        if self.use_stat and not self._equal_stat(file1, file2):
            return False

        # Compare times
        if self.use_times and not self._equal_times(file1, file2):
            return False

        # Compare attributes
        if self.use_attributes and not self._equal_attributes(file1, file2):
            return False

        # TODO: Optionally diff hashes

        return True

    def _is_binary(self, file):

        if file is None:
            return False
        textchars = bytearray({7, 8, 9, 10, 12, 13, 27}
                              | set(range(0x20, 0x100)) - {0x7f})  # noqa

        file_obj = file.GetFileObject()
        if file_obj is None:
            return False
        try:
            header = file_obj.read(512)
            file_obj.seek(0)

            try:
                header.decode("utf8", errors="strict")
            except UnicodeDecodeError:
                return True

            return bool(header.translate(None, textchars))

        except OSError:
            logging.warning(f"Failed to read {file.path_spec.location}")
            return True

    def _compare_binaries(self, file1, file2):

        return self._hash_file(file1) == self._hash_file(file2)

    def _hash_file(self, file_entry):
        """Calculates a message digest hash of the data of the file entry.

        Args:
        file_entry (dfvfs.FileEntry): file entry.

        Returns:
        str: digest hash or None.
        """
        if file_entry is None:
            return None

        if file_entry.IsDevice() or file_entry.IsPipe() or file_entry.IsSocket():
            # Ignore devices, FIFOs/pipes and sockets.
            return None

        hash_context = hashlib.sha256()

        try:
            file_object = file_entry.GetFileObject()
        except IOError as exception:
            logging.warning((
                'Unable to open path specification:\n{0:s}'
                'with error: {1!s}').format(file_entry.path_spec.location, exception))
            return None

        if not file_object:
            return None

        try:
            data = file_object.read(self._READ_BUFFER_SIZE)
            while data:
                hash_context.update(data)
                data = file_object.read(self._READ_BUFFER_SIZE)
        except IOError as exception:
            logging.warning((
                'Unable to read from path specification:\n{0:s}'
                'with error: {1!s}').format(file_entry.path_spec.location, exception))
            return None

        return hash_context.hexdigest()

    def get_stat_sequence(self, file):
        if file is None:
            return []

        stat = file.GetStatAttribute()
        out = []
        for attr in self._STAT_ATTRIBUTES:
            value = getattr(stat, attr)
            if value and attr == "mode":
                value = statlib.filemode(value)

            line = f"{attr}: {value}\n"
            out.append(line)
        return out

    def get_times_sequence(self, file):
        if file is None:
            return []
        out = []
        for attr in self._TIME_ATTRIBUTES:
            line = f"{attr}: {getattr(file, attr).CopyToDateTimeStringISO8601()}\n"
            out.append(line)
        return out

    def get_attribute_sequence(self, file):

        def _get_attribute_value(attribute):

            # macOS dfvfs
            if hasattr(attribute, "read"):
                attribute_value = attribute.read().decode(errors="ignore")
                return attribute_value

            # Windows dfvfs
            elif hasattr(attribute, "name"):
                attribute_value = attribute.name
                return attribute_value

            return None

        if file is None:
            return []
        out = []

        for attribute in file.attributes:
            attribute_value = _get_attribute_value(attribute)
            if attribute_value:
                line = f"{attribute.name}: {attribute_value}\n"
                out.append(line)
        return out

    def get_contents_sequence(self, file):
        if file is None:
            return []

        if not self.ignore_binary and self._is_binary(file):
            return ["<Binary file>\n"]

        file_obj = file.GetFileObject()

        if file_obj is None:
            return []

        contents = file_obj.read().decode("utf8", "ignore")

        lines = []
        # Make sure all lines end with newlines, to conform with diff format.

        for line in contents.split("\n"):
            lines.append(line + "\n")

        return lines

    def _equal_stat(self, file1, file2):

        stat1 = file1.GetStatAttribute()
        stat2 = file2.GetStatAttribute()
        for attr in self._STAT_ATTRIBUTES:
            if getattr(stat1, attr) != getattr(stat2, attr):
                return False

        return True

    def _equal_times(self, file1, file2):

        for attr in self._TIME_ATTRIBUTES:
            if getattr(file1, attr) != getattr(file2, attr):
                return False

        return True

    def _equal_attributes(self, file1, file2):

        if file1.number_of_attributes != file2.number_of_attributes:
            return False

        for attr1, attr2 in zip(file1.attributes, file2.attributes):

            # Only check the attributes we care about when considering equality.
            # (We have literally invented prejudice today boys.)

            for attr in self._ATTRIBUTE_ATTRIBUTES:
                if hasattr(attr1, attr) and hasattr(attr2, attr):
                    if getattr(attr1, attr) != getattr(attr2, attr):
                        return False

        return True

    def get_run_id(self):
        return config.RUN_ID

    def get_changed_files(self):

        if self.changed_file_paths:
            return self.changed_file_paths

        # Otherwise, we need to list the files in A and B first
        # This is the slowest part.
        self.a_file_lister.ListFileEntries()
        self.b_file_lister.ListFileEntries()

        # If path doesn't exist, consider it different

        changed_file_paths = set()

        a_paths_set = set(self.a_file_lister.file_entries.keys())
        b_paths_set = set(self.b_file_lister.file_entries.keys())
        self.added_files = b_paths_set - a_paths_set
        self.deleted_files = a_paths_set - b_paths_set

        if not self.only_changed_files:
            changed_file_paths = changed_file_paths | self.added_files | self.deleted_files

        # Get all files in A but not B (and vice versa), and consider them different
        remaining_paths = a_paths_set & b_paths_set

        # These paths are guaranteed to be in both A and B
        for path in remaining_paths:
            a_file = self.get_a_file(path)
            b_file = self.get_b_file(path)

            if not self.equal(a_file, b_file):
                changed_file_paths.add(path)

        logging.info(f"Files (from): {len(a_paths_set)}")
        logging.info(f"Files (to): {len(b_paths_set)}")
        logging.info(f"Files (both): {len(remaining_paths)}")
        logging.info(f"Files added: {len(self.added_files)}")
        logging.info(f"Files deleted: {len(self.deleted_files)}")
        logging.info(
            f"Files changed (including binary): {len(changed_file_paths)}")
        logging.debug("Changed files: ")
        logging.debug(changed_file_paths)

        self.changed_file_paths = changed_file_paths

        return self.changed_file_paths
