"""Contains code for the cli interface"""

import sys
import argparse
from .core import DupFinder


def main(arguments: list[str] | None = None) -> None:
    """main function of the cli interface"""
    args = parse_args(arguments if arguments is not None else sys.argv[1:])

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


def delete_duplicates(dirs: list[str], delete_dirs: list[str], dry_run: bool) -> None:
    print("TODO")
    print(f"Called with dirs: {dirs}, delete_dirs: {delete_dirs}, dry_run: {dry_run}")


def clear_cache() -> None:
    print("TODO")


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
