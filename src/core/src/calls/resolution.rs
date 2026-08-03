use super::resolved::ResolvedCall;
use std::collections::BTreeMap;

/// Ordered graph answers and the next answer each source location consumes.
pub(crate) struct ResolutionIndex<'answers> {
    answers: &'answers BTreeMap<(String, usize), Vec<ResolvedCall>>,
    positions: BTreeMap<(String, usize), usize>,
}

impl<'answers> ResolutionIndex<'answers> {
    pub(crate) fn new(answers: &'answers BTreeMap<(String, usize), Vec<ResolvedCall>>) -> Self {
        Self {
            answers,
            positions: BTreeMap::new(),
        }
    }

    pub(super) fn next(&mut self, path: &str, line: usize) -> Option<&'answers ResolvedCall> {
        let key = (path.to_string(), line);
        let position = self.positions.entry(key.clone()).or_default();
        let answer = self
            .answers
            .get(&key)
            .and_then(|answers| answers.get(*position))?;
        *position += 1;
        Some(answer)
    }
}
