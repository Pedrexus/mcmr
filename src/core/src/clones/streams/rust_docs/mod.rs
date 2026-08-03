use proc_macro2::{Delimiter, Group, TokenTree};

/// Whether one bracketed group is the attribute a doc comment was rewritten into.
pub(crate) fn documents(group: &Group) -> bool {
    if group.delimiter() != Delimiter::Bracket {
        return false;
    }
    let mut inside = group.stream().into_iter();
    let named = matches!(inside.next(), Some(TokenTree::Ident(ident)) if ident == "doc");
    named && matches!(inside.next(), Some(TokenTree::Punct(punct)) if punct.as_char() == '=')
}
