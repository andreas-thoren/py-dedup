# py-dedup

A Python utility to **find and handle duplicate files** across one or more directories. It identifies duplicates by comparing file sizes and then verifying file content via MD5 hashing.

---

## Features

- **Find duplicate files** by size and hash checking.
- **List empty files** (0 bytes).
- **Optionally delete** duplicates in specified directories.
- **Persistent caching** to store duplicate results and avoid unnecessary rescans.
- **Command-line interface (CLI)** for easy use.
- **Dry-run mode** for safe testing before deletion.
- **Customizable chunk size** and sorting.

---

## Requirements
- Python version >= 3.11
- No external dependencies required

---

## Installation

You can install `py-dedup` using `pip` directly from the Git repository or by cloning the repository and installing it manually.

### 1. Install via `pip` from GitHub (SSH)

This is the quickest way to install `py-dedup` without cloning the repository.

```bash
pip install git+ssh://git@github.com/andreas-thoren/py-dedup.git
```

### 2. Clone the Repository and Install Manually

If you prefer to have a local copy of the repository, follow these steps:

1. **Clone** this repository or download it as a ZIP.

    ```bash
    git clone https://github.com/andreas-thoren/py-dedup.git
    ```

2. **Navigate** to the project directory.

    ```bash
    cd py-dedup
    ```

3. **(Optional)** Create and activate a virtual environment:

    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

4. **Install** the package using `pip`:

    ```bash
    pip install .
    ```

---

## Usage

### CLI Usage

`py-dedup` provides a command-line interface (CLI) for easy use. Below are examples of common operations:

#### Find duplicate files

```bash
py-dedup find-duplicates /path/to/directory1 /path/to/directory2
```

This scans the specified directories for duplicate files and displays the results. Results are cached for faster retrieval later.

#### Show cached duplicate results

```bash
py-dedup show-duplicates /path/to/directory1 /path/to/directory2 --threshold 60
```

This retrieves previously scanned duplicate results if they are less than 60 minutes old.

#### Delete duplicate files (dry run)

```bash
py-dedup delete-duplicates /path/to/directory1 /path/to/directory2 --delete-dirs /path/to/directory2 -n
```

This command simulates deletion of duplicate files:
- If at least one duplicate exists outside `/path/to/directory2`, then all duplicates found within `/path/to/directory2` are flagged for deletion.
- If all duplicates are located within `/path/to/directory2`, then all except one copy are flagged for deletion (to ensure one copy remains). No files are actually deleted due to the -n (dry-run) option.

#### Delete duplicate files (actual deletion)

```bash
py-dedup delete-duplicates /path/to/directory1 /path/to/directory2 --delete-dirs /path/to/directory2
```

Do the actual deletions of duplicates in `/path/to/directory2`

#### Delete Empty Files

```bash
py-dedup delete-empty /path/to/directory1 /path/to/directory2
```

To scan for and remove empty files (0 bytes) from specified directories, use:

#### Clear cached results

```bash
py-dedup clear-cache
```

This removes cached scan results, forcing a fresh scan on the next run.

---

### Programmatic Usage (Python API)

Below is an example of how to use `py-dedup` in Python:

```python
import pathlib
from py_dedup import DupFinder, DupHandler

# 1. Create a DupFinder instance, specifying one or more directories.
finder = DupFinder(dirs=["/path/to/dir1", "/path/to/dir2"], chunk_size=8192)

# 2. Sort and get duplicates:
finder.sort_duplicates_alphabetically()
duplicates = finder.get_size_sorted_duplicates()

# 3. Print duplicates and empty files:
finder.print_duplicates()
print("Empty files detected:", finder.empty_files)

# 4. Create a DupHandler to manage deletions.
handler = DupHandler(finder)

# 5. Perform a dry-run deletion.
deleted_files_dry_run, failed_deletions_dry_run = handler.remove_dir_duplicates(
    dirs=["/path/to/dir1"], dry_run=True
)
print("Dry-run deleted files:", deleted_files_dry_run)

# 6. Perform actual deletion.
deleted_files, failed_deletions = handler.remove_dir_duplicates(
    dirs=["/path/to/dir1"], dry_run=False
)
print("Actually deleted files:", deleted_files)
```

---

## How It Works

1. **Size Grouping**: Files are first grouped by their size.
2. **Empty Files**: Any files of size 0 are immediately marked as empty files.
3. **MD5 Hash Check**: For each size group with more than one file, MD5 hashes are calculated to confirm exact duplicates.
4. **Duplicates Listing**: Duplicates are stored in a dictionary, keyed by file size, with each value containing lists of files sharing the same hash.
5. **Deletion**: If desired, you can use `DupHandler` to remove duplicates in a specified directory (or set of directories). A dry-run mode is available for safety.

---

## Project Structure

```
py-dedup/
│
├─ py_dedup/
│   ├─ __init__.py
│   ├─ core.py              # Contains DirectoryValidator, DupFinder, DupHandler
│   ├─ cli.py               # CLI interface
│   ├─ persistent_cache.py  # Caching for duplicate scan results
│
├─ tests/
│   ├─ __init__.py
│   ├─ global_test_vars.py
│   ├─ test_cli.py
│   ├─ test_config.toml
│   ├─ test_core.py
│   ├─ test_persistent_cache.py
│   ├─ utils_tests.py
│
├─ pyproject.toml
├─ LICENSE
├─ README.md
├─ manual_tests.py          # Used for manual testing. Not necessary for end user.
```

---

## TODO

- [ ] Add progress status bar to hashing part
- [ ] Implement logging
- [ ] Change datastructure of DupFinder to contain two dictionaries. One { "hash_value": dup_instance(file_size, set(file_paths)) }. The other { file_path: "hash_value" }. This so you can modify DupFinder instances easier.
- [ ] Add gui.py

---

**License**: MIT
