use crate::discovery::{Document, Packages};
use crate::functions::FunctionRecord;
use rayon::prelude::*;
use serde_json::Value;
use std::collections::BTreeMap;

#[cfg(test)]
use serde_json::json;

mod model;
mod records;
mod repository;

pub use records::{
    AttributeProjectionRecord, ClassAnalysisRecord, ClassRecord, ClassRelations,
    CoupledTypeGroupRecord, MethodBehavior, MethodIdentity, MethodRecord, ModelFileRecord,
};

use model::Stated;
use repository::Repository;

/// Join repository class evidence onto compatibility facts.
#[cfg(test)]
fn enrich(facts: &mut BTreeMap<String, Vec<Value>>, documents: &[Document], packages: &Packages) {
    enrich_all(facts, &mut [], &mut [], documents, packages);
}

/// Join repository evidence onto compatibility values and typed rows in one indexed pass.
pub(crate) fn enrich_all(
    facts: &mut BTreeMap<String, Vec<Value>>,
    classes: &mut [ClassRecord],
    functions: &mut [FunctionRecord],
    documents: &[Document],
    packages: &Packages,
) {
    let stated: Vec<Stated> = documents
        .par_iter()
        .filter(|document| document.relative.ends_with(".py"))
        .filter_map(|document| Stated::of(document, packages))
        .collect();
    let repository = Repository::of(&stated);
    if let Some(stream) = facts.get_mut("ClassFact") {
        for fact in stream.iter_mut() {
            repository.state(fact);
        }
    }
    if let Some(stream) = facts.get_mut("FunctionFact") {
        for fact in stream.iter_mut() {
            repository.state_callable(fact);
        }
    }
    for class in classes {
        repository.state_class(class);
    }
    for function in functions {
        repository.state_function(function);
    }
}

#[cfg(test)]
mod tests;
