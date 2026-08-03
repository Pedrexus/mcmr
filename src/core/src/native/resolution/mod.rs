use crate::graph::{Attachment, Edge, EdgeKind, Node, NodeKind, Reference, attach, stray};
use std::collections::{BTreeMap, BTreeSet};

/// Where the repository states each declared name, indexed by the last segment of it.
///
/// A qualified name is resolved here by namespace lookup rather than by where the file sits, and
/// asking that question of every declared name once per reference is what makes a large generated
/// translation unit unbearable. The last segment narrows the search to a handful before the
/// qualified tail decides.
#[derive(Debug, Default)]
pub struct Lookup {
    by_tail: BTreeMap<String, Vec<String>>,
}

impl Lookup {
    pub fn of(reachable: &BTreeSet<String>) -> Self {
        let mut by_tail: BTreeMap<String, Vec<String>> = BTreeMap::new();
        for known in reachable {
            let tail = known.rsplit("::").next().unwrap_or(known);
            by_tail
                .entry(tail.to_string())
                .or_default()
                .push(known.clone());
        }
        Self { by_tail }
    }

    /// Return the one declaration this written name can mean, when the repository states only one.
    ///
    /// Two matches mean the lookup needs more than this kernel knows, so the reference stays
    /// unresolved rather than being attached to whichever one came first.
    fn only(&self, written: &str) -> Option<&String> {
        let tail = written.rsplit("::").next().unwrap_or(written);
        let suffix = format!("::{written}");
        let mut matching = self
            .by_tail
            .get(tail)?
            .iter()
            .filter(|known| known.ends_with(&suffix));
        match (matching.next(), matching.next()) {
            (Some(only), None) => Some(only),
            _ => None,
        }
    }
}

/// Resolve one native reference against the repository, leaving what cannot be proved visible.
///
/// This language family resolves by name rather than by path, so the question is which enclosing
/// scope declares the name. A header and the unit that implements it land in the same module,
/// which is what makes a declaration in one and a definition in the other the same node.
pub fn resolve(
    reference: &Reference,
    reachable: &BTreeSet<String>,
    lookup: &Lookup,
    nodes: &mut BTreeMap<String, Node>,
    edges: &mut Vec<Edge>,
) {
    let written = reference.expression.trim_start_matches("::");
    let mut candidates = Vec::new();
    let mut scope: Vec<&str> = reference.module.split("::").collect();
    while !scope.is_empty() {
        candidates.push(format!("{}::{written}", scope.join("::")));
        scope.pop();
    }
    candidates.push(written.to_string());
    candidates.extend(lookup.only(written).cloned());
    if attach(
        Attachment {
            reference,
            candidates: &candidates,
            symbols: reachable,
            relation_kind: reference.kind,
        },
        nodes,
        edges,
    ) {
        return;
    }
    // An include this repository does not hold is a header the toolchain supplies, which is a
    // dependency rather than a gap.
    if reference.kind == EdgeKind::Import {
        stray(reference, NodeKind::ExternalModule, written, nodes, edges);
        return;
    }
    // An unknown namespace comes from a linked library and remains a named dependency. An
    // unresolved bare name is instead a gap in what this kernel can see.
    if is_provided(written) || written.contains("::") {
        stray(reference, NodeKind::ExternalSymbol, written, nodes, edges);
    } else {
        stray(
            reference,
            NodeKind::UnresolvedSymbol,
            &format!("{}::{written}", reference.module),
            nodes,
            edges,
        );
    }
}

/// Whether one name is something the language, its runtime, or its standard library provides.
///
/// A double underscore is how this family spells a compiler intrinsic, a cast is a keyword that
/// looks like a call, and a name under a standard namespace comes from a header nobody asked this
/// kernel to read. All three are outside the repository rather than missing from it.
fn is_provided(name: &str) -> bool {
    const NAMES: &[&str] = &[
        "static_cast",
        "reinterpret_cast",
        "const_cast",
        "dynamic_cast",
        "sizeof",
        "alignof",
        "decltype",
        "auto",
        "bool",
        "char",
        "double",
        "float",
        "int",
        "long",
        "short",
        "signed",
        "unsigned",
        "void",
        "size_t",
        "ssize_t",
        "ptrdiff_t",
        "uint8_t",
        "uint16_t",
        "uint32_t",
        "uint64_t",
        "int8_t",
        "int16_t",
        "int32_t",
        "int64_t",
        "nullptr_t",
        "wchar_t",
        "dim3",
        "half",
        "half2",
        "char2",
        "char3",
        "char4",
        "uchar2",
        "uchar3",
        "uchar4",
        "short2",
        "short3",
        "short4",
        "ushort2",
        "ushort3",
        "ushort4",
        "int2",
        "int3",
        "int4",
        "uint2",
        "uint3",
        "uint4",
        "long2",
        "long3",
        "long4",
        "ulong2",
        "ulong3",
        "ulong4",
        "float2",
        "float3",
        "float4",
        "double2",
        "double3",
        "double4",
    ];
    NAMES.contains(&name)
        || name.starts_with("__")
        || name.starts_with("std::")
        || name.starts_with("cuda::")
        || name.starts_with("cooperative_groups::")
        || name.starts_with("thrust::")
        || name.starts_with("cub::")
}
