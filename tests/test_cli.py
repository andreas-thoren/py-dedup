import io
import unittest
from unittest.mock import patch
from py_dedup.cli import parse_args


class TestParseArgs(unittest.TestCase):
    def test_find_duplicates(self):
        args = parse_args(["find-duplicates", "dir1", "dir2"])
        self.assertEqual(args.command, "find-duplicates")
        self.assertEqual(args.directories, ["dir1", "dir2"])

    def test_show_duplicates_with_threshold(self):
        args = parse_args(["show-duplicates", "dir1", "dir2", "--threshold", "100"])
        self.assertEqual(args.command, "show-duplicates")
        self.assertEqual(args.directories, ["dir1", "dir2"])
        self.assertEqual(args.threshold, 100)

    def test_show_duplicates_default_threshold(self):
        # If threshold is not provided, default should be 1440
        args = parse_args(["show-duplicates", "dir1"])
        self.assertEqual(args.command, "show-duplicates")
        self.assertEqual(args.directories, ["dir1"])
        self.assertEqual(args.threshold, 1440)

    def test_delete_duplicates(self):
        args = parse_args(
            [
                "delete-duplicates",
                "dir1",
                "dir2",
                "--delete-dirs",
                "dir3",
                "dir4",
                "--dry-run",
            ]
        )
        self.assertEqual(args.command, "delete-duplicates")
        self.assertEqual(args.directories, ["dir1", "dir2"])
        self.assertEqual(args.delete_dirs, ["dir3", "dir4"])
        self.assertTrue(args.dry_run)

    def test_delete_duplicates_missing_delete_dirs(self):
        # Patch sys.stderr to suppress argparse help message output.
        with patch("sys.stderr", new_callable=io.StringIO):
            # Missing the required --delete-dirs argument
            # should cause the parser to exit
            with self.assertRaises(SystemExit):
                parse_args(["delete-duplicates", "dir1", "dir2"])

    def test_clear_cache(self):
        args = parse_args(["clear-cache"])
        self.assertEqual(args.command, "clear-cache")

    def test_no_arguments(self):
        # Patch sys.stderr to suppress argparse help message output.
        with patch("sys.stderr", new_callable=io.StringIO):
            # If no arguments are provided,
            # argparse should exit with an error
            with self.assertRaises(SystemExit):
                parse_args([])


if __name__ == "__main__":
    unittest.main()
