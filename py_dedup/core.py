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
    def get_dir_set(dirs: Iterable[pathlib.Path | str]) -> set[pathlib.Path]:
        """
        Validates and resolves a list of directories into a set of Path objects.

        Args:
            dirs (Iterable[Path | str]): An iterable of directory paths.

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
        4. Get actual duplicates using the _filter_potential_duplicates method
        5. Convert actual duplicates to pathlib.Path instances and store final result
            in `self._duplicates` (format below).
        {
               size: [[dup1_path1, dup1_path2], [dup2_path1, ...], ...],
               ...
        }
        """
        # 1. Group files by size, delegates to _collect_files_by_size.
        # size_map will be modified in place by _collect_files_by_size.
        size_map: dict[int, list[str]] = {}
        for dir_path in self._dirs:
            self._collect_files_by_size(dir_path, size_map)

        # 2. Pop empty files and populate _empty files attribute
        empty_files = [pathlib.Path(path) for path in size_map.pop(0, [])]
        self._empty_files.extend(empty_files)

        # 3. Get potential duplicates = more than 1 file of same size
        potential_duplicates = []
        potential_duplicates_sizes = []  # Will be needed to create duplicates dict
        for file_size in tuple(size_map.keys()):
            paths = size_map.pop(file_size)
            if (num_paths := len(paths)) > 1:
                potential_duplicates.extend(paths)
                potential_duplicates_sizes.extend([file_size] * num_paths)

        # 4. Get duplicates from potential duplicate, delegates to _filter_potential_duplicates
        duplicates = self._filter_potential_duplicates(
            potential_duplicates, potential_duplicates_sizes
        )
        del potential_duplicates
        del potential_duplicates_sizes

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
        Recursively traverse a directory and group files by their size, storing results in `size_map`.

        The `size_map` dictionary has the form:
            {
                file_size: ["path/to/file1", "path/to/file2", ...],
                ...
            }

        Args:
            dir_path (pathlib.Path | str): The directory to scan.
            size_map (dict[int, list[str]]): A dictionary mapping file sizes to lists of file paths.
                This is modified in-place.

        Notes:
            - This method modifies the argument `size_map` in place.
            - Ignores symlinks (not followed).
            - Prints a message instead of raising an exception if a file/directory is inaccessible.
            - Descends into subdirectories recursively.
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
        self, potential_duplicates: list[str], potential_duplicates_sizes: list[int]
    ) -> dict[int, list[list[str]]]:
        """
        Filter potential duplicates by hashing each file (MD5), using multiprocessing for performance.

        Args:
            potential_duplicates (list[str]): The file paths that might be duplicates.
            potential_duplicates_sizes (list[int]): The file sizes corresponding to each path in
                `potential_duplicates`. Indices in this list match the order of `potential_duplicates`.

        Returns:
            dict[int, list[list[str]]]: A mapping of file size (int) to groups of duplicate files.
            Example structure:
                {
                    1024: [
                        ["path/to/dup1a", "path/to/dup1b"],
                        ["path/to/dup2a", "path/to/dup2b", "path/to/dup2c"]
                    ],
                    2048: [...]
                }
        """
        # 1. Hash potential duplicates
        with ProcessPoolExecutor() as executor:
            results = executor.map(
                DupFinder._get_file_hash,
                potential_duplicates,
                [self.chunk_size] * len(potential_duplicates),
                chunksize=32,
            )

        # 2. Create hash dict (hashed_potential_duplicates):
        # {size1: {hash_val1: [path1, ...], hash_val2: [...]}, size2: {...}}
        hashed_potential_duplicates: dict[int, dict[str, list[str]]] = {}
        for i, file_hash in enumerate(results):
            if file_hash is not None:
                size_dict: dict = hashed_potential_duplicates.setdefault(
                    potential_duplicates_sizes[i], {}
                )
                size_dict.setdefault(file_hash, []).append(potential_duplicates[i])

        # 3. Loop through hashed_potential_duplicates adding only actual duplicates
        #       to the duplicates dict (only if > 1 file with same hash).
        # {
        #     size1: [[dup1_path1, dup1_path2], [dup2_path1, ...], ...],
        #     size2: [[...], ...]
        # }
        duplicates: dict[int, list[list[str]]] = {}
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

    def get_duplicates_string(self, reverse: bool = True) -> str:
        """
        Get a string a string representation of all detected duplicates.

        Args:
            reverse (bool): If True, prints larger file-size groups first.
                            Defaults to True.

        Returns:
            A string of all detected duplicates grouped by their file size.
        """
        duplicate_list = self.get_size_sorted_duplicates(reverse)

        if not duplicate_list:
            return "No duplicates found!"

        output = ""
        msg = "The following files are duplicates"

        for size, list_of_dup_lists in duplicate_list:
            for dup_list in list_of_dup_lists:
                output += f"\n{msg}, filesize={size}:\n"
                for duplicate in dup_list:
                    output += f"{duplicate}\n"

        return output + "\n"

    def print_duplicates(self, reverse: bool = True) -> None:
        """
        Print all detected duplicates, grouped by their file size.

        Args:
            reverse (bool): If True, prints larger file-size groups first.
                            Defaults to True.
        """
        output = self.get_duplicates_string(reverse)
        print(output)

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
          When duplicates are found, if at least one copy exists outside the deletion
          directories, all duplicates within those directories are removed; otherwise,
          all except one copy (selected by sorted order) are deleted.
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
    ) -> tuple[list[pathlib.Path], list[tuple[pathlib.Path, Exception]]]:
        """
        Remove duplicate files from the specified directories.

        For each duplicate group, this method determines the files that reside in the
        deletion directories. If at least one duplicate exists outside the deletion
        directories, then all duplicates found within the deletion directories are removed.
        However, if all duplicates are located within the deletion directories, then all
        except one (selected by sorted order) are deleted to ensure at least one copy remains.

        Args:
            dirs (list[Path | str]): A list of directories where duplicates should be deleted.
            dry_run (bool): If True, simulate deletions without actually deleting files.
            force (bool): If True, bypasses the check for previously deleted duplicates. Use with caution.

        Returns:
            tuple[list[pathlib.Path], list[tuple[pathlib.Path, Exception]]]:
                - A list of files (as pathlib.Path objects) that were successfully deleted.
                - A list of tuples (file, exception) for files that could not be deleted.

        Raises:
            ValueError: If previous deletions have occurred and `force` is not set to True.

        Notes:
            - Internally calls `_delete_files`, which handles common errors such as FileNotFoundError,
              PermissionError, and other OSError exceptions.
        """
        if self._deletions_occurred and not force:
            raise ValueError(
                "You cannot perform additional deletions without using refresh or setting force=True"
                + "\nThis is because the underlying DupFinder.duplicates property will be inaccurate!"
                + "\nIf you are not very sure about what you are doing do NOT set force=True!"
                + "\nInstead use the refresh method on this DupHandler instance before calling this method again."
            )

        # Validate dirs and resolve them
        dir_set = DirectoryValidator.get_dir_set(dirs)
        deleted_files = []
        failed_deletions = []

        for size_group in self.finder.duplicates.values():
            for duplicate_list in size_group:
                # Find files that reside inside any of the delete dirs.
                dups_to_delete = [
                    path
                    for path in duplicate_list
                    if any(path.is_relative_to(d) for d in dir_set)
                ]

                if not dups_to_delete:
                    continue

                # If not all files in the duplicate group are in the delete dirs,
                # delete all duplicates in the delete dirs.
                # Otherwise, if all are in delete dirs, keep one copy (using sorted order) and delete the rest.
                dups_to_keep = len(dups_to_delete) < len(duplicate_list)
                files_to_remove = (
                    dups_to_delete if dups_to_keep else sorted(dups_to_delete)[1:]
                )

                new_deletions, error_tuples = self._delete_files(
                    files_to_remove, dry_run
                )
                deleted_files.extend(new_deletions)
                failed_deletions.extend(error_tuples)

        return deleted_files, failed_deletions

    def _delete_files(
        self, files_to_delete: list[pathlib.Path], dry_run: bool = False
    ) -> tuple[list[pathlib.Path], list[tuple[pathlib.Path, Exception]]]:
        """
        Deletes the specified files, with optional dry-run functionality.

        Args:
            files_to_delete (list[pathlib.Path]): A list of file paths to be deleted.
            dry_run (bool): If True, simulate deletions without actually deleting files.

        Returns:
            tuple[list[pathlib.Path], list[tuple[pathlib.Path, Exception]]]:
                A two-element tuple:
                  1. The files successfully deleted (or that would have been in a dry run).
                  2. A list of tuples, each containing the file that could not be deleted
                     and the exception that occurred.
        """
        deleted_files = []
        failed_deletions = []

        for file_path in files_to_delete:
            try:
                if not dry_run:
                    file_path.unlink()  # Deletes the file
                    self._deletions_occurred = True
                # In dry run, we consider it as a successful simulation
                deleted_files.append(file_path)
            except (FileNotFoundError, PermissionError, OSError) as e:
                failed_deletions.append((file_path, e))

        return deleted_files, failed_deletions

    def refresh(self):
        """
        Refresh the state of the `DupHandler` by calling the `refresh` method on
        the underlying `DupFinder` instance. Also resets the `_deletions_occurred` flag.
        """
        self.finder.refresh()
        self._deletions_occurred = False
