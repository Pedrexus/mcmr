use super::super::tokens::{Alphabet, IDENTIFIER, NOTHING, NUMBER, TEXT, TRUTH, Token};
use crate::discovery::Document;

/// Reduce one brace-language file, which here is TypeScript, C, C++, or CUDA.
///
/// The keyword list is the union over those four rather than one list each, because the cost of
/// calling a TypeScript variable named `struct` a keyword is nothing at all. Both sides of every
/// comparison pass through this same reader, so a coarse split still tells a copy from a body
/// that merely rhymes with it.
pub(in crate::clones) fn braces(
    document: &Document,
    alphabet: &mut Alphabet,
) -> Option<Vec<Token>> {
    const KEYWORDS: &[&str] = &[
        "as",
        "async",
        "auto",
        "await",
        "bool",
        "break",
        "case",
        "catch",
        "char",
        "class",
        "const",
        "constexpr",
        "continue",
        "default",
        "delete",
        "do",
        "double",
        "else",
        "enum",
        "export",
        "extends",
        "extern",
        "final",
        "finally",
        "float",
        "for",
        "from",
        "function",
        "goto",
        "if",
        "implements",
        "import",
        "in",
        "inline",
        "instanceof",
        "int",
        "interface",
        "let",
        "long",
        "namespace",
        "new",
        "of",
        "operator",
        "override",
        "private",
        "protected",
        "public",
        "readonly",
        "return",
        "short",
        "signed",
        "sizeof",
        "static",
        "struct",
        "super",
        "switch",
        "template",
        "this",
        "throw",
        "try",
        "typedef",
        "typename",
        "typeof",
        "union",
        "unsigned",
        "using",
        "var",
        "virtual",
        "void",
        "while",
        "yield",
    ];
    let source = document.source.as_bytes();
    let mut tokens: Vec<Token> = Vec::new();
    let mut cursor = ScanCursor::default();
    while cursor.offset < source.len() {
        let opened = cursor.line;
        match source[cursor.offset] {
            b'\n' => {
                cursor.line += 1;
                cursor.offset += 1;
            }
            byte if byte.is_ascii_whitespace() => cursor.offset += 1,
            b'/' if source.get(cursor.offset + 1) == Some(&b'/') => {
                cursor.skip_line_comment(source);
            }
            b'/' if source.get(cursor.offset + 1) == Some(&b'*') => {
                cursor.skip_block_comment(source)?;
            }
            quote @ (b'"' | b'\'' | b'`') => {
                cursor.skip_quoted(source, Quote::new(quote))?;
                tokens.push(Token::plain(alphabet.id(TEXT), opened));
            }
            byte if byte.is_ascii_digit() => {
                cursor.skip_token(source, is_number);
                tokens.push(Token::plain(alphabet.id(NUMBER), opened));
            }
            byte if is_word(byte) => {
                let from = cursor.offset;
                cursor.skip_token(source, is_word);
                let word = &document.source[from..cursor.offset];
                tokens.push(word_token(word, opened, alphabet, KEYWORDS));
            }
            _ => {
                tokens.push(Token::plain(
                    alphabet.id(&document.source[cursor.offset..cursor.offset + 1]),
                    opened,
                ));
                cursor.offset += 1;
            }
        }
    }
    Some(tokens)
}

/// Normalize one brace-language word while retaining the identity of an ordinary name.
fn word_token(word: &str, line: usize, alphabet: &mut Alphabet, keywords: &[&str]) -> Token {
    match word {
        "true" | "false" => Token::plain(alphabet.id(TRUTH), line),
        "null" | "undefined" | "nullptr" | "NULL" => Token::plain(alphabet.id(NOTHING), line),
        _ if keywords.contains(&word) => Token::plain(alphabet.id(word), line),
        _ => Token::identifier(alphabet.id(IDENTIFIER), line, word.to_string()),
    }
}

struct ScanCursor {
    offset: usize,
    line: usize,
}

impl Default for ScanCursor {
    fn default() -> Self {
        Self { offset: 0, line: 1 }
    }
}

impl ScanCursor {
    /// Advance past one closed block comment while tracking its source line.
    fn skip_block_comment(&mut self, source: &[u8]) -> Option<()> {
        self.offset += 2;
        while self.offset < source.len()
            && !(source[self.offset] == b'*' && source.get(self.offset + 1) == Some(&b'/'))
        {
            self.line += usize::from(source[self.offset] == b'\n');
            self.offset += 1;
        }
        source.get(self.offset..self.offset + 2)?;
        self.offset += 2;
        Some(())
    }

    /// Advance past one line comment.
    fn skip_line_comment(&mut self, source: &[u8]) {
        while self.offset < source.len() && source[self.offset] != b'\n' {
            self.offset += 1;
        }
    }

    /// Advance past one closed quoted literal while tracking its source line.
    fn skip_quoted(&mut self, source: &[u8], quote: Quote) -> Option<()> {
        self.offset += 1;
        while source.get(self.offset).copied()? != quote.byte() {
            self.line += usize::from(source[self.offset] == b'\n');
            if source[self.offset] == b'\\' {
                self.offset += 1;
                self.line += usize::from(source.get(self.offset).copied()? == b'\n');
            }
            self.offset += 1;
        }
        self.offset += 1;
        Some(())
    }

    /// Advance to the first byte that `continues` rejects.
    fn skip_token(&mut self, source: &[u8], continues: fn(u8) -> bool) {
        while self.offset < source.len() && continues(source[self.offset]) {
            self.offset += 1;
        }
    }
}

/// Whether one byte can sit inside a name, counting the bytes a non-ASCII letter is written in.
fn is_word(byte: u8) -> bool {
    byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'$') || byte >= 0x80
}

/// Whether one byte can sit inside a numeric literal, including its base and digit separators.
fn is_number(byte: u8) -> bool {
    byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'\'')
}
mod quote;

use quote::Quote;
