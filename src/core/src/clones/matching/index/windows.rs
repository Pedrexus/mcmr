use super::super::site::Site;
use super::contracts::WindowGroups;
use crate::clones::streams::Stream;
use crate::clones::tokens::WINDOW;

pub(crate) fn identical<'a>(streams: &'a [Stream], block: &[(u64, Site)]) -> WindowGroups<'a> {
    let mut found = WindowGroups::new();
    for (_, site) in block {
        let stream = &streams[site.stream];
        found
            .entry((
                stream.language,
                stream.window(site.range(WINDOW)),
                stream.identity_pattern(site.range(WINDOW)),
            ))
            .or_default()
            .push(*site);
    }
    found
}
