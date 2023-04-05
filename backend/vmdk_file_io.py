# -*- coding: utf-8 -*-
"""The VMDK image file-like object."""
# Copy of `vmdk_file_io` we patch and copy into the docker container.

# This is the patch.
import pyvmdk_delta as pyvmdk

from dfvfs.file_io import file_object_io
from dfvfs.lib import errors
from dfvfs.path import factory as path_spec_factory
from dfvfs.resolver import resolver


class VMDKFile(file_object_io.FileObjectIO):
    """File input/output (IO) object using pyvmdk."""

    def _OpenFileObject(self, path_spec):
        """Opens the file-like object defined by path specification.

        Args:
          path_spec (PathSpec): path specification.

        Returns:
          pyvmdk.handle: a file-like object.

        Raises:
          IOError: if the file-like object could not be opened.
          OSError: if the file-like object could not be opened.
          PathSpecError: if the path specification is incorrect.
        """
        if not path_spec.HasParent():
            raise errors.PathSpecError(
                'Unsupported path specification without parent.')

        parent_path_spec = path_spec.parent

        parent_location = getattr(parent_path_spec, 'location', None)
        if not parent_location:
            raise errors.PathSpecError(
                'Unsupported parent path specification without location.')

        # Note that we cannot use pyvmdk's open_extent_data_files_as_file_objects
        # function since it does not handle the file system abstraction dfVFS
        # provides.

        file_system = resolver.Resolver.OpenFileSystem(
            parent_path_spec, resolver_context=self._resolver_context)

        file_object = resolver.Resolver.OpenFileObject(
            parent_path_spec, resolver_context=self._resolver_context)

        vmdk_handle = pyvmdk.handle()
        vmdk_handle.open(parent_location)

        return vmdk_handle

    def open_extent_data_files(self, vmdk_handle, parent_path_spec):

        parent_location = getattr(parent_path_spec, 'location', None)
        file_system = resolver.Resolver.OpenFileSystem(
            parent_path_spec, resolver_context=self._resolver_context)

        parent_location_path_segments = file_system.SplitPath(parent_location)
        extent_data_files = []
        for extent_descriptor in iter(vmdk_handle.extent_descriptors):
            extent_data_filename = extent_descriptor.filename

            _, path_separator, filename = extent_data_filename.rpartition('/')
            if not path_separator:
                _, path_separator, filename = extent_data_filename.rpartition(
                    '\\')

            if not path_separator:
                filename = extent_data_filename

            # The last parent location path segment contains the extent data filename.
            # Since we want to check if the next extent data file exists we remove
            # the previous one form the path segments list and add the new filename.
            # After that the path segments list can be used to create the location
            # string.
            parent_location_path_segments.pop()
            parent_location_path_segments.append(filename)
            extent_data_file_location = file_system.JoinPath(
                parent_location_path_segments)

            # Note that we don't want to set the keyword arguments when not used
            # because the path specification base class will check for unused
            # keyword arguments and raise.
            kwargs = path_spec_factory.Factory.GetProperties(parent_path_spec)

            kwargs['location'] = extent_data_file_location
            if parent_path_spec.parent is not None:
                kwargs['parent'] = parent_path_spec.parent

            extent_data_file_path_spec = path_spec_factory.Factory.NewPathSpec(
                parent_path_spec.type_indicator, **kwargs)

            if not file_system.FileEntryExistsByPathSpec(extent_data_file_path_spec):
                break

            extent_data_files.append(extent_data_file_path_spec)

        if len(extent_data_files) != vmdk_handle.number_of_extents:
            raise IOError('Unable to locate all extent data files.')

        file_objects = []
        for extent_data_file_path_spec in extent_data_files:
            file_object = resolver.Resolver.OpenFileObject(
                extent_data_file_path_spec, resolver_context=self._resolver_context)
            file_objects.append(file_object)

        vmdk_handle.open_extent_data_files_as_file_objects(file_objects)

    def get_size(self):
        """Retrieves the size of the file-like object.

        Returns:
          int: size of the file-like object data.

        Raises:
          IOError: if the file-like object has not been opened.
          OSError: if the file-like object has not been opened.
        """
        if not self._is_open:
            raise IOError('Not opened.')

        return self._file_object.get_media_size()
