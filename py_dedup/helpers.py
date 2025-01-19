"""
This module provides utilities for identifying and handling duplicate files within directories.

Symlink Handling:
    - Symlinks are **not** supported and are ignored during directory scanning.
        The module does not follow symbolic links to prevent potential infinite recursion
        and to ensure accurate duplicate detection based on actual file contents.

Classes:
    DirectoryValidator:
        - Validates that given directory paths exist and point to actual directories.

    DupFinder:
        - Scans specified directories to find empty files and duplicate files by size and MD5 hash.
        - Offers properties to access duplicates and empty files.
        - Includes methods to print or retrieve duplicates in different sorted orders.

    DupHandler:
        - Performs actions on the results of a DupFinder, such as removing duplicates from specific directories.
        - Supports both a “dry run” mode to preview actions and a “force” mode to bypass safety checks.

Typical usage example:

    >>> import pathlib
    >>> from py_dedup import DupFinder, DupHandler
    
    >>> # 1. Identify duplicates
    >>> finder = DupFinder(dirs=[pathlib.Path("some_directory")])
    >>> duplicates = finder.duplicates
    >>> empty_files = finder.empty_files

    >>> # 2. Remove duplicates in certain directories, deletions will only occur
    >>> #       if at least one duplicate exists outside specified dir/dirs.
    >>> handler = DupHandler(finder)
    >>> deleted, failed = handler.remove_dir_duplicates(dirs=["some_directory"], dry_run=True)
    >>> # 'deleted' will hold paths that would have been removed; 'failed' any that couldn't be removed.
"""

from __future__ import annotations
import os
import pathlib
import hashlib
from concurrent.futures import ProcessPoolExecutor
from typing import Iterable


class DirectoryValidator:
    """
    Provides methods to validate and resolve directory paths into usable
    pathlib.Path objects, ensuring they exist and point to directories.
    """

    @staticmethod
    def get_dir_set(dirs: list[pathlib.Path | str]) -> set[pathlib.Path]:
        """
        Validates and resolves a list of directories into a set of Path objects.

        Args:
            dirs (list[Path | str]): A list of directory paths.

        Returns:
            set[Path]: A set of resolved directory Path objects.

        Raises:
            TypeError: If any directory is not a string or Path.
            ValueError: If any path is invalid or not a directory, or if the list is empty.
        """
        dir_set = set()
        for directory in dirs:
            if not isinstance(directory, (str, pathlib.Path)):
                raise TypeError(
                    f"All directories in dirs need to be of type string or Path. "
                    f"Got {directory} : {type(directory).__name__}"
                )

            try:
                dir_path = pathlib.Path(directory).resolve(strict=True)
                if not dir_path.is_dir():
                    raise ValueError(f"{directory} is not a valid directory path!")
            except FileNotFoundError:
                raise ValueError(f"{directory} is not a valid path!") from None

            dir_set.add(dir_path)

        if not dir_set:
            raise ValueError("dirs cannot be empty")

        return dir_set


