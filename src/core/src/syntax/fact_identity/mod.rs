#[derive(Clone, Copy)]
pub struct SyntaxFactIdentity<'declaration> {
    pub language: &'declaration str,
    pub qualname: &'declaration str,
    pub written: &'declaration str,
}
