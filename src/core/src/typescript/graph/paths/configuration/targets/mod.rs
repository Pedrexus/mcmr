/// One or more targets a TypeScript path mapping is required to state.
#[derive(Clone, Debug)]
pub(super) struct Targets {
    pub(super) first: String,
    pub(super) remaining: Vec<String>,
}

impl Targets {
    pub(super) fn from_config(pattern: &str, targets: Vec<String>) -> Result<Self, String> {
        let mut normalized = targets.into_iter();
        Ok(Self {
            first: normalized.next().ok_or_else(|| {
                format!("compilerOptions.paths target `{pattern}` must not be empty")
            })?,
            remaining: normalized.collect(),
        })
    }

    pub(super) fn replacing(&self, pattern: char, value: &str) -> Self {
        Self {
            first: self.first.replacen(pattern, value, 1),
            remaining: self
                .remaining
                .iter()
                .map(|target| target.replacen(pattern, value, 1))
                .collect(),
        }
    }

    pub(super) fn values(&self) -> impl Iterator<Item = &str> {
        std::iter::once(self.first.as_str()).chain(self.remaining.iter().map(String::as_str))
    }
}
