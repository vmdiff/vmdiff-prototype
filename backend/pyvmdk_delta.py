
import pyvmdk
import os


class handle(object):

    """Trick dfvfs into keeping the parent handles in scope by storing them in this object, which is going to masquerade as a pyvmdk.handle"""

    # The list of parent handles. Even though we never read from this list, storing parent handles in it keeps them in scope, preventing them from being deallocated.
    parent_handles = []

    def __init__(self):
        self.parent = None
        self._handle = pyvmdk.handle()

    def open(self, path):
        """Open a handle to a VMDK path
            AND open any parent delta files
            AND open extent data files for all VMDK files"""

        self._handle.open(path)
        self._handle.open_extent_data_files()

        parent_filename = self._handle.get_parent_filename()

        # If this disk is a delta disk, set its parent.
        if parent_filename:

            # Delta disks contain the filename to their parent disk, not the full path,
            # so we expect the parent disk to be in the same directory.
            parent_path = os.path.join(os.path.dirname(path), parent_filename)

            parent_handle = handle()
            # The parent disk may itself be a child of another disk, so recurse.
            parent_handle.open(parent_path)

            self.parent_handles.append(parent_handle)

            self._handle.set_parent(parent_handle._handle)

    def __getattribute__(self, name):

        # Hard code the list of attributes, because try/except is slow.
        if name in ("__getattribute__", "_handle", "open", "parent", "__init__", "parent_handles"):
            return object.__getattribute__(self, name)
        else:
            return getattr(self._handle, name)