class DupFinder:
    """
    The DupFinder class identifies duplicate files and empty files within specified directories.

    Symlink Handling:
        - Symlinks are **not** supported and are ignored during directory scanning.
            The module does not follow symbolic links to prevent potential infinite recursion
            and to ensure accurate duplicate detection based on actual file contents.

    Duplicates:
        - Files are considered duplicates if they have the same size and identical content
          (as verified by their MD5 hash).
        - Duplicate groups are stored in the `duplicates` property.

    Empty Files:
        - Files with a size of 0 bytes are recorded separately and can be accessed
          via the `empty_files` property.

    Attributes:
        - dirs (frozenset): The set of directories being scanned.
        - duplicates (dict): A mapping of file sizes to groups of duplicate files.
        - empty_files (list): A list of file paths corresponding to files with zero bytes.
    """

    def __init__(
        self,
        dirs: Iterable[str | pathlib.Path],
        chunk_size: int = 8192,
    ) -> None:
        """
        Initialize a DupFinder instance. An automatic scan for duplicates and empty files
        will be performed upon instantiation. Results can be accessed through the
        `duplicates` and `empty_files` properties.

        Args:
            dirs (Iterable[str | pathlib.Path]): An iterable of directory paths.
            chunk_size (int): Size of chunks for processing files, must be a positive integer.

        Raises:
            ValueError: If chunk_size is not a positive integer, dirs is empty,
                        or any path in dirs is not a valid directory.
            TypeError: If any item in dirs is not a string | pathlib.Path.
        """

        # Validate chunk size and set corresponding internal variable
        if not isinstance(chunk_size, int) or chunk_size <= 0:
            raise ValueError(
                f"chunk_size must be a positive integer, got {chunk_size} : {type(chunk_size).__name__}"
            )
        self.chunk_size = chunk_size

        # Validate dirs and set corresponding internal variable.
        self._dirs = DirectoryValidator.get_dir_set(dirs)

        # Initiate _empty_files and _duplicates attributes.
        self._empty_files: list[pathlib.Path] = []
        self._duplicates: dict[int, list[list[pathlib.Path]]] = {}

        # Set remaining instance attributes
        self._find_duplicates()  # Populates _empty_files and _duplicates attributes.

    @classmethod
    def _for_testing(
        cls,
        dirs: Iterable[str | pathlib.Path],
        chunk_size: int = 8192,
    ) -> DupFinder:
        """Creates new instance for testing purposes without automatic _find_duplicates call"""
        instance = cls.__new__(cls)  # Create the instance without calling __init__
        instance.chunk_size = chunk_size
        instance._dirs = DirectoryValidator.get_dir_set(dirs)
        instance._empty_files = []
        instance._duplicates = {}
        return instance

    def _find_duplicates(self) -> None:
        """
        Main function to find duplicates and empty files in the given directories.

        Steps:
        1. Group files by size using the _collect_files_by_size method.
        2. Populate `self._empty_files` with a list of files that have a size of 0 bytes.
        3. Identify potential duplicates, identified as more than 1 file of same size.
        4. Populate `self._duplicates` using the _filter_potential_duplicates method
        5. Convert actual duplicates to pathlib.Path instances

        self_duplicates = {
               size: [[dup1_path1, dup1_path2], [dup2_path1, ...], ...],
               ...
        }
        """
        # 1. Group files by size, delegates to _collect_files_by_size
        size_map = {}
        for dir_path in self._dirs:
            self._collect_files_by_size(dir_path, size_map)

        # 2. Pop empty files and populate _empty files attribute
        empty_files = [pathlib.Path(path) for path in size_map.pop(0, [])]
        self._empty_files.extend(empty_files)

        # 3. Get potential duplicates = more than 1 file of same size
        potential_duplicates = {
            size_value: paths
            for size_value, paths in size_map.items()
            if len(paths) > 1
        }
        del size_map

        # 4. Get duplicates from potential duplicate, delegates to _filter_potential_duplicates
        duplicates = self._filter_potential_duplicates(potential_duplicates)
        del potential_duplicates

        # 5. Convert actual duplicates to pathlib.Path instances
        for size_value, size_duplicates in duplicates.items():
            self._duplicates[size_value] = [
                [pathlib.Path(path) for path in path_list]
                for path_list in size_duplicates
            ]

    def _collect_files_by_size(
        self, dir_path: pathlib.Path | str, size_map: dict[int, list[str]]
    ) -> None:
        """
        Recursively traverse 'dir_path' using os.scandir, grouping file paths
        by file size in 'size_map' (a dict).

        size_map format:
            {
                file_size: [list_of_file_paths_with_that_size],
                ...
            }

        Args:
            dir_path (Path | str): The directory to scan recursively.
            size_map (dict): A dictionary mapping file sizes (int) to a list of file paths (str).

        Returns:
            None: This method modifies `size_map` in place.

        Notes:
            - If a file or subdirectory is inaccessible, a message is printed instead of raising an exception.
            - Symlinks are **not** followed; symbolic links are ignored during scanning.
            - Subdirectories are explored via recursion.
        """
        try:
            with os.scandir(dir_path) as entries:
                for entry in entries:
                    if entry.is_file(follow_symlinks=False):
                        try:
                            file_size = entry.stat().st_size
                            size_map.setdefault(file_size, []).append(entry.path)
                        except (OSError, PermissionError):
                            print(f"Could not access file: {entry.path}")
                    elif entry.is_dir(follow_symlinks=False):
                        # Recursively descend into subdirectories
                        self._collect_files_by_size(entry.path, size_map)
        except PermissionError:
            print(f"Permission denied: {dir_path}")

    def _filter_potential_duplicates(
        self, potential_duplicates: dict[int, list[str]]
    ) -> dict[int, list[list[str]]]:
        """
        Returns true duplicates as a dict mapping:
        { file size: list of duplicate groups }
            each group is a list of file paths.
        """
        file_paths = []
        file_sizez = []

        for size_value, paths in potential_duplicates.items():
            for path in paths:
                file_paths.append(path)
                file_sizez.append(size_value)

        with ProcessPoolExecutor() as executor:
            results = executor.map(
                DupFinder._get_file_hash,
                file_paths,
                [self.chunk_size] * len(file_paths),
                chunksize=32,
            )

        hashed_potential_duplicates = {}
        for i, file_hash in enumerate(results):
            if file_hash is not None:
                size_dict: dict = hashed_potential_duplicates.setdefault(
                    file_sizez[i], {}
                )
                size_dict.setdefault(file_hash, []).append(file_paths[i])

        duplicates = {}
        for size in tuple(hashed_potential_duplicates.keys()):
            hash_map = hashed_potential_duplicates.pop(size)
            size_duplicates = []

            for hash_equals in hash_map.values():
                if len(hash_equals) > 1:
                    size_duplicates.append(hash_equals)

            if size_duplicates:
                duplicates[size] = size_duplicates

        return duplicates

    @staticmethod
    def _get_file_hash(path: str, chunk_size: int) -> str | None:
        """
        Calculate the MD5 hash of a file and return it as a hexadecimal string.

        Args:
            path (str): The path to the file to hash.
            chunk_size (int): The size of the chunks to read from the file (in bytes).

        Returns:
            str | None: The MD5 hash of the file as a hexadecimal string
                if successful or None if an error occurs.

        Raises:
            ValueError: If `chunk_size` is less than or equal to 0.
        """
        if chunk_size <= 0:
            raise ValueError("chunk_size must be greater than 0")

        hasher = hashlib.md5()

        try:
            with open(path, "rb") as f:
                while chunk := f.read(chunk_size):
                    hasher.update(chunk)
        except (OSError, PermissionError):
            print(f"Could not read file for hashing: {path}")
            return None

        return hasher.hexdigest()

    def refresh(self) -> None:
        """
        Clears and re-populates the internal duplicates and empty_files data.

        This method:
            1. Empties the current `_empty_files` and `_duplicates` data.
            2. Re-runs the `_find_duplicates` process to discover duplicates and empty files.

        Returns:
            None
        """
        self._empty_files: list[pathlib.Path] = []
        self._duplicates: dict[int, list[list[pathlib.Path]]] = {}
        self._find_duplicates()  # Populates _empty_files and _duplicates attributes.

    def sort_duplicates_alphabetically(self) -> None:
        """Sort file duplicates accessible through self.duplicates by path (alphabetically)"""
        for _, duplicates_list in self._duplicates.items():
            for path_list in duplicates_list:
                path_list.sort()

    def get_size_sorted_duplicates(
        self, reverse: bool = True
    ) -> list[tuple[int, list[list[pathlib.Path]]]]:
        """
        Returns a list of (file_size, groups_of_duplicates) tuples, sorted by file size.

        Args:
            reverse (bool): If True (default), sort in descending order by file size.

        Returns:
            A list of tuples (size_value, list_of_duplicate_groups).
            Each duplicate group is a list of pathlib.Path objects representing files.
        """
        duplicate_list = list(self._duplicates.items())
        duplicate_list.sort(key=lambda x: x[0], reverse=reverse)
        return duplicate_list

    def print_duplicates(self, reverse: bool = True) -> None:
        """
        Print all detected duplicates, grouped by their file size.

        Args:
            reverse (bool): If True, prints larger file-size groups first.
                            Defaults to True.
        """
        duplicate_list = self.get_size_sorted_duplicates(reverse)

        if not duplicate_list:
            print("No duplicates found!")
            return

        print()
        msg = "The following files are duplicates"
        for size, list_of_dup_lists in duplicate_list:
            print(f"{msg}, filesize={size}:")
            for dup_list in list_of_dup_lists:
                for duplicate in dup_list:
                    print(f"{duplicate}")

                print()

    @property
    def dirs(self) -> frozenset[pathlib.Path]:
        """
        A frozenset of all directories this DupFinder scans.

        Returns:
            frozenset[pathlib.Path]: The set of scanned directories, as Path objects.
        """
        return frozenset(self._dirs)

    @property
    def duplicates(self) -> dict[int, list[list[pathlib.Path]]]:
        """
        Returns a dictionary mapping file sizes (int) to a list of groups of duplicate files.

        Each key in the dictionary is the file size (in bytes), and its value is a list of groups.
        Each group is a list of file paths (pathlib.Path objects) that are duplicates of one another.

        Example:
            {
                1024: [[Path("file1.txt"), Path("file2.txt")], [Path("file3.txt"), Path("file4.txt")]],
                ...
            }
        """
        return self._duplicates

    @property
    def empty_files(self) -> list[pathlib.Path]:
        """
        Returns a list of file-path pathlib.Path objects for all files that have a size of 0 bytes.

        Example:
            [Path("empty_file1.txt"), Path("empty_file2.txt")]
        """
        return self._empty_files


