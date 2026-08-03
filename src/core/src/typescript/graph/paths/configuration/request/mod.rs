use crate::typescript::graph::paths::names::JoinedPath;
use crate::typescript::graph::paths::support::parent_of;

pub struct WrittenSpecifier<'path> {
    pub from: &'path str,
    pub value: &'path str,
}

impl WrittenSpecifier<'_> {
    pub(super) fn governed_by(&self, directory: &str) -> bool {
        directory.is_empty() || self.from.starts_with(&format!("{directory}/"))
    }

    pub(super) fn relative_path(&self) -> String {
        JoinedPath {
            parent: parent_of(self.from),
            child: self.value,
        }
        .normalized()
    }
}
