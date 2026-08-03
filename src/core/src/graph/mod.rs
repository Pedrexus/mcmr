mod build;
mod construction;
mod contracts;
mod naming;
mod python;
mod reach;
mod resolution_engine;

#[cfg(test)]
mod tests;

pub use build::build;
pub use construction::{identity, node, parameter};
pub use contracts::{
    DatatypeKind, Edge, EdgeKind, Export, ExportBypass, Graph, Language, Node, NodeKind,
    ParameterKind, Reference, ReferenceLocation, ReferenceResolution, Relation, Resolution,
    Stated, Visibility,
};
pub use python::{ImportingModule, absolute_module};
pub use reach::{Declaration, DeclarationCounts, Reach, reach};
pub use resolution_engine::{expand, stray};

pub(crate) use resolution_engine::{Attachment, ResolutionContext, attach, is_builtin};