class DupHandler:
    """
    Provides functionality for handling duplicate files identified by a `DupFinder` instance.

    Features:
        - Removes duplicate files from specified directories.
        - Supports a dry run mode to simulate deletions without performing them.
        - Can refresh the state of the underlying `DupFinder` instance to ensure accurate results.

    Attributes:
        - finder (DupFinder): The `DupFinder` instance used for managing duplicates.
        - _deletions_occurred (bool): Tracks if deletions have been performed to ensure consistency.
    """

    def __init__(self, finder: DupFinder) -> None:
        """
        Initializes a new DupHandler instance.

        Args:
            finder (DupFinder): An instance of DupFinder used for discovering and tracking duplicates.

        Raises:
            TypeError: If the provided `finder` is not an instance of DupFinder.
        """

        if not isinstance(finder, DupFinder):
            raise TypeError(
                f"finder needs to be an instance of DupFinder. Got finder: {type(finder).__name__}"
            )

        self.finder = finder
        self._deletions_occurred = False

    def remove_dir_duplicates(
        self, dirs: list[pathlib.Path | str], dry_run: bool = False, force: bool = False
    ) -> tuple[list[pathlib.Path], list[pathlib.Path]]:
        """
        Remove duplicate files from the specified directories.

        Args:
            dirs (list[Path | str]): A list of directories where duplicates should be deleted.
            dry_run (bool): If True, simulate deletions without actually deleting files.
            force (bool): If True, bypasses the check for previously deleted duplicates. Use with caution.

        Returns:
            tuple[list[Path], list[Path]]:
                - A list of files successfully deleted.
                - A list of files that could not be deleted.

        Raises:
            ValueError: If previous deletions have occurred and `force` is not set to True.

        Notes:
            - Internally calls `_delete_files`, which catches common errors (`FileNotFoundError`,
              `PermissionError`, and other `OSError` exceptions). Any files that fail to be deleted
              for such reasons will be returned in the second list of the tuple.
        """

        # If previous deletions has occured the underlying DupFinder instance is inaccurate.
        if self._deletions_occurred and not force:
            raise ValueError(
                "You cannot perform additional deletions without using refresh or setting force=True"
                + "\nThis is because the underlying DupFinder.duplicates property will be inaccurate!"
                + "\nIf you are not very sure about what you are doing do NOT set force=True!"
                + "\nInstead use the refresh method on this DupHandler instance before calling this "
                + "method again."
            )

        # Validate dirs and resolve dirs
        dir_set = DirectoryValidator.get_dir_set(dirs)
        deleted_files = []
        failed_deletions = []

        for size_group in self.finder.duplicates.values():
            for duplicate_list in size_group:
                # Split paths into those in specified dirs where dups should be deleted and others
                dups_to_delete = [
                    path
                    for path in duplicate_list
                    if any(path.is_relative_to(d) for d in dir_set)
                ]

                dups_to_keep = [
                    path
                    for path in duplicate_list
                    if not any(path.is_relative_to(d) for d in dir_set)
                ]

                # If at least one duplicate exists outside parentdir1, delete the ones in parentdir1
                if dups_to_keep:
                    new_deletions, new_errors = self._delete_files(
                        dups_to_delete, dry_run
                    )
                    deleted_files.extend(new_deletions)
                    failed_deletions.extend(new_errors)

        return deleted_files, failed_deletions

    def _delete_files(
        self, files_to_delete: list[pathlib.Path], dry_run: bool = False
    ) -> tuple[list[pathlib.Path], list[pathlib.Path]]:
        """
        Deletes the specified files, with optional dry-run functionality.

        Args:
            files_to_delete (list[Path]): A list of file paths to be deleted.
            dry_run (bool): If True, simulate deletions without actually deleting files.

        Returns:
            tuple[list[Path], list[Path]]:
                - A list of files successfully deleted.
                - A list of files for which deletion failed.

        Internal Exceptions Handling:
            - FileNotFoundError: Caught if the file is already missing.
            - PermissionError: Caught if the file cannot be deleted due to access restrictions.
            - OSError: Caught for other system-related errors.

        Notes:
            - These exceptions are not re-raised; instead, they are logged, and the offending
              file paths are appended to the returned `failed_deletions` list.
        """
        deleted_files = []
        failed_deletions = []

        for file_path in files_to_delete:
            try:
                if not dry_run:
                    file_path.unlink()  # Deletes the file
                    self._deletions_occurred = True
                    print(f"Deleted: {file_path}")
                else:
                    print(f"Would have deleted: {file_path}")
                deleted_files.append(file_path)
            except FileNotFoundError:
                print(f"File not found (already deleted?): {file_path}")
                failed_deletions.append(file_path)
            except PermissionError:
                print(f"Permission denied: {file_path}")
                failed_deletions.append(file_path)
            except OSError as e:
                print(f"Error deleting {file_path}: {e}")
                failed_deletions.append(file_path)

        return deleted_files, failed_deletions

    def refresh(self):
        """
        Refresh the state of the `DupHandler` by calling the `refresh` method on
        the underlying `DupFinder` instance. Also resets the `_deletions_occurred` flag.
        """
        self.finder.refresh()
        self._deletions_occurred = False
