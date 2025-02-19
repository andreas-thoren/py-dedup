import unittest
import shutil
from py_dedup import DupFinder, DupHandler
from tests.global_test_vars import (
    TEST_DATA_DIR,
    TEST_DIR,
    CMPR_DIR,
    EXPECTED_DUPLICATES,
)


class TestDupFinderWithTestData(unittest.TestCase):
    def test_init_with_invalid_chunk_size(self):
        """
        Check that chunk_size must be a positive integer.
        """
        with self.assertRaises(ValueError):
            DupFinder(dirs=[TEST_DIR], chunk_size=0)  # 0 is invalid

        with self.assertRaises(ValueError):
            DupFinder(dirs=[TEST_DIR], chunk_size=-10)  # negative is invalid

    def test_init_with_empty_dirs(self):
        """
        Check that an empty 'dirs' list raises ValueError.
        """
        with self.assertRaises(ValueError):
            DupFinder(dirs=[])

    def test_init_with_nonexistent_dir(self):
        """
        Pass a directory path that does not exist. Should raise ValueError.
        """
        fake_path = TEST_DATA_DIR / "does_not_exist"
        with self.assertRaises(ValueError):
            DupFinder(dirs=[fake_path])

    def test_init_with_wrong_type_dir(self):
        """
        Passing an invalid type (non-string/Path) in 'dirs' should raise TypeError.
        """
        with self.assertRaises(TypeError):
            DupFinder(dirs=[123])  # not str or pathlib.Path

    def test_no_duplicates_in_single_dir(self):
        """
        When scanning only 'test_dir', we expect zero duplicates.
        (Even though 'common1.txt' or 'common2.txt' exist, each appears only once here.)
        """
        handler = DupFinder(dirs=[TEST_DIR])
        self.assertEqual(
            len(handler.duplicates),
            0,
            "No duplicates should be found when scanning only one directory.",
        )

    def test_duplicates_between_two_dirs(self):
        """
        When scanning both 'TEST_DIR' and 'CMPR_DIR', we expect to find:
          1) common1.txt in both
          2) common_dir/common2.txt in both
          3) common_dir/common_empty1 in both (if it's considered duplicate).
        We verify that each set is present.
        """
        handler = DupFinder(dirs=[TEST_DIR, CMPR_DIR])
        duplicates = handler.duplicates

        # We expect something to be duplicated, so duplicates should not be empty.
        self.assertTrue(duplicates, "Expected duplicates but found none.")

        # Convert dicitionary values
        # from list[list[pathlib.Path, ...], ...]
        # to frozenset(frosenzet(pathlib.Path, ...), ...) for each size group
        all_duplicates = []
        for _, list_of_groups in duplicates.items():
            size_duplicates = frozenset(
                frozenset(dup_list) for dup_list in list_of_groups
            )
            all_duplicates.append(size_duplicates)

        # all_duplicates_frozen: frozenset(frozenset(frozenset(pathlib.Path, ...), ...), ...)
        all_duplicates_frozen = frozenset(all_duplicates)
        self.assertEqual(EXPECTED_DUPLICATES, all_duplicates_frozen)

    def test_dirs_property(self):
        """
        Ensure the dirs property reflects what we passed in.
        """
        handler = DupFinder(dirs=[TEST_DIR, CMPR_DIR])
        # dirs property is a frozenset of resolved Paths
        # We'll check that both test_dir and cmpr_dir are in there.
        result_dirs = handler.dirs

        # Compare as Path objects (no need to cast to str)
        self.assertIn(TEST_DIR.resolve(), result_dirs)
        self.assertIn(CMPR_DIR.resolve(), result_dirs)


