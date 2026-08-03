/// One copy of a repeated run, as the lines of one file it covers.
#[derive(Debug)]
pub(crate) struct Fragment {
    pub(crate) path: String,
    pub(crate) start_line: usize,
    pub(crate) end_line: usize,
}
