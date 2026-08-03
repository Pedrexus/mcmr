use ruff_text_size::TextSize;

pub(super) struct AccessRequest<'a> {
    pub(super) source: &'a str,
    pub(super) expression: &'a str,
    pub(super) offset: TextSize,
}
