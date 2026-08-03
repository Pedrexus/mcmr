#[derive(Clone, Copy)]
pub(crate) struct IdentifierPattern<'a> {
    pub(crate) marker: &'a str,
    pub(crate) separator: &'a str,
}

/// Return each identifier that follows one marker.
pub(crate) fn after(text: &str, pattern: IdentifierPattern<'_>) -> impl Iterator<Item = String> {
    text.match_indices(pattern.marker)
        .filter_map(move |(position, _)| {
            let rest = &text[position + pattern.marker.len()..];
            let start = rest.find(pattern.separator)? + pattern.separator.len();
            let name: String = rest[start..]
                .chars()
                .skip_while(|letter| letter.is_whitespace())
                .take_while(|letter| letter.is_alphanumeric() || *letter == '_')
                .collect();
            (!name.is_empty()).then_some(name)
        })
}
