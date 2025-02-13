"""
This module provides a command-line interface (CLI) for interacting with py-dedup.

The CLI allows users to:
    - Find duplicate files within specified directories.
    - View cached duplicate results if available.
    - Delete duplicate files from specified directories.
    - Clear cached duplicate results.

Commands:
    - find-duplicates: Scans specified directories for duplicate files.
    - show-duplicates: Displays cached duplicate results.
    - delete-duplicates: Removes duplicate files, ensuring at least one copy remains elsewhere.
    - clear-cache: Deletes all cached scan results.

Typical usage example:
    >>> py-dedup find-duplicates /path/dir1 /path/dir2
    >>> py-dedup show-duplicates /path/dir1 --threshold 60
    >>> py-dedup delete-duplicates /path/dir1 /path/dir2 --delete-dirs /path/dir2 -n
    >>> py-dedup clear-cache
"""

import sys
import argparse
import pathlib
import pydoc
from datetime import timedelta
from .core import DupFinder, DupHandler
from .persistent_cache import (
    get_current_tempfile,
    get_tempfile_prefix,
    cleanup_user_tempfiles,
    create_tempfile,
    unpickle_dupfinder,
    pickle_dupfinder,
    TMP_FILE_SUFFIX,
)


def main(arguments: list[str] | None = None) -> None:
    """
    Parses CLI arguments and executes the corresponding command.

    Args:
        arguments (list[str] | None): Command-line arguments, defaults to None.

    Raises:
        ValueError: If an invalid command is provided.
    """
    if arguments is None:
        arguments = sys.argv[1:]

    if not arguments:  # Handle case where no arguments are provided
        print("No command provided. Use --help for usage details.")
        sys.exit(1)

    args = parse_args(arguments)

    commands = {
        "find-duplicates": lambda: find_duplicates(args.directories),
        "show-duplicates": lambda: show_duplicates(args.directories, args.threshold),
        "delete-duplicates": lambda: delete_duplicates(
            args.directories, args.delete_dirs, args.dry_run
        ),
        "clear-cache": clear_cache,
    }

    try:
        commands[args.command]()
    except KeyError as exc:
        raise ValueError(
            f"py-dedup called with erroneous command: {args.command}"
        ) from exc


def set_cache(dirs: list[str]) -> pathlib.Path:
    """
    1. Deletes previous cache files from duplicate scanning of the specific dirs.
    2. Creates a temporary cache file for storing future duplicate scan results
        with the specific dirs as arguments.

    Args:
        dirs (list[str]): The dirs associated with the cache file/files.

    Returns:
        pathlib.Path: The path to the created cache file.
    """
    prefix = get_tempfile_prefix(dirs)
    pattern = f"{prefix}*{TMP_FILE_SUFFIX}"
    cleanup_user_tempfiles(pattern=pattern)
    return create_tempfile(dirs)


def display_output(output: str) -> None:
    """
    Displays output using a pager if in an interactive terminal,
    otherwise prints to stdout.

    Args:
        output (str): The output string to be displayed.
    """
    # If output in terminal use pager else print
    if sys.stdout.isatty():
        pydoc.pager(output)
    else:
        print(output)


def find_duplicates(dirs: list[str]) -> None:
    """
    Finds duplicate files in the specified directories and caches the results.

    Args:
        dirs (list[str]): The list of directories to scan.
    """
    finder = DupFinder(dirs)
    finder.sort_duplicates_alphabetically()

    output = finder.get_duplicates_string()
    display_output(output)

    tmp_file = set_cache(dirs)
    pickle_dupfinder(finder=finder, path=tmp_file)


def show_duplicates(dirs: list[str], threshold: int) -> None:
    """
    Displays cached duplicate results if available within the given time threshold.

    Args:
        dirs (list[str]): The list of directories to show duplicates in.
        threshold (int): The threshold time in minutes for cache validity.
    """
    threshold = timedelta(minutes=threshold)
    tmp_file = get_current_tempfile(dirs, threshold)
    if tmp_file is None:
        print(
            f"No cached result for dirs: {dirs} exist within threshold. Use py-dedup find-duplicates"
        )
        return

    finder = unpickle_dupfinder(tmp_file)
    if finder is None:
        print(
            f"Error reading cache for dirs: {dirs}. Use py-dedup find-duplicates instead!"
        )
        return

    if not finder.duplicates:
        print(f"No duplicates exist in dirs: {dirs}")

    # If output in terminal use pager else print
    output = finder.get_duplicates_string()
    display_output(output)


