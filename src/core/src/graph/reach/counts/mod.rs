use serde::Serialize;

mod references;
mod uses;

pub use references::ReferenceCounts;
pub use uses::UseCounts;

#[derive(Debug, Serialize)]
pub struct DeclarationCounts {
    #[serde(flatten)]
    pub references: ReferenceCounts,
    #[serde(flatten)]
    pub uses: UseCounts,
}
