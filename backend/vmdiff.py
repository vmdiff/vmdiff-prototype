#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Script to list file entries."""

from dfvfs.helpers import command_line
from dfvfs.helpers import volume_scanner
import memdiff
import diff_tree
import diffcache
import diskdiff
import file_entry_lister
import logging
import sys
import os
import json
import inspect

import hashlib


# Hacks to import the config from the parent directory.
currentdir = os.path.dirname(os.path.abspath(
    inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

import config  # noqa

logging.basicConfig(
    format='[%(asctime)s]:%(levelname)s:%(message)s', level=config.LOG_LEVEL)


class CachingStdinInputReader(command_line.StdinInputReader):
    """Remembers the last input, so it can be reused."""

    def __init__(self, encoding='utf-8'):
        """
        Args:
            encoding (Optional[str]): input encoding.
        """
        super(CachingStdinInputReader, self).__init__(encoding=encoding)
        self.last_input = None

    def Read(self):
        self.last_input = super(CachingStdinInputReader, self).Read()
        return self.last_input


def load_memory_results():
    memory_run_name = f"{config.FROM_MEMORY_IMAGE_FILENAME}__{config.TO_MEMORY_IMAGE_FILENAME}"
    memory_run_path = os.path.join(
        config.RESULTS_DIR, "memory", memory_run_name)
    results = {}
    for plugin in config.MEMORY_PLUGINS:

        from_plugin_path = os.path.join(memory_run_path, f"from-{plugin}.json")
        to_plugin_path = os.path.join(memory_run_path, f"to-{plugin}.json")
        with open(from_plugin_path) as f:
            from_plugin = json.load(f)
        with open(to_plugin_path) as f:
            to_plugin = json.load(f)

        results[plugin] = (from_plugin, to_plugin)

    return results


def dump_api_data(cache):

    run_path = cache.tree_path

    dump_dir = run_path / "json"
    children_dir = dump_dir / "children"
    diff_dir = dump_dir / "diff"

    if config.USE_CACHE and dump_dir.exists():
        return

    logging.info(f"Generating API data for static site: {dump_dir}")

    os.makedirs(dump_dir, exist_ok=True)
    os.makedirs(children_dir, exist_ok=True)
    os.makedirs(diff_dir, exist_ok=True)

    logging.info(f"Dumping API data to {dump_dir}")

    tree, children_map = cache.get_tree_data_from_cache()

    json.dump(tree, open(dump_dir / "changed_files", "w"))

    # Dump all the data with url encoded keys, so we can serve it statically later
    for key, children in children_map.items():

        # Make sure to also encode the "/" character.
        filename = hashlib.sha1(key.encode("utf8")).hexdigest()

        path = children_dir / filename
        json.dump(children, open(path, "w"))

        # Get the diff and dump it too.
        diff = cache.get_diff(key)
        if diff is None:
            result = None
        else:
            result = diff.diff_lines

        if result:
            path = diff_dir / filename
            json.dump(result, open(path, "w"))


def Main():

    # Leave Blank or invalid for interactive prompt
    partition = config.PARTITION
    VOLUMES = "all"

    logging.basicConfig(
        level=logging.INFO, format='[%(levelname)s] %(message)s')

    caching_input_reader = CachingStdinInputReader()
    mediator = command_line.CLIVolumeScannerMediator(
        input_reader=caching_input_reader)

    volume_scanner_options = volume_scanner.VolumeScannerOptions()
    volume_scanner_options.partitions = mediator.ParseVolumeIdentifiersString(
        partition)

    volume_scanner_options.volumes = mediator.ParseVolumeIdentifiersString(
        VOLUMES)

    # Init disk file listers.
    parent_lister = file_entry_lister.FileEntryLister(
        config.FROM_DISK_PATH, volume_scanner_options, mediator=mediator, ignore_dirs=config.ignore_dirs, allow_dirs=config.allow_dirs)

    partition_input = partition
    if not partition_input:
        # Get the input the user gave the first time, if any.
        partition_input = caching_input_reader.last_input

    volume_scanner_options.partitions = list(mediator.ParseVolumeIdentifiersString(
        partition_input))

    delta_lister = file_entry_lister.FileEntryLister(
        config.TO_DISK_PATH, volume_scanner_options, mediator=mediator, ignore_dirs=config.ignore_dirs, allow_dirs=config.allow_dirs)

    # ls parition to make sure it's the right one:
    if not partition:
        entries = list(
            parent_lister.file_system.GetRootFileEntry().sub_file_entries)
        ls_root = [e.name for e in entries]
        logging.info(f"Partition {partition} root files: {ls_root}")

    diff_config = config.diff_config
    differ = diskdiff.DiskDiffer(
        parent_lister, delta_lister,
        **diff_config
    )

    USE_CACHE = config.USE_CACHE

    run_process_path = config.RUN_MEMORY_PATH if config.USE_MEMORY else None

    cache = diffcache.DiffCache(
        config.RUN_DISK_PATH, config.RUN_TREE_PATH, run_process_path)

    if USE_CACHE and cache.cache_exists() and (not config.USE_MEMORY or (config.USE_MEMORY and cache.process_cache_exists())):
        # Slice off the leading "/" and trailing "/disk"
        results_dir = os.path.join(*cache.run_path.parts[1:-1])
        logging.info(f"Results already cached at: {str(results_dir)}")
        # The diffs can be accessed via cache.get_diff_from_cache(path)
    else:
        logging.info("No cache found, diffing... ")

        if config.USE_DISK:
            logging.info("Diffing disk... ")

            # Get results and cache them.
            differ.get_changed_files()
            results = differ.diff_all()

            if not results:
                logging.info("No disk differences found.")
            cache.cache_results(results)

            # Now render the tree
            disk_tree = diff_tree.DiffTree(differ)

        if config.USE_MEMORY:
            logging.info("Diffing memory... ")

            plugin_results = load_memory_results()
            from_pslist, to_pslist = plugin_results.get(
                "windows.pslist.PsList")
            from_envars, to_envars = plugin_results.get(
                "windows.envars.Envars")
            from_cmdline, to_cmdline = plugin_results.get(
                "windows.cmdline.CmdLine")

            # Load pslists already provided by memory-processing.
            mem_differ = memdiff.MemoryDiffer(from_pslist,
                                              to_pslist,
                                              from_envars=from_envars,
                                              to_envars=to_envars,
                                              from_cmdline=from_cmdline,
                                              to_cmdline=to_cmdline,
                                              ignore_regex=config.IGNORE_PROCESSES_REGEX)

            memdiffs = mem_differ.diff_all()
            if not memdiffs:
                logging.info("No memory differences found.")
            cache.cache_process_results(memdiffs)

            mem_tree = diff_tree.DiffTree(mem_differ)

        if config.USE_DISK and config.USE_MEMORY:
            merged_tree = disk_tree.merge(mem_tree)
        elif config.USE_DISK:
            merged_tree = disk_tree
        elif config.USE_MEMORY:
            merged_tree = mem_tree
        else:
            raise RuntimeError(
                "Must set either USE_DISK or USE_MEMORY, otherwise what am I supposed to diff, huh wise guy")

        logging.debug(merged_tree.children_map)

        cache.cache_tree(merged_tree)
        dump_api_data(cache)

        logging.info(f"Saved results to {cache.run_path}")

    return cache


if __name__ == '__main__':
    Main()
