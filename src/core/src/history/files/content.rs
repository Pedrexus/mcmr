/// How long one file is now, and the lines in it that name something else.
pub(in crate::history) struct Content {
    pub(in crate::history) line_count: usize,
    pub(in crate::history) imports: Vec<String>,
}
