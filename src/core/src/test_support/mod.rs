use std::io::ErrorKind;
use std::path::Path;

/// Remove a test directory while accepting that a fresh fixture has nothing to remove.
pub(crate) fn remove_directory(path: &Path) {
    match std::fs::remove_dir_all(path) {
        Ok(()) => {}
        Err(failure) if failure.kind() == ErrorKind::NotFound => {}
        Err(failure) => panic!(
            "could not remove test directory {}: {failure}",
            path.display()
        ),
    }
}
