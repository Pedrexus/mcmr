use path_slash::PathExt as _;
use std::path::Path;

/// One discovered path whose repository-relative spelling is required.
pub(crate) struct RepositoryPath<'path>(&'path Path);

impl<'path> RepositoryPath<'path> {
    pub(crate) fn new(path: &'path Path) -> Self {
        Self(path)
    }

    pub(crate) fn relative_to(self, root: &Path, context: &str) -> Result<String, String> {
        let relative = self.0.strip_prefix(root).map_err(|failure| {
            format!(
                "{context} path {} is outside its root {}: {failure}",
                self.0.display(),
                root.display()
            )
        })?;
        relative
            .to_slash()
            .map(|text| text.into_owned())
            .ok_or_else(|| format!("{context} path {} is not valid UTF-8", relative.display()))
    }
}
