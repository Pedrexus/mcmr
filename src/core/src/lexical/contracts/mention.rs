#[derive(Clone, Copy)]
pub struct Mention<'a> {
    pub name: &'a str,
    pub declared_in: &'a str,
}
