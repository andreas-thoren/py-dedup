import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from py_dedup.core import DupFinder, DupHandler
from py_dedup.cli import (
    parse_args,
    find_duplicates,
    delete_duplicates,
    delete_empty_files,
)
from py_dedup.persistent_cache import (
    get_tempfile_prefix,
    cleanup_user_tempfiles,
    get_current_tempfile,
    TMP_FILE_SUFFIX,
    unpickle_dupfinder,
)
from .global_test_vars import TEST_DIR, CMPR_DIR
from .utils_tests import dupfinders_are_equal, get_dry_run_deleted_paths


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

    def test_delete_duplicates_with_duplicate_delete_args(self):
        """
        Providing both --delete-dirs and --delete-patterns should raise an error.
        """
        with patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(SystemExit):
                parse_args(
                    [
                        "delete-duplicates",
                        "dir1",
                        "dir2",
                        "--delete-dirs",
                        "dir3",
                        "--delete-patterns",
                        "*.log",
                        "*.bak",
                        "--dry-run",
                    ]
                )

    def test_delete_empty_parse_args_dryrun(self):
        """
        Ensure that the delete-empty command correctly parses the dry-run flag.
        """
        args = parse_args(["delete-empty", "dir1", "-n"])
        self.assertEqual(args.command, "delete-empty")
        self.assertEqual(args.directories, ["dir1"])
        self.assertTrue(args.dry_run)
        self.assertEqual(args.threshold, 1440)


class TestCLIFuncs(unittest.TestCase):
    def setUp(self):
        """
        Create a temporary directory structure and files for testing remove_glob_duplicates.
        This method runs before each test method below.
        """
        self.dirs = [str(TEST_DIR), str(CMPR_DIR)]

    def tearDown(self):
        """
        Remove the temporary testing directory after each test.
        """
        prefix = get_tempfile_prefix(self.dirs)
        pattern = f"{prefix}*{TMP_FILE_SUFFIX}"
        cleanup_user_tempfiles(pattern)

    def test_find_duplicates(self):
        # Call find_duplicates without printing output
        dirs = self.dirs
        with patch("sys.stdout", new_callable=io.StringIO):
            find_duplicates(dirs)

        # Make sure cached dupfinder equals finder created directly
        path = get_current_tempfile(dirs)
        cached_finder = unpickle_dupfinder(path)
        finder = DupFinder(dirs)
        finder.sort_duplicates_alphabetically()
        self.assertTrue(dupfinders_are_equal(finder, cached_finder))

    def test_delete_duplicates_delete_dirs(self):
        dirs = self.dirs
        output = io.StringIO()

        with redirect_stdout(output):
            delete_duplicates(dirs, delete_dirs=[str(CMPR_DIR)], dry_run=True)

        deleted_paths = get_dry_run_deleted_paths(output)

        finder = DupFinder(dirs)
        handler = DupHandler(finder)
        deleted, _ = handler.remove_dir_duplicates([CMPR_DIR], dry_run=True)

        # Same files should be dry_run deleted by delete_duplicates as by the
        # programatic API
        self.assertEqual(deleted_paths, set(deleted))

        # Since dry_run=True no deletions should have taken place
        self.assertTrue(all(path.exists() for path in deleted_paths))

    def test_delete_duplicates_delete_patterns(self):
        dirs = self.dirs
        output = io.StringIO()

        with redirect_stdout(output):
            delete_duplicates(dirs, delete_patterns=["*.txt"], dry_run=True)

        deleted_paths = get_dry_run_deleted_paths(output)

        finder = DupFinder(dirs)
        handler = DupHandler(finder)
        deleted, _ = handler.remove_glob_duplicates(["*.txt"], dry_run=True)

        # Same files should be dry_run deleted by delete_duplicates as by the
        # programatic API
        self.assertEqual(deleted_paths, set(deleted))

        # Since dry_run=True no deletions should have taken place
        self.assertTrue(all(path.exists() for path in deleted_paths))

    def test_delete_empty_dry_run(self):
        """
        Test the delete-empty CLI command in dry-run mode such that empty files are reported as deleted.
        """
        dirs = self.dirs
        output = io.StringIO()

        with redirect_stdout(output):
            delete_empty_files(dirs, dry_run=True)

        deleted_paths = get_dry_run_deleted_paths(output)

        finder = DupFinder(dirs)
        handler = DupHandler(finder)
        deleted, _ = handler.delete_empty_files(dry_run=True)

        # Same files should be dry_run deleted by delete_empty_files as by the
        # programatic API
        self.assertEqual(deleted_paths, set(deleted))

        # Since dry_run=True no deletions should have taken place
        self.assertTrue(all(path.exists() for path in deleted_paths))


if __name__ == "__main__":
    unittest.main()
