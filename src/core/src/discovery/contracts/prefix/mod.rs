pub(crate) trait PathPrefix {
    /// Whether one directory sits at or below this path, compared by whole components.
    fn prefixes(&self, directory: &str) -> bool;
}

impl PathPrefix for str {
    fn prefixes(&self, directory: &str) -> bool {
        self.is_empty() || directory == self || directory.starts_with(&format!("{self}/"))
    }
}
