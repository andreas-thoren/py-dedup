"""Contains code for the cli interface"""

import sys
import argparse
from datetime import timedelta
from .core import DupFinder, DupHandler
from .persistent_cache import (
    get_current_tempfile,
    cleanup_user_tempfiles,
    create_tempfile,
    unpickle_dupfinder,
    pickle_dupfinder,
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
        "find": lambda: find_duplicates(args.directories),
        "show-duplicates": lambda: show_duplicates(args.directories, args.threshold),
        "delete": lambda: delete_duplicates(
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


def find_duplicates(dirs: list[str]) -> None:
    finder = DupFinder(dirs)
    finder.sort_duplicates_alphabetically()
    finder.print_duplicates()

    tmp_file = get_current_tempfile(dirs) or create_tempfile(dirs)
    pickle_dupfinder(finder=finder, path=tmp_file)


def show_duplicates(dirs: list[str], threshold: int) -> None:
    threshold = timedelta(minutes=threshold)
    tmp_file = get_current_tempfile(dirs, threshold)
    if tmp_file is None:
        print(
            f"No cached result for dirs: {dirs} exist within threshold. Use py-dedup find"
        )
        return

    finder = unpickle_dupfinder(tmp_file)
    if finder is None:
        print(f"Error reading cache for dirs: {dirs}. Use py-dedup find instead!")
        return

    if not finder.duplicates:
        print(f"No duplicates exist in dirs: {dirs}")

    finder.sort_duplicates_alphabetically()
    finder.print_duplicates()


def delete_duplicates(dirs: list[str], delete_dirs: list[str], dry_run: bool) -> None:
    # Attempt to retrieve DupFinder instance from cache
    tmp_file = get_current_tempfile(dirs)
    finder = unpickle_dupfinder(tmp_file) if tmp_file else None

    # If unpickling failed or no cache exists, create a new instance
    if finder is None:
        finder = DupFinder(dirs)
        tmp_file = tmp_file or create_tempfile(dirs)
        pickle_dupfinder(finder=finder, path=tmp_file)

    # Instantiate DupHandler and perform deletions (if not dry_run=True)
    handler = DupHandler(finder=finder)
    deleted_files, error_files = handler.remove_dir_duplicates(
        dirs=delete_dirs, dry_run=dry_run
    )

    # Present result for user
    delete_msg = "Would have deleted (dry_run=True)" if dry_run else "Deleted"
    for deleted_file in deleted_files:
        print(f"{delete_msg}: {deleted_file}")

    for error_file in error_files:
        print(f"Error deleting: {error_file}")

    # If actual file deletions took place delete cache (not current any longer)
    if tmp_file and deleted_files and not dry_run:
        tmp_file.unlink(missing_ok=True)


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
        "find", help="Find duplicate files in specified directories."
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
        "delete", help="Delete duplicate files in specified directories."
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
