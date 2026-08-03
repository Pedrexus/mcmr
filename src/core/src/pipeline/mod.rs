use super::deferred::{DeferredFacts, DeferredMode};
use super::delivery::Delivery;
use super::runtime::{GRAPH_DERIVED, REPOSITORY_BUILT, SPOOLED, TypedFamilies, TypedRows};
use crate::extraction::{DocumentExtraction, RepositoryExtraction};
use crate::protocol::{Request, Stats};
use crate::{classes, discovery, exceptions, graph, project};
use std::collections::{BTreeMap, BTreeSet};
use std::time::Instant;

mod documents;
mod graph_facts;
mod lifecycle;
mod scans;

use documents::extract_documents;
use graph_facts::deliver_graph_facts;
use lifecycle::{complete_stats, discover_repository, initial_stats};
use scans::deliver_repository_scans;

fn deliver_extracted_facts<Emit>(
    extraction: RepositoryExtraction<'_>,
    packages: &discovery::Packages,
    deferred: &mut DeferredFacts,
    delivery: &mut Delivery<Emit>,
    typed: &mut TypedRows<'_>,
) -> Result<(), String>
where
    Emit: FnMut(String, Vec<serde_json::Value>) -> Result<(), String>,
{
    let request = extraction.request;
    let built = extraction.built;
    let inventory = extraction.inventory;
    let documents = &inventory.documents;
    for (family, fact) in project::facts(std::path::Path::new(&request.root), built, inventory)? {
        delivery.send(family, vec![fact])?;
    }
    if family_is_requested(request, typed, "ExceptionFact") {
        delivery.send(
            "ExceptionFact".to_string(),
            exceptions::facts(documents, packages),
        )?;
    }
    if family_is_requested(request, typed, "ClassFact")
        || family_is_requested(request, typed, "FunctionFact")
    {
        deliver_class_facts(extraction, packages, deferred, delivery, typed)?;
    }
    if family_is_requested(request, typed, "DirectoryFact") {
        deliver_directory_facts(extraction, packages, deferred, delivery)?;
    }
    Ok(())
}

fn deliver_class_facts<Emit>(
    extraction: RepositoryExtraction<'_>,
    packages: &discovery::Packages,
    deferred: &mut DeferredFacts,
    delivery: &mut Delivery<Emit>,
    typed: &mut TypedRows<'_>,
) -> Result<(), String>
where
    Emit: FnMut(String, Vec<serde_json::Value>) -> Result<(), String>,
{
    let wants_legacy = |name: &str| {
        extraction
            .request
            .families
            .iter()
            .any(|family| family == name)
    };
    let mut facts = BTreeMap::new();
    for family in ["ClassFact", "FunctionFact"]
        .into_iter()
        .filter(|family| wants_legacy(family))
    {
        facts.insert(family.to_string(), deferred.read(family)?);
    }
    let class_rows = typed
        .families
        .classes
        .as_deref_mut()
        .map_or(&mut [] as &mut [_], Vec::as_mut_slice);
    let function_rows = typed
        .families
        .functions
        .as_deref_mut()
        .map_or(&mut [] as &mut [_], Vec::as_mut_slice);
    classes::enrich_all(
        &mut facts,
        class_rows,
        function_rows,
        &extraction.inventory.documents,
        packages,
    );
    if !wants_legacy("ClassFact") {
        facts.remove("ClassFact");
    }
    delivery.send_all(facts)?;
    for (family, count) in [
        (
            "FunctionFact",
            typed.families.functions.as_deref().map(Vec::len),
        ),
        ("ClassFact", typed.families.classes.as_deref().map(Vec::len)),
    ] {
        if !wants_legacy(family)
            && let Some(count) = count
        {
            delivery.mark_typed(family, count)?;
        }
    }
    Ok(())
}

