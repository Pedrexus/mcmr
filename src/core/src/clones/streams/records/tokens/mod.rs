pub(crate) struct StreamTokens {
    pub(crate) symbols: Vec<u32>,
    pub(crate) identities: Vec<Option<String>>,
    pub(crate) lines: Vec<usize>,
    pub(crate) depths: Vec<usize>,
    pub(crate) fingerprints: Vec<u64>,
}
