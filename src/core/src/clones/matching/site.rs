use std::ops::Range;

use crate::clones::streams::Stream;

/// One place a repeated window starts, as the file it is in and the token it begins at.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub(crate) struct Site {
    pub(super) stream: usize,
    pub(super) start: usize,
}

/// Drop copies whose token or physical line range overlaps a copy already kept.
pub(super) fn without_overlap(members: &[Site], length: usize, streams: &[Stream]) -> Vec<Site> {
    let mut kept: Vec<Site> = Vec::new();
    for site in members {
        let inside = kept.last().is_some_and(|prior| {
            if prior.stream != site.stream {
                return false;
            }
            let tokens_overlap = prior.start + length > site.start;
            let stream = &streams[site.stream];
            let (_, prior_end) = stream.line_range(prior.range(length));
            let (current_start, _) = stream.line_range(site.range(length));
            let lines_overlap = prior_end >= current_start;
            tokens_overlap || lines_overlap
        });
        if !inside {
            kept.push(*site);
        }
    }
    kept
}

impl Site {
    pub(super) fn range(&self, length: usize) -> Range<usize> {
        self.start..self.start + length
    }
}
