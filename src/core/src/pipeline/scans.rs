use crate::delivery::Delivery;
use crate::protocol::Request;
use crate::{clones, discovery, history, interop, organization, routes};

/// Build and immediately release each family scanned across the complete repository.
pub(super) fn deliver_repository_scans<Emit>(
    request: &Request,
    documents: &[discovery::Document],
    root: &std::path::Path,
    scope: &discovery::Scope,
    delivery: &mut Delivery<Emit>,
) -> Result<(), String>
where
    Emit: FnMut(String, Vec<serde_json::Value>) -> Result<(), String>,
{
    deliver_interop(request, root, scope, delivery)?;
    deliver_clones(request, documents, delivery)?;
    deliver_history(request, root, scope, delivery)?;
    deliver_routes(request, root, scope, delivery)?;
    deliver_organization(request, documents, delivery)
}

fn deliver_interop<Emit>(
    request: &Request,
    root: &std::path::Path,
    scope: &discovery::Scope,
    delivery: &mut Delivery<Emit>,
) -> Result<(), String>
where
    Emit: FnMut(String, Vec<serde_json::Value>) -> Result<(), String>,
{
    if request.wants("InteropFact") {
        delivery.send(
            "InteropFact".to_string(),
            interop::facts(&interop::scan(root, scope)?),
        )?;
    }
    Ok(())
}

fn deliver_clones<Emit>(
    request: &Request,
    documents: &[discovery::Document],
    delivery: &mut Delivery<Emit>,
) -> Result<(), String>
where
    Emit: FnMut(String, Vec<serde_json::Value>) -> Result<(), String>,
{
    if request.wants("CloneGroupFact") {
        delivery.send("CloneGroupFact".to_string(), clones::scan(documents))?;
    }
    Ok(())
}

fn deliver_history<Emit>(
    request: &Request,
    root: &std::path::Path,
    scope: &discovery::Scope,
    delivery: &mut Delivery<Emit>,
) -> Result<(), String>
where
    Emit: FnMut(String, Vec<serde_json::Value>) -> Result<(), String>,
{
    if request.wants("RepositoryHistoryFact") {
        delivery.send(
            "RepositoryHistoryFact".to_string(),
            history::read(root, scope)?,
        )?;
    }
    Ok(())
}

fn deliver_routes<Emit>(
    request: &Request,
    root: &std::path::Path,
    scope: &discovery::Scope,
    delivery: &mut Delivery<Emit>,
) -> Result<(), String>
where
    Emit: FnMut(String, Vec<serde_json::Value>) -> Result<(), String>,
{
    if request.wants("RouteFact") {
        delivery.send(
            "RouteFact".to_string(),
            routes::facts(&routes::scan(root, scope)?),
        )?;
    }
    Ok(())
}

fn deliver_organization<Emit>(
    request: &Request,
    documents: &[discovery::Document],
    delivery: &mut Delivery<Emit>,
) -> Result<(), String>
where
    Emit: FnMut(String, Vec<serde_json::Value>) -> Result<(), String>,
{
    if request.wants("Enum") || request.wants("SymbolFact") {
        let packages = discovery::Packages::of(documents);
        let organization = organization::Organization::of(documents, &packages);
        if request.wants("Enum") {
            delivery.send("Enum".to_string(), vec![organization.enum_fact()])?;
        }
        if request.wants("SymbolFact") {
            delivery.send("SymbolFact".to_string(), vec![organization.typing_fact()])?;
        }
    }
    Ok(())
}
