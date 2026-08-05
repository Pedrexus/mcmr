use serde::Serialize;

mod ownership;

pub use ownership::ReferenceOwnership;

#[derive(Debug, Serialize)]
pub struct ReferenceCounts {
    pub own_file_references: usize,
    pub other_file_references: usize,
    #[serde(flatten)]
    pub ownership: ReferenceOwnership,
    pub referencing_files: usize,
    pub referencing_directories: usize,
    pub referencing_packages: usize,
}
