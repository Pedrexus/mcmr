#[derive(Clone, Copy)]
pub struct SessionFamilies<'a> {
    pub typed: &'a [String],
    pub generic: &'a [String],
}
