use std::collections::HashMap;

/// The symbol table every normalized token is interned into.
///
/// Interning is what makes a window an array of integers, so comparing two windows is a memory
/// comparison rather than a string comparison and a window costs four bytes a token to keep.
#[derive(Default)]
pub(crate) struct Alphabet {
    ids: HashMap<String, u32>,
}

impl Alphabet {
    pub(crate) fn id(&mut self, text: &str) -> u32 {
        if let Some(known) = self.ids.get(text) {
            return *known;
        }
        let minted = u32::try_from(self.ids.len()).expect("clone token alphabet exceeded u32");
        self.ids.insert(text.to_string(), minted);
        minted
    }

    #[cfg(test)]
    pub(crate) fn text(&self, symbol: u32) -> Option<&str> {
        self.ids
            .iter()
            .find_map(|(text, known)| (*known == symbol).then_some(text.as_str()))
    }
}