fn deliver_directory_facts<Emit>(
    extraction: RepositoryExtraction<'_>,
    packages: &discovery::Packages,
    deferred: &mut DeferredFacts,
    delivery: &mut Delivery<Emit>,
) -> Result<(), String>
where
    Emit: FnMut(String, Vec<serde_json::Value>) -> Result<(), String>,
{
    let modules = deferred.read("ModuleFact")?;
    let inventory = extraction.inventory;
    let catalogs = discovery::definition_catalogs(&modules);
    let roots = discovery::SourceRoots::of(&inventory.directories, packages);
    if extraction
        .request
        .families
        .iter()
        .any(|family| family == "ModuleFact")
    {
        delivery.send("ModuleFact".to_string(), modules)?;
    }
    delivery.send(
        "DirectoryFact".to_string(),
        discovery::directories(&inventory.directories, &roots, &catalogs),
    )
}

fn family_is_requested(request: &Request, typed: &TypedRows<'_>, family: &str) -> bool {
    request.families.iter().any(|selected| selected == family) || typed.contains(family)
}

fn per_file_families(request: &Request, built: &[String], typed: &TypedRows<'_>) -> Vec<String> {
    let needs_directory_modules = family_is_requested(request, typed, "DirectoryFact")
        && !family_is_requested(request, typed, "ModuleFact");
    built
        .iter()
        .filter(|family| {
            !GRAPH_DERIVED.contains(&family.as_str())
                && !REPOSITORY_BUILT.contains(&family.as_str())
        })
        .cloned()
        .chain(needs_directory_modules.then(|| "ModuleFact".to_string()))
        .chain(
            typed
                .families
                .classes
                .is_some()
                .then(|| "ClassFact".to_string()),
        )
        .chain(
            typed
                .families
                .import_bindings
                .is_some()
                .then(|| "ImportBindingFact".to_string()),
        )
        .chain(
            typed
                .families
                .syntax
                .is_some()
                .then(|| "SyntaxFact".to_string()),
        )
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect()
}

fn spooled_families(request: &Request, typed: &TypedRows<'_>, per_file: &[String]) -> Vec<String> {
    let legacy_class = request.families.iter().any(|family| family == "ClassFact");
    let wants_directory = family_is_requested(request, typed, "DirectoryFact");
    per_file
        .iter()
        .filter(|family| {
            (SPOOLED.contains(&family.as_str())
                && (family.as_str() != "ClassFact" || legacy_class))
                || (family.as_str() == "ModuleFact" && wants_directory)
        })
        .cloned()
        .collect()
}

fn extract_per_file<Emit>(
    extraction: DocumentExtraction<'_>,
    deferred: &mut DeferredFacts,
    delivery: &mut Delivery<Emit>,
    stats: &mut Stats,
    typed: &mut TypedRows<'_>,
) -> Result<(), String>
where
    Emit: FnMut(String, Vec<serde_json::Value>) -> Result<(), String>,
{
    if extraction.families.is_empty() && !typed.has_any() {
        return Ok(());
    }
    extract_documents(
        extraction,
        deferred,
        delivery,
        stats,
        TypedRows {
            families: TypedFamilies {
                functions: typed.families.functions.as_deref_mut(),
                calls: typed.families.calls.as_deref_mut(),
                classes: typed.families.classes.as_deref_mut(),
                import_bindings: typed.families.import_bindings.as_deref_mut(),
                syntax: typed.families.syntax.as_deref_mut(),
                attribute_accesses: typed.families.attribute_accesses.as_deref_mut(),
                string_expressions: typed.families.string_expressions.as_deref_mut(),
            },
            retention: typed.retention,
        },
    )
}

fn mark_empty_typed<Emit>(
    delivery: &mut Delivery<Emit>,
    typed: &TypedRows<'_>,
) -> Result<(), String>
where
    Emit: FnMut(String, Vec<serde_json::Value>) -> Result<(), String>,
{
    for (family, empty) in [
        (
            "ImportBindingFact",
            typed
                .families
                .import_bindings
                .as_deref()
                .is_some_and(Vec::is_empty),
        ),
        (
            "SyntaxFact",
            typed.families.syntax.as_deref().is_some_and(Vec::is_empty),
        ),
        (
            "ClassFact",
            typed.families.classes.as_deref().is_some_and(Vec::is_empty),
        ),
        (
            "AttributeAccessFact",
            typed
                .families
                .attribute_accesses
                .as_deref()
                .is_some_and(Vec::is_empty),
        ),
        (
            "StringExpressionFact",
            typed
                .families
                .string_expressions
                .as_deref()
                .is_some_and(Vec::is_empty),
        ),
    ] {
        if empty {
            delivery.mark_typed(family, 0)?;
        }
    }
    Ok(())
}

