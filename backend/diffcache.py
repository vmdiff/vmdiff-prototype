import pathlib
import os
import logging
import json

import unified_diff
import utils

DIR_META_FILENAME = ".__this_directory__"


class DiffCache(object):

    def __init__(self, run_disk_path, run_tree_path, run_process_path=None):
        self.run_path = pathlib.Path(run_disk_path)
        self.tree_path = pathlib.Path(run_tree_path)
        self.run_process_path = pathlib.Path(str(run_process_path))
        if run_process_path:
            os.makedirs(self.run_process_path, exist_ok=True)

    def cache_results(self, results):
        """Create output directory, and write the same filesystem into it as in the results"""

        os.makedirs(self.run_path, exist_ok=True)
        # Sort by path, so we only create parent directories after children.
        for path, diff in sorted(results.items(), key=lambda tup: tup[0]):

            path = utils.ensure_posix(path)

            if diff.is_dir:
                path = path / pathlib.Path(DIR_META_FILENAME)

            root, *relative_disk_path = path.parts

            relative_disk_path = pathlib.Path(
                relative_disk_path[0]).joinpath(*relative_disk_path[1:])

            result_path = self.run_path / pathlib.Path(relative_disk_path)

            try:
                # Create the parent directories
                result_path.parent.mkdir(parents=True, exist_ok=True)
            except FileExistsError:
                # This means a path has changed from a directory to a file.
                # Whatever, tho
                # Limitation: Let's keep it as a directory
                result_path.parent.rename(
                    result_path.parent.with_suffix(".__renamed__"))

                result_path.parent.mkdir(parents=True, exist_ok=True)

                logging.warning(
                    f"Ignoring file exists error when creating parents for {str(result_path)}, overwriting parent file with directory.")

            if result_path.is_dir():
                result_path = result_path.with_suffix(".__directory_as_file__")
                logging.warning(
                    f"Path has changed from directory to file (or vice versa), writing as {str(result_path)}")

            # Write the diff file.
            with open(result_path, "w") as f:
                f.writelines(diff.diff_lines)

    def ensure_posix(self, path):
        if path.startswith("\\"):
            # Force POSIX path so that we can create the directory structure in the Docker container, even if the path is Windows.
            path = pathlib.PureWindowsPath(path).as_posix()
        path = pathlib.Path(path)
        return path

    def cache_process_results(self, results):
        for pid, diff in results.items():

            filename = pid

            result_path = self.run_process_path / filename

            # Write the diff file.
            with open(result_path, "w") as f:
                f.writelines(diff.diff_lines)

    def get_process_diff_from_cache(self, pid):
        filename = pid
        result_path = self.run_process_path / filename
        try:
            with open(result_path, "r") as f:
                lines = f.readlines()
                diff = unified_diff.UnifiedDiff(lines)
                return diff
        except FileNotFoundError:
            print(f"Process diff cache not found: {result_path}")
            return None

    def get_diff_from_cache(self, vm_path):

        if not self.run_path.exists:
            return None

        vm_path = utils.ensure_posix(vm_path)

        # Slice off the root (and drive on Windows) from the vm path, so it's not an absolute path
        cache_path = self.run_path.joinpath(*vm_path.parts[1:])
        is_dir = False
        # If this was a directory on the VM, the diff is stored in a file called DIR_META_FILENAME
        if cache_path.joinpath(DIR_META_FILENAME).exists():
            is_dir = True
            cache_path = cache_path.joinpath(DIR_META_FILENAME)

        if not cache_path.is_file():
            return None

        with open(cache_path) as f:
            lines = f.readlines()
            diff = unified_diff.UnifiedDiff(lines, is_dir)
            return diff

    def get_diff(self, key):
        # If the key is a process ID (numeric)
        if key.isdigit():
            return self.get_process_diff_from_cache(key)
        else:
            return self.get_diff_from_cache(key)

    def cache_exists(self):
        return self.run_path.exists() and self.tree_cache_exists()

    def process_cache_exists(self):
        return self.run_process_path is not None and self.run_process_path.exists()

    def get_cached_results(self):

        if not self.cache_exists():
            raise RuntimeError(f"Cache path {self.run_path} does not exist!")

        results = {}

        logging.info(f"Loading from diff cache {self.run_dir}")
        for path, subdirs, files in os.walk(self.run_path):
            for filename in files:
                is_dir = False
                if filename == DIR_META_FILENAME:
                    is_dir = True
                filepath = os.path.join(path, filename)
                with open(filepath) as f:
                    lines = f.readlines()
                    diff = unified_diff.UnifiedDiff(lines, is_dir)
                    relative_path = pathlib.Path(
                        filepath).relative_to(self.run_path)
                    if is_dir:
                        # Remove dir suffix if this is a dir
                        relative_path = relative_path.parent

                    original_path = os.path.join("/", relative_path)

                    results[original_path] = diff

        return results

    def tree_cache_exists(self):
        return (self.tree_path / "tree.json").exists()

    def cache_tree(self, tree):
        os.makedirs(self.tree_path, exist_ok=True)
        with open(self.tree_path / "tree.json", "w") as f:
            json.dump(tree.get_tree(), f)
        with open(self.tree_path / "children.json", "w") as f:
            json.dump(tree.get_children_map(), f)

    def get_tree_data_from_cache(self):
        with open(self.tree_path / "tree.json", "r") as f:
            tree = json.load(f)
        with open(self.tree_path / "children.json", "r") as f:
            children_map = json.load(f)

        return tree, children_map