def delete_duplicates(dirs: list[str], delete_dirs: list[str], dry_run: bool) -> None:
    """
    1. Scans direcories (dirs) for duplicates (or loads cached results).
    2. Removes duplicate files from the specified directories (delete_dirs)
        while ensuring at least one copy remains elsewhere.

    Args:
        dirs (list[str]): The directories to scan for duplicates.
        delete_dirs (list[str]): The directories where duplicates should be deleted.
        dry_run (bool): If True, simulates deletions without actually removing files.

    Raises:
        ValueError: If an issue occurs during deletion or file retrieval.

    Notes:
        - Only duplicates found within `delete_dirs` are removed.
        - If `dry_run` is enabled, no actual deletions occur, only a preview is provided.
    """
    # Attempt to retrieve DupFinder instance from cache
    tmp_file = get_current_tempfile(dirs)
    finder = unpickle_dupfinder(tmp_file) if tmp_file else None

    # If unpickling failed or no cache exists, create a new instance
    if finder is None:
        finder = DupFinder(dirs)
        tmp_file = set_cache(dirs)
        pickle_dupfinder(finder=finder, path=tmp_file)

    # Instantiate DupHandler and perform deletions (if not dry_run=True)
    handler = DupHandler(finder=finder)
    deleted_files, error_files = handler.remove_dir_duplicates(
        dirs=delete_dirs, dry_run=dry_run
    )

    # Create output string from return of remove_dir_duplicates
    msg = "Would have deleted:" if dry_run else "Deleted:"
    del_output = "\n".join(f"{msg} {path}" for path in deleted_files)
    err_output = "\n".join(
        f"Error deleting: {path}, Exception: {exc}" for path, exc in error_files
    )
    output = f"{del_output}\n\n{err_output}\n" if err_output else f"{del_output}\n"
    display_output(output)

    # If actual file deletions took place delete cache (not current any longer)
    if deleted_files and not dry_run:
        pattern = f"{get_tempfile_prefix(dirs)}*{TMP_FILE_SUFFIX}"
        cleanup_user_tempfiles(pattern=pattern)


def clear_cache() -> None:
    """
    Clears all cached duplicate scan results.
    """
    deleted_files, error_files = cleanup_user_tempfiles()

    if deleted_files:
        print(
            "Deleted the following temp files:\n"
            + "\n".join(str(path) for path in deleted_files)
        )

    if error_files:
        print(
            "Error deleting the following temp files:\n"
            + "\n".join(str(path) for path in error_files)
        )


def parse_args(arguments: list[str]) -> argparse.Namespace:
    """
    Parses command-line arguments and returns an argparse.Namespace object.

    Args:
        arguments (list[str]): List of command-line arguments to be parsed.

    Returns:
        argparse.Namespace: Parsed arguments containing command and its options.

    Raises:
        SystemExit: If invalid arguments are provided.
    """
    parser = argparse.ArgumentParser(
        description="py-dedup: A tool to find and handle duplicate files."
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subparser for finding duplicates
    find_parser = subparsers.add_parser(
        "find-duplicates", help="Find duplicate files in specified directories."
    )
    find_parser.add_argument(
        "directories", nargs="+", help="Directories to scan for duplicates."
    )

    # Subparser for showing cached duplicates
    show_parser = subparsers.add_parser(
        "show-duplicates", help="Show cached duplicate results if available."
    )
    show_parser.add_argument(
        "directories",
        nargs="+",
        help="Directories to show cached result for duplicates.",
    )
    show_parser.add_argument(
        "--threshold",
        type=int,
        default=1440,
        help="Threshold (in minutes) to consider cache valid. Default: 1440 (1 day).",
    )

    # Subparser for deleting duplicates
    delete_parser = subparsers.add_parser(
        "delete-duplicates", help="Delete duplicate files in specified directories."
    )
    delete_parser.add_argument(
        "directories", nargs="+", help="Directories to scan for duplicates."
    )
    delete_parser.add_argument(
        "--delete-dirs",
        nargs="+",
        required=True,
        help="Directories where duplicates should be deleted if at least one copy exists elsewhere.",
    )
    delete_parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Perform a dry run without deleting files.",
    )

    # Subparser for clearing cache
    subparsers.add_parser("clear-cache", help="Clear the persistent cache.")

    return parser.parse_args(arguments)


if __name__ == "__main__":
    main()
