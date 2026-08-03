mod retention;
mod rows;

pub(crate) use retention::LegacyRetention;
pub(crate) use rows::{TypedFamilies, TypedRows};

/// The families the repository graph answers, which no frontend is ever asked for.
///
/// Each of these is a statement about several files at once. A file cannot see what imports it,
/// which module overrides its methods, or how far a declaration reaches, so a per-file builder
/// answering any of them can only state what one file happens to hold and a rule reading that
/// answers the same thing forever.
pub(super) const GRAPH_DERIVED: &[&str] = &[
    "DependencyComponentFact",
    "ExportFact",
    "ModuleCouplingFact",
    "OverrideFact",
    "SymbolReachFact",
];

/// Per-file families spooled until repository-wide evidence can be joined onto them.
pub(super) const SPOOLED: &[&str] = &["CallFact", "ClassFact", "FunctionFact", "TestFunctionFact"];

/// Families built directly from repository-wide evidence rather than by a frontend.
pub(super) const REPOSITORY_BUILT: &[&str] = &[
    "CloneGroupFact",
    "DirectoryFact",
    "ExceptionFact",
    "InteropFact",
    "RepositoryHistoryFact",
    "RouteFact",
];

pub(super) const FACT_BATCH_SIZE: usize = 128;
