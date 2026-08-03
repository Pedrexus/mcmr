pub use directory::Directory;
pub use document::Document;

mod directory;
mod document;

/// Everything one walk of a repository found, which is its source files and its directories.
#[derive(Default)]
pub struct Inventory {
    pub documents: Vec<Document>,
    pub guides: Vec<Document>,
    pub directories: Vec<Directory>,
    pub fingerprint: String,
}
