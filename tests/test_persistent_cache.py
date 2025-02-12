import pathlib
import unittest
from time import sleep
from py_dedup.persistent_cache import *
from tests.global_test_vars import TEST_DIR, CMPR_DIR, COPY_CMPR_DIR


class TestPersistentCache(unittest.TestCase):
    def test_get_temp_dir_path(self):
        temp_dir_path = get_temp_dir_path()
        self.assertTrue(temp_dir_path.parent.is_dir())
        self.assertTrue(not temp_dir_path.exists() or temp_dir_path.is_dir())
        self.assertTrue(isinstance(temp_dir_path, pathlib.Path))

    def test_get_tempfile_prefix(self):
        cwd = pathlib.Path.cwd()
        absolute_paths = [TEST_DIR, CMPR_DIR, COPY_CMPR_DIR]
        relative_paths = [path.relative_to(cwd) for path in absolute_paths]
        parent_paths = [path.parent for path in relative_paths]
        reverse_paths = relative_paths[::-1]

        prefix_absolute = get_tempfile_prefix(absolute_paths)
        prefix_relative = get_tempfile_prefix(relative_paths)
        prefix_parents = get_tempfile_prefix(parent_paths)
        prefix_reversed = get_tempfile_prefix(reverse_paths)

        # Same prefix is expected no matter if paths are relative or absolute
        self.assertEqual(prefix_absolute, prefix_relative)

        # Same prefix is expected no matter the order
        self.assertEqual(prefix_absolute, prefix_reversed)

        # Different actual dirs should result in different prefixes
        self.assertNotEqual(prefix_relative, prefix_parents)

    def test_create_tempfile_and_cleanup_user_tempfiles(self):
        # Setup
        dir_path = get_temp_dir_path()
        num_tmp = len([path for path in dir_path.iterdir() if path.is_file()])
        dirs1 = [CMPR_DIR, TEST_DIR, COPY_CMPR_DIR]
        dirs2 = [CMPR_DIR, COPY_CMPR_DIR]
        path1 = create_tempfile(dirs1)
        path2 = create_tempfile(dirs2)
        # Both files should exist
        self.assertTrue(path1.is_file())
        self.assertTrue(path2.is_file())
        # Only 2 files should be created
        diff = len([path for path in dir_path.iterdir() if path.is_file()]) - num_tmp
        self.assertEqual(diff, 2)
        # Test cleanup of files
        prefix_dirs1 = get_tempfile_prefix(dirs1)
        pattern1 = f"{prefix_dirs1}*{TMP_FILE_SUFFIX}"
        prefix_dirs2 = get_tempfile_prefix(dirs2)
        pattern2 = f"{prefix_dirs2}*{TMP_FILE_SUFFIX}"
        # Test that dryrun do not remove any files
        cleanup_user_tempfiles(dry_run=True, pattern=pattern1)
        diff = len([path for path in dir_path.iterdir() if path.is_file()]) - num_tmp
        self.assertTrue(path1.is_file())
        self.assertEqual(diff, 2)
        # Test actual cleanup of 1 file
        cleanup_user_tempfiles(dry_run=False, pattern=pattern1)
        diff = len([path for path in dir_path.iterdir() if path.is_file()]) - num_tmp
        self.assertTrue(not path1.is_file())
        self.assertEqual(diff, 1)
        # Remaining cleanup
        cleanup_user_tempfiles(dry_run=False, pattern=pattern2)
        diff = len([path for path in dir_path.iterdir() if path.is_file()]) - num_tmp
        self.assertTrue(not path2.is_file())
        self.assertEqual(diff, 0)

    def test_get_current_tempfile(self):
        dirs = [CMPR_DIR, TEST_DIR]
        # Create 2 tempfiles with dirs specific prefix
        path1 = create_tempfile(dirs)
        sleep(0.04)  # Needed so there is an assured difference in st_mtime
        path2 = create_tempfile(dirs)
        # Check that the latest file_path is returned
        returned_path = get_current_tempfile(dirs)
        self.assertEqual(path2, returned_path)
        # Cleanup
        prefix = get_tempfile_prefix(dirs)
        pattern = f"{prefix}*{TMP_FILE_SUFFIX}"
        cleanup_user_tempfiles(pattern=pattern)
        # Should return None now that all dirs specific tempfile was removed
        tmp_file = get_current_tempfile(dirs)
        self.assertIsNone(tmp_file)

    # TODO write tests for pickling/unpickling


if __name__ == "__main__":
    unittest.main()
