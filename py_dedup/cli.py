"""Contains code for the cli interface"""

import sys
import argparse
from .core import DupFinder


def main(arguments: list[str] | None = None) -> None:
    """main function of the cli interface"""
    args = parse_args(arguments if arguments is not None else sys.argv[1:])
    finder = DupFinder(dirs=args.directories)
    finder.sort_duplicates_alphabetically()
    finder.print_duplicates()


def parse_args(arguments: list[str]) -> argparse.Namespace:
    """Parses command-line arguments."""
    parser = argparse.ArgumentParser(
        description="py-dedup: A tool to find and handle duplicate files."
    )

    parser.add_argument(
        "directories", nargs="+", help="Directories to scan for duplicates."
    )

    return parser.parse_args(arguments)


if __name__ == "__main__":
    main()
