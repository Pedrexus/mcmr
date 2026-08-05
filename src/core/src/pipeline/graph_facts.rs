use super::super::deferred::DeferredFacts;
use super::super::delivery::Delivery;
use super::super::runtime::GRAPH_DERIVED;
use crate::protocol::Request;
use crate::{calls, coupling, discovery, graph, modules, overrides};
use std::collections::BTreeMap;

/// Build the repository graph once and release every family derived from it.
pub(super) fn deliver_graph_facts<Emit>(
    request: &Request,
    documents: &[discovery::Document],
    deferred: &mut DeferredFacts,
    delivery: &mut Delivery<Emit>,
    calls: Option<&mut Vec<calls::CallRecord>>,
) -> Result<Option<graph::Graph>, String>
where
    Emit: FnMut(String, Vec<serde_json::Value>) -> Result<(), String>,
{
    let wants = |name: &str| request.families.iter().any(|family| family == name);
    let typed_calls = calls.is_some();
    let wants_calls = wants("CallFact") || wants("TestFunctionFact") || typed_calls;
    let wants_graph = GRAPH_DERIVED.iter().any(|family| wants(family)) || wants_calls;
    let graph = if request.graph || wants_graph {
        Some(graph::build(&request.root, documents)?)
    } else {
        None
    };
    let Some(built) = &graph else {
        return Ok(graph);
    };
    deliver_architecture(wants, built, delivery)?;
    if wants_calls {
        deliver_calls(request, built, deferred, delivery, calls)?;
    }
    Ok(graph)
}

fn deliver_architecture<Emit>(
    wants: impl Fn(&str) -> bool,
    built: &graph::Graph,
    delivery: &mut Delivery<Emit>,
) -> Result<(), String>
where
    Emit: FnMut(String, Vec<serde_json::Value>) -> Result<(), String>,
{
    for family in [
        "OverrideFact",
        "ModuleCouplingFact",
        "DependencyComponentFact",
        "SymbolReachFact",
        "ExportFact",
    ] {
        if !wants(family) {
            continue;
        }
        let facts = match family {
            "OverrideFact" => overrides::pairs(built),
            "ModuleCouplingFact" => coupling::modules(built),
            "DependencyComponentFact" => vec![modules::dependencies(built)],
            "SymbolReachFact" => reach_facts(built),
            "ExportFact" => export_facts(built),
            _ => unreachable!("the architecture family list is closed"),
        };
        delivery.send(family.to_string(), facts)?;
    }
    Ok(())
}

fn deliver_calls<Emit>(
    request: &Request,
    built: &graph::Graph,
    deferred: &mut DeferredFacts,
    delivery: &mut Delivery<Emit>,
    mut calls: Option<&mut Vec<calls::CallRecord>>,
) -> Result<(), String>
where
    Emit: FnMut(String, Vec<serde_json::Value>) -> Result<(), String>,
{
    let standard_library = request
        .python_standard_library
        .iter()
        .map(String::as_str)
        .collect();
    let resolved = calls::resolutions(built, &standard_library);
    let test_reachability = calls::TestReachability::new(built);
    if let Some(output) = calls.as_deref_mut() {
        let mut index = calls::ResolutionIndex::new(&resolved);
        crate::calls::enrich_records(output, &mut index);
    }
    deliver_deferred_calls(request, deferred, delivery, &resolved, &test_reachability)?;
    if !request.families.iter().any(|family| family == "CallFact")
        && let Some(output) = calls.as_deref()
    {
        delivery.mark_typed("CallFact", output.len())?;
    }
    Ok(())
}

fn deliver_deferred_calls<Emit>(
    request: &Request,
    deferred: &mut DeferredFacts,
    delivery: &mut Delivery<Emit>,
    resolved: &BTreeMap<(String, usize), Vec<calls::ResolvedCall>>,
    test_reachability: &calls::TestReachability,
) -> Result<(), String>
where
    Emit: FnMut(String, Vec<serde_json::Value>) -> Result<(), String>,
{
    for family in ["CallFact", "TestFunctionFact"]
        .into_iter()
        .filter(|family| request.families.iter().any(|wanted| wanted == family))
    {
        let mut index = calls::ResolutionIndex::new(resolved);
        deferred.drain(family, |mut facts| {
            crate::calls::enrich_facts(family, &mut facts, &mut index);
            if family == "TestFunctionFact" {
                crate::calls::enrich_test_reach(&mut facts, test_reachability);
            }
            delivery.send(family.to_string(), facts)
        })?;
    }
    Ok(())
}

fn export_facts(built: &graph::Graph) -> Vec<serde_json::Value> {
    built
        .exports
        .iter()
        .map(|export| {
            serde_json::json!({
                "key": format!("export:{}.{}", export.module, export.name),
                "span": {"path": export.path},
                "language": "python",
                "public_export": {
                    "name": export.name,
                    "target": export.target,
                    "consumer_count": export.consumer_count,
                    "nodes": export.nodes,
                    "span": {"path": export.path, "start_line": 1},
                },
                "bypasses": export.bypasses.iter().map(|bypass| {
                    serde_json::json!({
                        "public_module": export.module,
                        "name": export.name,
                        "target": export.target,
                        "expression": bypass.expression,
                        "module_node": bypass.module_node,
                        "replacement_module": bypass.replacement_module,
                        "binding_count": bypass.binding_count,
                        "is_cycle_safe": bypass.is_cycle_safe,
                        "span": {
                            "path": bypass.path,
                            "start_line": bypass.line,
                            "end_line": bypass.line,
                        },
                    })
                }).collect::<Vec<_>>(),
            })
        })
        .collect()
}

fn reach_facts(built: &graph::Graph) -> Vec<serde_json::Value> {
    graph::reach(built)
        .into_iter()
        .map(|reach| {
            serde_json::json!({
                "key": format!("reach:{}", reach.module),
                "span": {"path": reach.path},
                "language": reach.language,
                "is_test_module": reach.is_test_module,
                "declarations": reach.declarations,
            })
        })
        .collect()
}
