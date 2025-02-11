"""Contains code for the cli interface"""

import sys
import argparse
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

    if args.command == "find":
        find_duplicates(args.directories)
    elif args.command == "delete":
        delete_duplicates(args.directories, args.delete_dirs, args.dry_run)
    elif args.command == "clear-cache":
        clear_cache()
    else:
        raise ValueError(f"py-dedup called with erroneous command: {args.command}")


def find_duplicates(dirs: list[str]) -> None:
    finder = DupFinder(dirs=dirs)
    finder.sort_duplicates_alphabetically()
    finder.print_duplicates()

    tmp_file = get_current_tempfile(dirs=dirs) or create_tempfile(dirs=dirs)
    pickle_dupfinder(finder=finder, path=tmp_file)


def delete_duplicates(dirs: list[str], delete_dirs: list[str], dry_run: bool) -> None:
    # Attempt to retrieve DupFinder instance from cache
    tmp_file = get_current_tempfile(dirs)
    finder = unpickle_dupfinder(tmp_file) if tmp_file else None

    # If unpickling failed or no cache exists, create a new instance
    if finder is None:
        finder = DupFinder(dirs=dirs)
        tmp_file = tmp_file or create_tempfile(dirs=dirs)
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
    cleanup_user_tempfiles()


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
