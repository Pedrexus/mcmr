use ignore::{IncrementalIgnore, WalkBuilder};
use std::path::{Path, PathBuf};
use std::sync::Mutex;

/// Which files one request is about, which every pass asks rather than only the walk.
///
/// The walk is not the only thing that reads a repository. The cross-language scan, the route
/// scan, and the history pass each open their own view of the tree, and a caller who narrowed the
/// request meant all of them. Compiling the answer once and handing it to each keeps Git ignores
/// and requested suffixes identical for source, history, routes, and cross-language evidence.
pub struct Scope {
    ignored: Mutex<IncrementalIgnore>,
    prefix: PathBuf,
    suffixes: Vec<String>,
}

impl Scope {
    /// Read the repository's Git ignore contract beside the requested source suffixes.
    pub fn of(root: &Path, suffixes: &[String]) -> Self {
        let scan_root = std::fs::canonicalize(root).unwrap_or_else(|_| root.to_path_buf());
        let contract_root = scan_root
            .ancestors()
            .find(|ancestor| ancestor.join(".gitignore").is_file())
            .unwrap_or(scan_root.as_path());
        let prefix = scan_root
            .strip_prefix(contract_root)
            .unwrap_or(Path::new(""))
            .to_path_buf();
        let mut walk = WalkBuilder::new(contract_root);
        walk.standard_filters(false)
            .parents(false)
            .git_ignore(true)
            .require_git(false);
        let ignored = walk
            .build_matchers()
            .pop()
            .expect("one discovery root always yields one matcher");
        Self {
            ignored: Mutex::new(ignored),
            prefix,
            suffixes: suffixes.to_vec(),
        }
    }

    /// Whether the exclusion set removes one path.
    pub fn excludes(&self, relative: &str) -> bool {
        if relative.split('/').any(|component| component == ".git") {
            return true;
        }
        let mut matcher = self
            .ignored
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        matcher
            .matched(self.contract_path(relative), false)
            .is_ignore()
    }

    /// Whether the exclusion set removes one directory, which is what lets a walk skip its subtree.
    ///
    /// A pattern that excludes a directory is written for the paths inside it, the way
    /// `**/target/**` is, so the directory is matched as the prefix its own contents carry rather
    /// than as a bare name that no such pattern would ever hit.
    pub fn excludes_directory(&self, relative: &str) -> bool {
        if relative.is_empty() {
            return false;
        }
        if relative.split('/').any(|component| component == ".git") {
            return true;
        }
        let mut matcher = self
            .ignored
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        matcher
            .matched(self.contract_path(relative), true)
            .is_ignore()
    }

    /// Whether one repository-relative path is source this request asked to read.
    pub fn holds(&self, relative: &str) -> bool {
        !self.excludes(relative)
            && self
                .suffixes
                .iter()
                .any(|suffix| relative.ends_with(suffix.as_str()))
    }

    fn contract_path(&self, relative: &str) -> PathBuf {
        self.prefix.join(relative)
    }
}

#[cfg(test)]
mod tests {
    use super::Scope;

    #[test]
    fn a_nested_scan_inherits_the_repository_ignore_contract() {
        let root = tempfile::tempdir().expect("a temporary repository must open");
        let repository = root.path().join("repository");
        std::fs::create_dir(&repository).expect("the repository must be writable");
        std::fs::write(repository.join(".gitignore"), "__pycache__/\n")
            .expect("the ignore contract must be writable");
        let nested = repository.join("src/package");
        std::fs::create_dir_all(&nested).expect("the nested scan root must be writable");

        assert!(Scope::of(&nested, &[".py".to_string()]).excludes_directory("__pycache__"));
    }
}
