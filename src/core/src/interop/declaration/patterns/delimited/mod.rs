#[derive(Clone, Copy)]
pub(crate) struct DelimitedPattern<'a> {
    pub(crate) marker: &'a str,
    pub(crate) closing: char,
}

/// Return each name a macro states as its first argument.
pub(crate) fn between(text: &str, pattern: DelimitedPattern<'_>) -> impl Iterator<Item = String> {
    text.match_indices(pattern.marker)
        .filter_map(move |(position, _)| {
            let rest = &text[position + pattern.marker.len()..];
            let end = rest.find(pattern.closing)?;
            let name = rest[..end].trim().trim_matches('"').to_string();
            (!name.is_empty()).then_some(name)
        })
}
