/// What one language has to say about its own comments.
pub trait Dialect {
    /// Whether one comment body speaks to a tool rather than to a reader.
    fn is_directive(&mut self, body: &str) -> bool;

    /// Whether one comment body is source this language would compile rather than prose.
    fn is_source(&mut self, body: &str) -> bool;
}
