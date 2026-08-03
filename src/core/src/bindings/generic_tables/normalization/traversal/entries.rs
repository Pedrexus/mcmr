use super::super::kind::ContainerKind;
use serde_json::Value;

pub(crate) use context::EntryContext;

mod context;

pub(crate) enum ContainerEntries<'a> {
    Array(std::slice::Iter<'a, Value>),
    Map(serde_json::map::Iter<'a>),
}

impl<'a> Iterator for ContainerEntries<'a> {
    type Item = (Option<&'a str>, &'a Value);

    fn next(&mut self) -> Option<Self::Item> {
        match self {
            Self::Array(entries) => entries.next().map(|value| (None, value)),
            Self::Map(entries) => entries
                .next()
                .map(|(key, value)| (Some(key.as_str()), value)),
        }
    }
}

impl ContainerEntries<'_> {
    pub(crate) fn len(&self) -> usize {
        match self {
            Self::Array(entries) => entries.len(),
            Self::Map(entries) => entries.len(),
        }
    }
}

pub(crate) fn container_entries<'a>(
    kind: ContainerKind,
    actual: &'a Value,
    relation: &str,
) -> Result<ContainerEntries<'a>, String> {
    match kind {
        ContainerKind::Array => actual
            .as_array()
            .map(|entries| ContainerEntries::Array(entries.iter()))
            .ok_or_else(|| format!("relation {relation} is not an array")),
        ContainerKind::Map => actual
            .as_object()
            .map(|entries| ContainerEntries::Map(entries.iter()))
            .ok_or_else(|| format!("relation {relation} is not a map")),
    }
}
