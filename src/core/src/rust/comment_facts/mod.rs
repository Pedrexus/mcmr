use crate::comments;
use crate::comments::CommentText as _;

/// What Rust says about its own comments, past what the shared reader already settles.
pub(super) struct Notes;

impl comments::Dialect for Notes {
    /// Whether one comment addresses a tool rather than a reader.
    ///
    /// Rust states most of its suppressions as attributes, which are code and never reach here.
    /// What is left is the switches the tools around the compiler still read from a comment, and
    /// all of them are written as the opening word.
    fn is_directive(&mut self, body: &str) -> bool {
        body.opens_with(&[
            "rustfmt",
            "clippy",
            "tarpaulin",
            "grcov",
            "coverage:",
            "codecov",
            "cspell",
            "cbindgen",
        ])
    }

    /// Whether one comment body is Rust rather than prose, decided by parsing it.
    ///
    /// A block is tried first and a file second, because a commented-out statement is far and away
    /// the common case and settling it takes one parse. A declaration needs the second, since a
    /// block holding one parses as the item rather than as what a body would run.
    ///
    /// A block here yields its last expression, so a note that only calls something is code even
    /// with no semicolon in it, and the punctuation worth handing to the parser is wider than what
    /// a brace language would ask for.
    fn is_source(&mut self, body: &str) -> bool {
        comments::holds_code(body, &['=', '(', ';', '{'])
            && (syn::parse_str::<syn::Block>(&format!("{{{body}}}")).is_ok()
                || syn::parse_file(body).is_ok())
    }
}

/// Return every comment one Rust source states, in the order it states them.
///
/// `syn` keeps a doc comment as an attribute and drops every other one, and the token stream drops
/// them all, so the only reader that sees an ordinary comment is a lexical one. What it has to get
/// right is where a comment is not a comment, since `//` inside a URL and `/*` inside a pattern
/// are text. Strings, raw strings, and characters are therefore stepped over rather than read, and
/// a block comment nests, which is the one place this language differs from its neighbours.
///
/// The cursor walks characters rather than bytes. A source is a `str` and slicing one anywhere but
/// a character boundary panics, so a scanner stepping a byte at a time takes the whole run down
/// the first time an identifier, a literal, or a comment is written in any language but English.
pub(super) fn scan(text: &str) -> Vec<ruff_text_size::TextRange> {
    let mut found = Vec::new();
    let mut cursor = 0;
    while let Some(held) = text[cursor..].chars().next() {
        let rest = &text[cursor..];
        if rest.starts_with("//") {
            let end = rest.find('\n').map_or(text.len(), |offset| cursor + offset);
            found.push(comments::at(cursor..end));
            cursor = end;
        } else if rest.starts_with("/*") {
            let end = block_end(text, cursor);
            found.push(comments::at(cursor..end));
            cursor = end;
        } else {
            cursor = match held {
                '"' => quoted_end(text, cursor + 1, '"'),
                '\'' => character_end(text, cursor + 1),
                'r' if rest.starts_with("r\"") || rest.starts_with("r#") => raw_end(text, cursor),
                _ => cursor + held.len_utf8(),
            };
        }
    }
    found
}

/// Return the offset one character past the one this offset opens.
fn after(text: &str, at: usize) -> usize {
    at + text[at..].chars().next().map_or(0, char::len_utf8)
}

/// Return where one nested block comment closes, which is where its last `*/` matches its first.
fn block_end(text: &str, at: usize) -> usize {
    let mut depth = 0;
    let mut cursor = at;
    while cursor < text.len() {
        let rest = &text[cursor..];
        if rest.starts_with("/*") {
            depth += 1;
            cursor += 2;
        } else if rest.starts_with("*/") {
            depth -= 1;
            cursor += 2;
            if depth == 0 {
                return cursor;
            }
        } else {
            cursor = after(text, cursor);
        }
    }
    text.len()
}

/// Return where one quoted literal closes, stepping over whatever a backslash escaped.
fn quoted_end(text: &str, at: usize, closing: char) -> usize {
    let mut cursor = at;
    while let Some(held) = text[cursor..].chars().next() {
        match held {
            '\\' => cursor = after(text, cursor + 1),
            found if found == closing => return cursor + closing.len_utf8(),
            _ => cursor += held.len_utf8(),
        }
    }
    text.len()
}

/// Return where one character literal closes, which a lifetime never does.
///
/// `'a` opens no literal, so a lifetime and a label have to be stepped past or every borrow in the
/// file would swallow the source after it. What tells the two apart is what follows the quote: an
/// escape always opens a literal, and a single character followed by the closing quote does too,
/// whatever that character costs in bytes.
fn character_end(text: &str, at: usize) -> usize {
    let mut held = text[at..].chars();
    match held.next() {
        Some('\\') => quoted_end(text, at, '\''),
        Some(_) if held.next() == Some('\'') => quoted_end(text, at, '\''),
        _ => at,
    }
}

/// Return where one raw string closes, which is the hash count its opening declared.
fn raw_end(text: &str, at: usize) -> usize {
    let hashes = text[at + 1..]
        .chars()
        .take_while(|held| *held == '#')
        .count();
    let opened = at + 1 + hashes;
    let closing = format!("\"{}", "#".repeat(hashes));
    match text[opened..].starts_with('"') {
        true => text[opened + 1..]
            .find(&closing)
            .map_or(text.len(), |offset| opened + 1 + offset + closing.len()),
        false => at + 1,
    }
}
