//! Discovery, parsing, fact extraction, and the repository graph for My Code, My Rules.
//!
//! The binary is a thin shell over this library. Exposing the modules rather than hiding them in
//! one executable is what lets a benchmark measure a single family in isolation, which is the only
//! way to know which one is worth optimizing.

#[cfg(feature = "python")]
pub mod bindings;
pub mod calls;
pub mod classes;
pub mod clones;
pub mod comments;
pub mod coupling;
pub mod discovery;
pub mod exceptions;
mod extraction;
pub mod families;
pub mod functions;
pub mod graph;
pub mod history;
pub mod imports;
pub mod interop;
pub mod lexical;
pub mod modules;
pub mod native;
pub mod organization;
pub mod overrides;
pub mod project;
pub mod protocol;
pub mod python;
pub mod routes;
pub mod rust;
pub mod source;
pub mod syntax;
pub mod typescript;
pub mod walk;

mod deferred;
mod delivery;
mod pipeline;
mod runtime;
mod session;
#[cfg(test)]
mod test_support;

pub use session::{
    SessionFamilies, SessionOutput, run, run_session, run_session_with_generic, run_stream,
};

#[cfg(test)]
use deferred::{FORBID_FACT_SPOOLS, FactSpools};
#[cfg(test)]
use runtime::FACT_BATCH_SIZE;

#[cfg(test)]
mod tests;
