"""Contains code for the cli interface"""

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
    """main function of the cli interface"""
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
    prefix = get_tempfile_prefix(dirs)
    pattern = f"{prefix}*{TMP_FILE_SUFFIX}"
    cleanup_user_tempfiles(pattern=pattern)
    return create_tempfile(dirs)


def find_duplicates(dirs: list[str]) -> None:
    finder = DupFinder(dirs)
    finder.sort_duplicates_alphabetically()

    # If output in terminal use pager else print
    if sys.stdout.isatty():
        output = finder.get_duplicates_string()
        pydoc.pager(output)
    else:
        finder.print_duplicates()

    tmp_file = set_cache(dirs)
    pickle_dupfinder(finder=finder, path=tmp_file)


def show_duplicates(dirs: list[str], threshold: int) -> None:
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

    finder.sort_duplicates_alphabetically()

    # If output in terminal use pager else print
    if sys.stdout.isatty():
        output = finder.get_duplicates_string()
        pydoc.pager(output)
    else:
        finder.print_duplicates()


def delete_duplicates(dirs: list[str], delete_dirs: list[str], dry_run: bool) -> None:
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

    # If output in terminal use pager else print
    if sys.stdout.isatty():
        pydoc.pager(output)
    else:
        print(output)

    # If actual file deletions took place delete cache (not current any longer)
    if deleted_files and not dry_run:
        pattern = f"{get_tempfile_prefix(dirs)}*{TMP_FILE_SUFFIX}"
        cleanup_user_tempfiles(pattern=pattern)


def clear_cache() -> None:
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
    """Parses command-line arguments with subcommands."""
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
