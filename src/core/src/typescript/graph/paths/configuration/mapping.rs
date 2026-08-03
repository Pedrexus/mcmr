use super::targets::Targets;
use crate::typescript::graph::paths::names::JoinedPath;

/// One `paths` entry, as the specifier prefix it matches and the module prefixes it stands for.
#[derive(Debug)]
pub(in crate::typescript) struct Mapping {
    pub(super) pattern: String,
    pub(super) targets: Targets,
}

impl Mapping {
    pub(super) fn from_config(
        pattern: &str,
        targets: &[String],
        base: &str,
    ) -> Result<Self, String> {
        Ok(Self {
            pattern: pattern.to_owned(),
            targets: Targets::from_config(pattern, normalized_targets(targets, base))?,
        })
    }

    /// Return what one specifier becomes under this mapping, when this mapping matches it.
    pub(super) fn apply(&self, specifier: &str) -> Option<Targets> {
        let Some((head, tail)) = self.pattern.split_once('*') else {
            return (self.pattern == specifier).then(|| self.targets.clone());
        };
        let held = specifier.strip_prefix(head)?.strip_suffix(tail)?;
        Some(self.targets.replacing('*', held))
    }
}

fn normalized_targets(targets: &[String], base: &str) -> Vec<String> {
    targets
        .iter()
        .map(|target| {
            JoinedPath {
                parent: base,
                child: target,
            }
            .normalized()
        })
        .collect()
}