class TestDupHandler(unittest.TestCase):
    def setUp(self):
        """
        Create a temporary directory structure and files for testing remove_dir_duplicates.
        This method runs before each test method below.
        """
        self.temp_dir = TEST_DATA_DIR / "temp_handler_test_dir"
        self.temp_dir.mkdir(exist_ok=False)

        # Create subdirectories
        self.sub_dir_1 = self.temp_dir / "sub1"
        self.sub_dir_1.mkdir(exist_ok=False)
        self.sub_dir_2 = self.temp_dir / "sub2"
        self.sub_dir_2.mkdir(exist_ok=False)
        self.sub_dir_3 = self.temp_dir / "sub3"
        self.sub_dir_3.mkdir(exist_ok=False)
        self.sub_dir_4 = self.temp_dir / "sub4"
        self.sub_dir_4.mkdir(exist_ok=False)

        # Create some duplicate files
        (self.sub_dir_1 / "dup1_1.txt").write_text("Duplicate content 1")
        (self.sub_dir_1 / "dup1_2.txt").write_text("Duplicate content 1")

        (self.sub_dir_2 / "dup2_1.txt").write_text("Duplicate content 2")
        (self.sub_dir_2 / "dup2_2.txt").write_text("Duplicate content 2")

        (self.sub_dir_3 / "dup2_3.txt").write_text("Duplicate content 2")
        (self.sub_dir_3 / "dup3_1.txt").write_text("Duplicate content 3")
        (self.sub_dir_3 / "dup3_2.txt").write_text("Duplicate content 3")

        (self.sub_dir_4 / "dup2_4.txt").write_text("Duplicate content 2")
        (self.sub_dir_4 / "dup2_5.txt").write_text("Duplicate content 2")

        # Create unique file
        (self.temp_dir / "unique.txt").write_text("I am unique!")

        # Prepare a DupFinder and DupHandler
        self.finder = DupFinder(dirs=[self.temp_dir])
        self.handler = DupHandler(finder=self.finder)

    def tearDown(self):
        """
        Remove the temporary testing directory after each test.
        """
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_remove_dir_duplicates_fail(self):
        """
        Test removing duplicates from sub1. dup1_1 should be kept (not deleted)
        since all duplicates are in delete dirs.
        """
        dup_map = self.finder.duplicates
        self.assertTrue(dup_map, "Expected some duplicates before deletion.")

        # Attempt to remove duplicates in sub1 only
        self.handler.remove_dir_duplicates(
            dirs=[self.sub_dir_1],
            dry_run=False,
        )

        # dup1_1.txt should still exist since all duplicates are in delete directories
        self.assertTrue((self.sub_dir_1 / "dup1_1.txt").exists())

    def test_remove_dir_duplicates_dryrun(self):
        """
        Test dryrun of removing duplicates from sub4. Deletions should occur only for duplicates
        within sub4 since copies exist in other directories.
        """

        dup2_4 = self.sub_dir_4 / "dup2_4.txt"
        dup2_5 = self.sub_dir_4 / "dup2_5.txt"
        self.assertTrue(dup2_4.exists() and dup2_5.exists())

        # Attempt to remove duplicates in sub4 only
        deleted_files, _ = self.handler.remove_dir_duplicates(
            dirs=[self.sub_dir_4], dry_run=True
        )

        # Check that files still exists
        self.assertTrue(dup2_4.exists() and dup2_5.exists())

        # Check that files are returned in deleted_files list and they are whats expected
        self.assertEqual(set(deleted_files), {dup2_4, dup2_5})

    def test_remove_dir_duplicates(self):
        """
        Test removing duplicates from sub3. Deletions should occur only for duplicates
        within sub3 since copies exist in other directories.
        Also tests force parameter and refresh mechanics.
        """

        # Attempt to remove duplicates in sub3 only
        deleted_files, error_tuples = self.handler.remove_dir_duplicates(
            dirs=[self.sub_dir_3],
            dry_run=False,
        )

        # Check that expected files are deleted and the rest untouched
        dup2_1 = self.sub_dir_2 / "dup2_1.txt"  # Should not be deleted
        dup2_2 = self.sub_dir_2 / "dup2_2.txt"  # Should not be deleted
        dup2_3 = self.sub_dir_3 / "dup2_3.txt"  # Should be deleted
        dup3_1 = self.sub_dir_3 / "dup3_1.txt"  # Should not be deleted
        dup3_2 = self.sub_dir_3 / "dup3_2.txt"  # Should be deleted
        self.assertTrue(dup2_1.exists(), "dup2_1.txt should still exist.")
        self.assertTrue(dup2_2.exists(), "dup2_2.txt should still exist.")
        self.assertFalse(dup2_3.exists(), "dup2_3.txt should no longer exist.")
        self.assertTrue(dup3_1.exists(), "dup3_1.txt should still exist.")
        self.assertFalse(dup3_2.exists(), "dup3_2.txt should no longer exist.")
        self.assertEqual(
            {dup2_3, dup3_2},
            set(deleted_files),
            "Only dup2_3.txt and dup3_2.txt should have been deleted.",
        )
        self.assertFalse(error_tuples, "No deletions should have failed.")

        # Check that further calls to remove_dir_duplicates fail when force=False
        self.assertTrue(self.handler._deletions_occurred)
        with self.assertRaises(ValueError):
            self.handler.remove_dir_duplicates(dirs=[self.sub_dir_3], force=False)

        # Test refresh mechanics as well
        self.handler.refresh()
        self.assertFalse(self.handler._deletions_occurred)

    def test_remove_glob_duplicates_simple(self):
        """
        Test removing duplicates with a simple glob pattern (e.g., "common.txt").
        """
        # Create duplicate files with the same name in different directories
        (self.sub_dir_1 / "common.txt").write_text("Duplicate content")
        (self.sub_dir_2 / "common.txt").write_text("Duplicate content")
        (self.sub_dir_3 / "common_other.txt").write_text("Duplicate content")

        # Refresh finder to include new files
        self.finder.refresh()

        # Attempt to remove duplicates matching "common.txt"
        deleted_files, _ = self.handler.remove_glob_duplicates(
            pattern="common.txt", dry_run=False
        )

        # Check that the expected files are deleted
        self.assertFalse((self.sub_dir_1 / "common.txt").exists())
        self.assertFalse((self.sub_dir_2 / "common.txt").exists())
        self.assertTrue((self.sub_dir_3 / "common_other.txt").exists())
        self.assertEqual(
            set(deleted_files),
            {self.sub_dir_1 / "common.txt", self.sub_dir_2 / "common.txt"},
        )

        # Clean up the remaining duplicate
        (self.sub_dir_3 / "common_other.txt").unlink()

    def test_remove_glob_duplicates_all_txt_files(self):
        """
        Test removing all .txt files using a glob pattern (e.g., "*.txt").
        """
        # Create duplicate .txt files in different directories
        (self.sub_dir_1 / "file1.txt").write_text("Duplicate content")
        (self.sub_dir_2 / "file2.txt").write_text("Duplicate content")
        (self.sub_dir_3 / "file3.txt").write_text("Duplicate content")
        (self.sub_dir_4 / "file4_other").write_text("Duplicate content")

        # Refresh finder to include new files
        self.finder.refresh()

        # Attempt to remove all .txt duplicates
        deleted_files, _ = self.handler.remove_glob_duplicates(
            pattern="**/file*.txt", dry_run=False
        )

        # Check that the expected files are deleted
        self.assertFalse((self.sub_dir_1 / "file1.txt").exists())
        self.assertFalse((self.sub_dir_2 / "file2.txt").exists())
        self.assertFalse((self.sub_dir_3 / "file3.txt").exists())
        self.assertTrue((self.sub_dir_4 / "file4_other").exists())
        self.assertEqual(
            set(deleted_files),
            {
                self.sub_dir_1 / "file1.txt",
                self.sub_dir_2 / "file2.txt",
                self.sub_dir_3 / "file3.txt",
            },
        )

        # Clean up the remaining duplicate
        (self.sub_dir_4 / "file4_other").unlink()

    def test_remove_glob_duplicates_specific_dir(self):
        """
        Test removing all .txt files in a specific directory using a glob pattern (e.g., "path/to/dir/*.txt").
        """
        # Create duplicate .txt files in different directories
        (self.sub_dir_1 / "file1.txt").write_text("Duplicate content")
        (self.sub_dir_2 / "file2.txt").write_text("Duplicate content")
        (self.sub_dir_3 / "file3.txt").write_text("Duplicate content")
        (self.sub_dir_4 / "file4_other.txt").write_text("Duplicate content")

        # Refresh finder to include new files
        self.finder.refresh()

        # Attempt to remove all .txt duplicates in sub_dir_2
        deleted_files, _ = self.handler.remove_glob_duplicates(
            pattern=f"{str(self.sub_dir_2)}/file*.txt", dry_run=False
        )

        # Check that the expected files are deleted
        self.assertTrue((self.sub_dir_1 / "file1.txt").exists())
        self.assertFalse((self.sub_dir_2 / "file2.txt").exists())
        self.assertTrue((self.sub_dir_3 / "file3.txt").exists())
        self.assertTrue((self.sub_dir_4 / "file4_other.txt").exists())
        self.assertEqual(
            set(deleted_files),
            {self.sub_dir_2 / "file2.txt"},
        )

        # Clean up the remaining duplicates
        (self.sub_dir_1 / "file1.txt").unlink()
        (self.sub_dir_3 / "file3.txt").unlink()
        (self.sub_dir_4 / "file4_other.txt").unlink()


if __name__ == "__main__":
    unittest.main()
