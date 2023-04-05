import re
import logging


from dfvfs.helpers import volume_scanner
from dfvfs.lib import definitions as dfvfs_definitions
from dfvfs.lib import errors
from dfvfs.resolver import resolver
from dfvfs.path import factory


class FileEntryLister(volume_scanner.VolumeScanner):
    """File entry lister."""

    _NON_PRINTABLE_CHARACTERS = list(range(0, 0x20)) + list(range(0x7f, 0xa0))
    _ESCAPE_CHARACTERS = str.maketrans({
        value: '\\x{0:02x}'.format(value)
        for value in _NON_PRINTABLE_CHARACTERS})

    def __init__(self, source, volume_scanner_options, mediator=None, ignore_dirs=None, allow_dirs=None):
        """Initializes a file entry lister.

        Args:
          mediator (VolumeScannerMediator): a volume scanner mediator.
        """
        super(FileEntryLister, self).__init__(mediator=mediator)

        if ignore_dirs is None:
            ignore_dirs = set()
        if allow_dirs is None:
            allow_dirs = set(["/"])

        self.allow_dirs = allow_dirs
        self.ignore_dirs = ignore_dirs

        self._list_only_files = False

        self.base_path_specs = self.GetBasePathSpecs(
            source, options=volume_scanner_options)

        self.source = source

        if not self.base_path_specs:
            raise Exception(
                f'{source}: No supported file system found in source.')

        # TODO: Support multiple base path specs
        self.base_path_spec = self.base_path_specs[0]
        self.file_system = resolver.Resolver.OpenFileSystem(
            self.base_path_spec)

        self.file_entries = {}

    def _GetDisplayPath(self, path_spec, path_segments, data_stream_name):
        """Retrieves a path to display.

        Args:
          path_spec (dfvfs.PathSpec): path specification of the file entry.
          path_segments (list[str]): path segments of the full path of the file
              entry.
          data_stream_name (str): name of the data stream.

        Returns:
          str: path to display.
        """
        display_path = ''

        if path_spec.HasParent():
            parent_path_spec = path_spec.parent
            if parent_path_spec and parent_path_spec.type_indicator in (
                    dfvfs_definitions.PARTITION_TABLE_TYPE_INDICATORS):
                display_path = ''.join(
                    [display_path, parent_path_spec.location])

        path_segments = [
            segment.translate(self._ESCAPE_CHARACTERS) for segment in path_segments]
        display_path = ''.join([display_path, '/'.join(path_segments)])

        if data_stream_name:
            data_stream_name = data_stream_name.translate(
                self._ESCAPE_CHARACTERS)
            display_path = ':'.join([display_path, data_stream_name])

        return display_path or '/'

    def _ShouldListDir(self, file_entry):

        location = file_entry.path_spec.location

        for allow_dir in self.allow_dirs:
            if location.startswith(allow_dir) or allow_dir.startswith(location):
                for ignore_dir in self.ignore_dirs:
                    # Convert to raw string so backslashes aren't interpreted as escapes.
                    ignore_dir = repr(ignore_dir).strip("'")
                    if re.search(ignore_dir, location):
                        return False
                return True

        return False

    def _ListFileEntry(
            self, file_entry):
        """Lists a file entry.

        Args:
          file_entry (dfvfs.FileEntry): file entry to list.
        """
        def _dedup_backslashes(path):
            return path.replace("\\\\", "\\")

        location = file_entry.path_spec.location
        if location.startswith("\\"):

            location = _dedup_backslashes(location)

        self.file_entries[location] = file_entry

        try:
            for sub_file_entry in file_entry.sub_file_entries:

                if not self._ShouldListDir(sub_file_entry):
                    continue

                self._ListFileEntry(sub_file_entry)

        except OSError as e:
            if "unable to read MFT entry:" in str(e):
                logging.error(
                    f"{self.source}: Unable to list subdirectories for {location}: MFT is corrupted. Try chkdsk first?")
            else:
                logging.error(
                    f"{self.source}: Unable to list subdirectories for {location}")
                logging.debug(
                    f"{self.source}: {e}")

    def ListFileEntries(self):
        """Lists file entries in the base path specification."""
        for base_path_spec in self.base_path_specs:
            self.file_system = resolver.Resolver.OpenFileSystem(base_path_spec)
            file_entry = resolver.Resolver.OpenFileEntry(base_path_spec)

            if file_entry is None:
                logging.warning(
                    'Unable to open base path specification:\n{0:s}'.format(
                        base_path_spec))
                return

            self._ListFileEntry(file_entry)

    def GetFileEntry(self, path):

        for base_path_spec in self.base_path_specs:
            path_spec = factory.Factory.NewPathSpec(
                base_path_spec.type_indicator, location=path, parent=self.base_path_spec.parent)
            try:
                file_entry = resolver.Resolver.OpenFileEntry(path_spec)
                if file_entry:
                    return file_entry
            except errors.BackEndError:
                logging.warning(
                    f"{base_path_spec.location}: Unable to open file: {path}")

        return None
