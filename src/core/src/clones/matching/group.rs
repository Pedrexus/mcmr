use super::site::Site;
use crate::clones::streams::{Fragment, Stream};
use serde_json::{Value, json};
use std::collections::HashMap;

/// One repeated run of normalized tokens and every place it appears.
#[derive(Debug)]
pub(crate) struct Group {
    pub(super) length: usize,
    pub(super) sites: Vec<Site>,
}

impl Group {
    /// Return this group as the one fact a rule reads it through.
    pub(crate) fn fact(
        &self,
        streams: &[Stream],
        repository_line_count: usize,
        sources: &HashMap<&str, &str>,
    ) -> Value {
        let fragments: Vec<Fragment> = self
            .sites
            .iter()
            .map(|site| streams[site.stream].fragment(site.range(self.length)))
            .collect();
        let head = &fragments[0];
        json!({
            "key": format!("clone:{}:{}:{}", head.path, head.start_line, self.length),
            "span": {
                "path": head.path,
                "start_line": head.start_line,
                "start_column": 0,
                "end_line": head.end_line,
                "end_column": 0,
            },
            "language": streams[self.sites[0].stream].language,
            "token_length": self.length,
            "repository_line_count": repository_line_count,
            "fragments": fragments
                .iter()
                .map(|fragment| fragment.value(sources))
                .collect::<Vec<_>>(),
        })
    }

    /// Return the order this group is reported in, so two runs over one tree agree exactly.
    pub(crate) fn order(&self, streams: &[Stream]) -> (String, usize, usize) {
        let head = self.sites[0];
        let stream = &streams[head.stream];
        (
            stream.path.clone(),
            stream.tokens.lines[head.start],
            self.length,
        )
    }
}