fn extract_requested<Emit>(
    extraction: RepositoryExtraction<'_>,
    delivery: &mut Delivery<Emit>,
    stats: &mut Stats,
    typed: &mut TypedRows<'_>,
    deferred_mode: DeferredMode,
) -> Result<DeferredFacts, String>
where
    Emit: FnMut(String, Vec<serde_json::Value>) -> Result<(), String>,
{
    let per_file = per_file_families(extraction.request, extraction.built, typed);
    let packages = discovery::Packages::of(&extraction.inventory.documents);
    let mut deferred = DeferredFacts::new(
        spooled_families(extraction.request, typed, &per_file),
        deferred_mode,
    )?;
    typed.retention.import_bindings = extraction
        .request
        .families
        .iter()
        .any(|family| family == "ImportBindingFact");
    typed.retention.syntax = extraction
        .request
        .families
        .iter()
        .any(|family| family == "SyntaxFact");
    typed.retention.classes = extraction
        .request
        .families
        .iter()
        .any(|family| family == "ClassFact");
    extract_per_file(
        DocumentExtraction {
            documents: &extraction.inventory.documents,
            packages: &packages,
            families: &per_file,
        },
        &mut deferred,
        delivery,
        stats,
        typed,
    )?;
    mark_empty_typed(delivery, typed)?;
    deliver_extracted_facts(extraction, &packages, &mut deferred, delivery, typed)?;
    Ok(deferred)
}

fn deliver_repository_facts<Emit>(
    extraction: RepositoryExtraction<'_>,
    scope: &discovery::Scope,
    deferred: &mut DeferredFacts,
    delivery: &mut Delivery<Emit>,
    calls: Option<&mut Vec<crate::calls::CallRecord>>,
) -> Result<(Option<graph::Graph>, u128), String>
where
    Emit: FnMut(String, Vec<serde_json::Value>) -> Result<(), String>,
{
    let started = Instant::now();
    let documents = &extraction.inventory.documents;
    deliver_repository_scans(
        extraction.request,
        documents,
        std::path::Path::new(&extraction.request.root),
        scope,
        delivery,
    )?;
    let graph = deliver_graph_facts(extraction.request, documents, deferred, delivery, calls)?;
    Ok((graph, started.elapsed().as_nanos()))
}

pub(super) fn analyze<Emit>(
    request: &Request,
    built: &[String],
    delivery: &mut Delivery<Emit>,
    mut typed: TypedRows<'_>,
    deferred_mode: DeferredMode,
) -> Result<(Option<graph::Graph>, Stats), String>
where
    Emit: FnMut(String, Vec<serde_json::Value>) -> Result<(), String>,
{
    // One compiled answer to what this request is about, so the walk, the cross-language scan, the
    // route scan, and the history pass all read the same repository rather than four of them.
    let (scope, inventory, discovery_nanoseconds) = discover_repository(request)?;
    let mut stats = initial_stats(&inventory, discovery_nanoseconds);
    if request.fingerprint_only {
        return Ok((None, stats));
    }
    let extraction_started = Instant::now();
    let extraction = RepositoryExtraction {
        request,
        built,
        inventory: &inventory,
    };
    let mut deferred =
        extract_requested(extraction, delivery, &mut stats, &mut typed, deferred_mode)?;
    stats.timing.extraction_nanoseconds = extraction_started.elapsed().as_nanos();
    let (graph, graph_nanoseconds) = deliver_repository_facts(
        extraction,
        &scope,
        &mut deferred,
        delivery,
        typed.families.calls.as_deref_mut(),
    )?;
    complete_stats(
        &mut stats,
        &graph,
        graph_nanoseconds,
        delivery.fact_count() + typed.fact_count(&request.families),
    );
    Ok((graph.filter(|_| request.graph), stats))
}
