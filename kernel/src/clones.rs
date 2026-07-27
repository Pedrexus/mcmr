use crate::discovery::Document;
use crate::graph::Language;
use crate::source::Source;
use proc_macro2::{Delimiter, TokenStream, TokenTree};
use ruff_python_ast::token::TokenKind;
use ruff_python_parser::parse_module;
use ruff_text_size::Ranged;
use serde_json::{Value, json};
use std::collections::{BTreeMap, HashMap};
use std::str::FromStr;

/// The shortest run of normalized tokens worth calling a duplicate.
///
/// Pylint's Symilar defaults to four similar lines, but those are four lines of exact text, which
/// is a far stronger claim than four lines of shape. Normalization throws every name and every
/// literal away on purpose, so the floor has to buy back what it gave away or the detector starts
/// reporting grammar. Whole-file scanning needed sixty tokens before shared declarations stopped
/// looking like copies. Candidate windows are now confined to implementation blocks, so forty
/// tokens can find a compact pasted body without admitting module scaffolding.
const WINDOW: usize = 40;

/// What every identifier is reduced to, which is what lets a rename stay a clone.
const IDENTIFIER: &str = "$id";
/// What every string, character, and interpolated text literal is reduced to.
const TEXT: &str = "$s";
/// What every integer, float, and complex literal is reduced to.
const NUMBER: &str = "$n";
/// What every boolean literal is reduced to.
const TRUTH: &str = "$b";
/// What every empty literal is reduced to, whichever word its language spells it with.
const NOTHING: &str = "$x";
/// The end of a logical line, kept because a statement boundary is structure rather than trivia.
const NEWLINE: &str = "$nl";
/// The opening of an indented block, which is how an off-side language states nesting.
const INDENT: &str = "$in";
/// The closing of an indented block.
const DEDENT: &str = "$de";

/// Find the implementation blocks that say the same thing in different places.
///
/// Detection is token normalized rather than textual, so a clone survives renamed locals and
/// reformatting, which is what separates a real duplicate from two functions that happen to share
/// a shape. What this returns is the locations, and the judgment of whether a duplicate is worth
/// removing belongs to the rule that reads them.
///
/// Every language the kernel reads is normalized, by three readers rather than one. Python goes
/// through the same `ruff` lexer the Python frontend parses with, Rust through the `proc-macro2`
/// token stream, and TypeScript, C, C++, and CUDA through one small brace-language lexer written
/// here. That last reader is deliberately coarse. A multi-character operator arrives as its
/// separate characters, a template literal and a regular expression each arrive as one text
/// placeholder, and the keyword list is the union over those four languages rather than one list
/// each. None of that costs a comparison its meaning, because both sides of every comparison are
/// reduced by the very same reader, but the token count is coarser here than a full grammar would
/// give. The Rust reader has one quirk of its own worth stating, which is that a doc comment
/// reaches it as the `#[doc = "..."]` attribute the lexer already made of it, so dropping doc
/// comments is something this code does deliberately rather than something it inherits.
///
/// Only windows inside an indented or braced implementation block are candidates. Module imports,
/// declarations, documentation, and other top-level scaffolding are evidence of a shared API or
/// framework rather than copied implementation. The cost is linear in the tokens read. Each file
/// is reduced once, a rolling hash fingerprints every window in one pass, and equal fingerprints
/// are found by sorting rather than by comparing windows against each other, so no file is ever
/// tested against another file.
pub fn scan(documents: &[Document]) -> Vec<Value> {
    let mut alphabet = Alphabet::default();
    let streams: Vec<Stream> = documents
        .iter()
        .filter_map(|document| Stream::read(document, &mut alphabet))
        .collect();
    let repository_line_count: usize = streams.iter().map(|stream| stream.line_count).sum();
    let mut groups = maximal(repeated(&streams), &streams);
    groups.sort_by_key(|group| group.order(&streams));
    groups
        .iter()
        .map(|group| group.fact(&streams, repository_line_count))
        .collect()
}

/// Return every run of normalized tokens that appears in more than one place.
///
/// The whole repository is fingerprinted into one list of window starts, which is sorted so that
/// equal fingerprints sit together. Each block of equal fingerprints is then split by the tokens
/// it actually holds, because a fingerprint is a hash and two unrelated windows may land on one.
/// A group that also matches one token earlier is dropped, since the longer run containing it is
/// reported instead, and what survives is grown to the right for as long as every copy agrees.
fn repeated(streams: &[Stream]) -> Vec<Group> {
    let mut index: Vec<(u64, Site)> = Vec::new();
    for (position, stream) in streams.iter().enumerate() {
        index.extend(
            stream
                .fingerprints
                .iter()
                .enumerate()
                .filter(|(start, _)| stream.inside(*start, WINDOW))
                .map(|(start, fingerprint)| (*fingerprint, Site::new(position, start))),
        );
    }
    index.sort_unstable();
    let mut groups = Vec::new();
    let mut at = 0;
    while at < index.len() {
        let width = index[at..].partition_point(|(seen, _)| *seen == index[at].0);
        let block = &index[at..at + width];
        at += width;
        if block.len() < 2 {
            continue;
        }
        for members in identical(streams, block).into_values() {
            if members.len() < 2 || extends_left(streams, &index, &members) {
                continue;
            }
            let length = extent(streams, &members);
            let sites = without_overlap(&members, length);
            if sites.len() > 1 {
                groups.push(Group { length, sites });
            }
        }
    }
    groups
}

/// Keep the longest reading of every duplicated region and drop the ones nested inside it.
///
/// One copied region is shared by a different set of files at each of its lengths, since a file
/// that stops matching halfway through still matched the first half. Every one of those readings
/// is a real group, and reporting all of them would bury the finding that matters under the
/// shorter ones it already contains. The longest wins, and a group survives only where at least
/// two of its copies are still somewhere no longer group has claimed.
fn maximal(groups: Vec<Group>, streams: &[Stream]) -> Vec<Group> {
    let mut ordered = groups;
    ordered.sort_by(|left, right| {
        right
            .length
            .cmp(&left.length)
            .then_with(|| left.sites.cmp(&right.sites))
    });
    let mut claimed: Vec<Vec<(usize, usize)>> = vec![Vec::new(); streams.len()];
    let mut kept: Vec<Group> = Vec::new();
    for group in ordered {
        let fresh = group
            .sites
            .iter()
            .filter(|site| {
                !claimed[site.stream]
                    .iter()
                    .any(|(from, to)| *from <= site.start && site.start + group.length <= *to)
            })
            .count();
        if fresh < 2 {
            continue;
        }
        for site in &group.sites {
            claimed[site.stream].push((site.start, site.start + group.length));
        }
        kept.push(group);
    }
    kept
}

/// Split one block of equal fingerprints into the sets whose tokens really are the same.
///
/// The language leads the key so that a Python window and a TypeScript window reduced to the same
/// placeholders are never called copies of each other. They share one alphabet and could collide
/// on `$id ( $id )` alone, and a clone across two languages is a claim this detector cannot make.
fn identical<'a>(
    streams: &'a [Stream],
    block: &[(u64, Site)],
) -> BTreeMap<(Language, &'a [u32]), Vec<Site>> {
    let mut found: BTreeMap<(Language, &[u32]), Vec<Site>> = BTreeMap::new();
    for (_, site) in block {
        let stream = &streams[site.stream];
        found
            .entry((stream.language, stream.window(site.start, WINDOW)))
            .or_default()
            .push(*site);
    }
    found
}

/// Whether every copy in one group can step a token to the left together.
///
/// A duplicated run of tokens produces one window at every starting position inside it, and
/// reporting all of them would report a single copied function forty times. Only the leftmost
/// window survives, and a window whose whole membership matches one token earlier as well is not
/// the leftmost one. The membership has to match in size too, since a group that loses a copy by
/// stepping left is a longer shared run of its own rather than the tail of the shorter one.
fn extends_left(streams: &[Stream], index: &[(u64, Site)], members: &[Site]) -> bool {
    let Some(head) = members.first() else {
        return false;
    };
    if members.iter().any(|site| site.start == 0) {
        return false;
    }
    if members
        .iter()
        .any(|site| !streams[site.stream].inside(site.start - 1, WINDOW))
    {
        return false;
    }
    let earlier = streams[head.stream].symbols[head.start - 1];
    let together = members
        .iter()
        .all(|site| streams[site.stream].symbols[site.start - 1] == earlier);
    together
        && occurrences(streams, index, Site::new(head.stream, head.start - 1)) == members.len()
}

/// Return how many windows in the repository hold exactly what one window holds.
fn occurrences(streams: &[Stream], index: &[(u64, Site)], site: Site) -> usize {
    let stream = &streams[site.stream];
    let fingerprint = stream.fingerprints[site.start];
    let window = stream.window(site.start, WINDOW);
    let first = index.partition_point(|(seen, _)| *seen < fingerprint);
    index[first..]
        .iter()
        .take_while(|(seen, _)| *seen == fingerprint)
        .filter(|(_, other)| {
            let candidate = &streams[other.stream];
            candidate.language == stream.language
                && candidate.window(other.start, WINDOW) == window
        })
        .count()
}

/// Grow one match to the right for as long as every copy states the same next token.
fn extent(streams: &[Stream], members: &[Site]) -> usize {
    let head = members[0];
    let mut length = WINDOW;
    while let Some(symbol) = streams[head.stream].symbols.get(head.start + length) {
        if streams[head.stream].depths[head.start + length] == 0 {
            break;
        }
        let shared = members[1..].iter().all(|site| {
            streams[site.stream]
                .depths
                .get(site.start + length)
                .copied()
                != Some(0)
                && streams[site.stream].symbols.get(site.start + length) == Some(symbol)
        });
        if !shared {
            break;
        }
        length += 1;
    }
    length
}

/// Drop the copies that sit inside a copy already kept, which only a self-similar run produces.
fn without_overlap(members: &[Site], length: usize) -> Vec<Site> {
    let mut kept: Vec<Site> = Vec::new();
    for site in members {
        let inside = kept
            .last()
            .is_some_and(|prior| prior.stream == site.stream && prior.start + length > site.start);
        if !inside {
            kept.push(*site);
        }
    }
    kept
}

/// One place a repeated window starts, as the file it is in and the token it begins at.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
struct Site {
    stream: usize,
    start: usize,
}

impl Site {
    fn new(stream: usize, start: usize) -> Self {
        Self { stream, start }
    }
}

/// One repeated run of normalized tokens and every place it appears.
#[derive(Debug)]
struct Group {
    length: usize,
    sites: Vec<Site>,
}

impl Group {
    /// Return the order this group is reported in, so two runs over one tree agree exactly.
    fn order(&self, streams: &[Stream]) -> (String, u32, usize) {
        let head = self.sites[0];
        let stream = &streams[head.stream];
        (stream.path.clone(), stream.lines[head.start], self.length)
    }

    /// Return this group as the one fact a rule reads it through.
    fn fact(&self, streams: &[Stream], repository_line_count: usize) -> Value {
        let fragments: Vec<Fragment> = self
            .sites
            .iter()
            .map(|site| streams[site.stream].fragment(site.start, self.length))
            .collect();
        let head = &fragments[0];
        json!({
            "key": format!("clone:{}:{}:{}", head.path, head.start_line, self.length),
            "span": {
                "path": head.path,
                "start_line": head.start_line,
                "start_column": 0,
                "end_line": head.end_line,
                "end_column": 0,
            },
            "language": streams[self.sites[0].stream].language,
            "token_length": self.length,
            "repository_line_count": repository_line_count,
            "fragments": fragments.iter().map(Fragment::value).collect::<Vec<_>>(),
        })
    }
}

/// One copy of a repeated run, as the lines of one file it covers.
#[derive(Debug)]
struct Fragment {
    path: String,
    start_line: u32,
    end_line: u32,
}

impl Fragment {
    fn value(&self) -> Value {
        json!({
            "path": self.path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "line_count": self.end_line - self.start_line + 1,
        })
    }
}

/// The symbol table every normalized token is interned into.
///
/// Interning is what makes a window an array of integers, so comparing two windows is a memory
/// comparison rather than a string comparison and a window costs four bytes a token to keep.
#[derive(Default)]
struct Alphabet {
    ids: HashMap<String, u32>,
}

impl Alphabet {
    fn id(&mut self, text: &str) -> u32 {
        if let Some(known) = self.ids.get(text) {
            return *known;
        }
        let minted = u32::try_from(self.ids.len()).unwrap_or(u32::MAX);
        self.ids.insert(text.to_string(), minted);
        minted
    }
}

/// One file reduced to the normalized tokens a clone is matched on.
struct Stream {
    path: String,
    language: Language,
    symbols: Vec<u32>,
    lines: Vec<u32>,
    depths: Vec<usize>,
    block_open: u32,
    fingerprints: Vec<u64>,
    line_count: usize,
}

impl Stream {
    /// Reduce one document, through the reader its language needs.
    fn read(document: &Document, alphabet: &mut Alphabet) -> Option<Self> {
        let language = Language::of(&document.relative)?;
        let tokens = match language {
            Language::Python => python(document, alphabet),
            Language::Rust => rust(document, alphabet),
            Language::TypeScript | Language::C | Language::Cpp | Language::Cuda => {
                braces(document, alphabet)
            }
        };
        let symbols: Vec<u32> = tokens.iter().map(|(symbol, _)| *symbol).collect();
        let (open, close) = match language {
            Language::Python => (alphabet.id(INDENT), alphabet.id(DEDENT)),
            Language::Rust
            | Language::TypeScript
            | Language::C
            | Language::Cpp
            | Language::Cuda => (alphabet.id("{"), alphabet.id("}")),
        };
        let depths = nesting(&symbols, open, close);
        let fingerprints = fingerprint(&symbols);
        Some(Self {
            path: document.relative.clone(),
            language,
            symbols,
            lines: tokens.iter().map(|(_, line)| *line).collect(),
            depths,
            block_open: open,
            fingerprints,
            line_count: document.source.lines().count(),
        })
    }

    fn window(&self, start: usize, length: usize) -> &[u32] {
        &self.symbols[start..start + length]
    }

    /// Whether one candidate window lies wholly inside an implementation block.
    fn inside(&self, start: usize, length: usize) -> bool {
        self.depths
            .get(start..start + length)
            .is_some_and(|depths| depths.iter().all(|depth| *depth > 0))
    }

    fn fragment(&self, start: usize, length: usize) -> Fragment {
        let start_line = match start.checked_sub(1) {
            Some(previous) if self.symbols[previous] == self.block_open => match self.language {
                Language::Python => self.lines[previous.saturating_sub(1)],
                _ => self.lines[previous],
            },
            _ => self.lines[start],
        };
        Fragment {
            path: self.path.clone(),
            start_line,
            end_line: self.lines[start + length - 1],
        }
    }
}

/// Return the block depth of every token, leaving delimiters outside the block they introduce.
fn nesting(symbols: &[u32], open: u32, close: u32) -> Vec<usize> {
    let mut depth: usize = 0;
    symbols
        .iter()
        .map(|symbol| {
            if *symbol == close {
                depth = depth.saturating_sub(1);
            }
            let current = depth;
            if *symbol == open {
                depth += 1;
            }
            current
        })
        .collect()
}

/// Fingerprint every window of one token stream in a single pass.
///
/// The hash is a polynomial over scrambled symbols, rolled one token at a time, so the whole file
/// costs one multiply and one add per token rather than one pass per window. It is a hash and not
/// a proof, which is why the caller compares the tokens themselves before calling two windows the
/// same run.
fn fingerprint(symbols: &[u32]) -> Vec<u64> {
    const BASE: u64 = 0x0000_0100_0000_01b3;
    if symbols.len() < WINDOW {
        return Vec::new();
    }
    let power = BASE.wrapping_pow(u32::try_from(WINDOW - 1).unwrap_or(u32::MAX));
    let mut rolling = symbols[..WINDOW].iter().fold(0u64, |carried, symbol| {
        carried.wrapping_mul(BASE).wrapping_add(scramble(*symbol))
    });
    let mut fingerprints = vec![rolling];
    for start in 1..=symbols.len() - WINDOW {
        rolling = rolling.wrapping_sub(scramble(symbols[start - 1]).wrapping_mul(power));
        rolling = rolling
            .wrapping_mul(BASE)
            .wrapping_add(scramble(symbols[start + WINDOW - 1]));
        fingerprints.push(rolling);
    }
    fingerprints
}

/// Spread one small symbol number across a whole word, so the rolling hash has bits to work with.
fn scramble(symbol: u32) -> u64 {
    let mut mixed = u64::from(symbol).wrapping_add(0x9e37_79b9_7f4a_7c15);
    mixed = (mixed ^ (mixed >> 30)).wrapping_mul(0xbf58_476d_1ce4_e5b9);
    mixed = (mixed ^ (mixed >> 27)).wrapping_mul(0x94d0_49bb_1331_11eb);
    mixed ^ (mixed >> 31)
}

/// Reduce one Python file through the same lexer the Python frontend parses with.
///
/// A dedent is written where the block it closes has already ended, so it carries no source of
/// its own and would otherwise report a clone as reaching one line past its last statement. Every
/// token that spans no text takes the line of the last token that did.
fn python(document: &Document, alphabet: &mut Alphabet) -> Vec<(u32, u32)> {
    let Ok(parsed) = parse_module(&document.source) else {
        return Vec::new();
    };
    let source = Source::new(&document.relative, &document.source);
    let mut tokens = Vec::new();
    let mut written = 1;
    for token in parsed.tokens() {
        let text = match token.kind() {
            TokenKind::Comment | TokenKind::NonLogicalNewline | TokenKind::EndOfFile => continue,
            TokenKind::Newline => NEWLINE,
            TokenKind::Indent => INDENT,
            TokenKind::Dedent => DEDENT,
            TokenKind::Name => IDENTIFIER,
            TokenKind::Int | TokenKind::Float | TokenKind::Complex => NUMBER,
            TokenKind::String
            | TokenKind::FStringStart
            | TokenKind::FStringMiddle
            | TokenKind::FStringEnd
            | TokenKind::TStringStart
            | TokenKind::TStringMiddle
            | TokenKind::TStringEnd => TEXT,
            TokenKind::True | TokenKind::False => TRUTH,
            TokenKind::None => NOTHING,
            _ => source.slice(token.range()),
        };
        if !token.range().is_empty() {
            written = source.line_of(token.range().start());
        }
        tokens.push((alphabet.id(text), u32::try_from(written).unwrap_or(1)));
    }
    tokens
}

/// Reduce one Rust file through the token stream its own front end would see.
fn rust(document: &Document, alphabet: &mut Alphabet) -> Vec<(u32, u32)> {
    let Ok(parsed) = TokenStream::from_str(&document.source) else {
        return Vec::new();
    };
    let mut tokens = Vec::new();
    flatten(parsed, alphabet, &mut tokens);
    tokens
}

/// Write one Rust token stream out flat, keeping the delimiters that carry its nesting.
///
/// A doc comment reaches this reader as the `#[doc = "..."]` attribute the lexer already turned
/// it into, so dropping it here is what keeps the promise that a comment never decides whether
/// two items are copies. The hash and the bang that introduced the attribute go with it.
fn flatten(stream: TokenStream, alphabet: &mut Alphabet, tokens: &mut Vec<(u32, u32)>) {
    const KEYWORDS: &[&str] = &[
        "Self", "as", "async", "await", "break", "const", "continue", "crate", "dyn", "else",
        "enum", "extern", "fn", "for", "if", "impl", "in", "let", "loop", "match", "mod", "move",
        "mut", "pub", "ref", "return", "self", "static", "struct", "super", "trait", "type",
        "union", "unsafe", "use", "where", "while",
    ];
    for tree in stream {
        let line = u32::try_from(tree.span().start().line).unwrap_or(1);
        match tree {
            TokenTree::Ident(ident) => {
                let name = ident.to_string();
                let text = match name.as_str() {
                    "true" | "false" => TRUTH,
                    word if KEYWORDS.contains(&word) => word,
                    _ => IDENTIFIER,
                };
                tokens.push((alphabet.id(text), line));
            }
            TokenTree::Literal(literal) => {
                let written = literal.to_string();
                let text = match written.starts_with(['"', '\'', 'b', 'c', 'r']) {
                    true => TEXT,
                    false => NUMBER,
                };
                tokens.push((alphabet.id(text), line));
            }
            TokenTree::Punct(punct) => {
                tokens.push((alphabet.id(&punct.as_char().to_string()), line));
            }
            TokenTree::Group(group) if documents(&group) => {
                let markers = [alphabet.id("#"), alphabet.id("!")];
                while tokens
                    .last()
                    .is_some_and(|(symbol, _)| markers.contains(symbol))
                {
                    tokens.pop();
                }
            }
            TokenTree::Group(group) => {
                let (open, close) = match group.delimiter() {
                    Delimiter::Parenthesis => ("(", ")"),
                    Delimiter::Brace => ("{", "}"),
                    Delimiter::Bracket => ("[", "]"),
                    Delimiter::None => (INDENT, DEDENT),
                };
                tokens.push((alphabet.id(open), line));
                flatten(group.stream(), alphabet, tokens);
                let closing = u32::try_from(group.span_close().start().line).unwrap_or(line);
                tokens.push((alphabet.id(close), closing));
            }
        }
    }
}

/// Whether one bracketed group is the attribute a doc comment was rewritten into.
fn documents(group: &proc_macro2::Group) -> bool {
    if group.delimiter() != Delimiter::Bracket {
        return false;
    }
    let mut inside = group.stream().into_iter();
    let named = matches!(inside.next(), Some(TokenTree::Ident(ident)) if ident == "doc");
    named && matches!(inside.next(), Some(TokenTree::Punct(punct)) if punct.as_char() == '=')
}

/// Reduce one brace-language file, which here is TypeScript, C, C++, or CUDA.
///
/// The keyword list is the union over those four rather than one list each, because the cost of
/// calling a TypeScript variable named `struct` a keyword is nothing at all. Both sides of every
/// comparison pass through this same reader, so a coarse split still tells a copy from a body
/// that merely rhymes with it.
fn braces(document: &Document, alphabet: &mut Alphabet) -> Vec<(u32, u32)> {
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
    let mut tokens: Vec<(u32, u32)> = Vec::new();
    let mut line: u32 = 1;
    let mut at = 0;
    while at < source.len() {
        let opened = line;
        match source[at] {
            b'\n' => {
                line += 1;
                at += 1;
            }
            byte if byte.is_ascii_whitespace() => at += 1,
            b'/' if source.get(at + 1) == Some(&b'/') => {
                while at < source.len() && source[at] != b'\n' {
                    at += 1;
                }
            }
            b'/' if source.get(at + 1) == Some(&b'*') => {
                at += 2;
                while at < source.len()
                    && !(source[at] == b'*' && source.get(at + 1) == Some(&b'/'))
                {
                    line += u32::from(source[at] == b'\n');
                    at += 1;
                }
                at = source.len().min(at + 2);
            }
            quote @ (b'"' | b'\'' | b'`') => {
                at += 1;
                while at < source.len() && source[at] != quote {
                    line += u32::from(source[at] == b'\n');
                    at += 1 + usize::from(source[at] == b'\\');
                }
                at = source.len().min(at + 1);
                tokens.push((alphabet.id(TEXT), opened));
            }
            byte if byte.is_ascii_digit() => {
                while at < source.len() && is_number(source[at]) {
                    at += 1;
                }
                tokens.push((alphabet.id(NUMBER), opened));
            }
            byte if is_word(byte) => {
                let from = at;
                while at < source.len() && is_word(source[at]) {
                    at += 1;
                }
                let word = &document.source[from..at];
                let text = match word {
                    "true" | "false" => TRUTH,
                    "null" | "undefined" | "nullptr" | "NULL" => NOTHING,
                    _ if KEYWORDS.contains(&word) => word,
                    _ => IDENTIFIER,
                };
                tokens.push((alphabet.id(text), opened));
            }
            _ => {
                tokens.push((alphabet.id(&document.source[at..at + 1]), opened));
                at += 1;
            }
        }
    }
    tokens
}

/// Whether one byte can sit inside a name, counting the bytes a non-ASCII letter is written in.
fn is_word(byte: u8) -> bool {
    byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'$') || byte >= 0x80
}

/// Whether one byte can sit inside a numeric literal, including its base and digit separators.
fn is_number(byte: u8) -> bool {
    byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'\'')
}

#[cfg(test)]
mod tests {
    use super::*;

    fn document(relative: &str, source: &str) -> Document {
        Document {
            relative: relative.to_string(),
            source: source.to_string(),
        }
    }

    /// One body long enough to clear the window, written with whatever names it is given.
    fn body(name: &str, total: &str, item: &str) -> String {
        format!(
            "def {name}(rows, limit):\n    {total} = 0\n    for {item} in rows:\n        if \
             {item} > limit:\n            {total} = {total} + {item} * 2\n        else:\n          \
             {total} = {total} - 1\n    if {total} < 0:\n        return 0\n    return {total}\n"
        )
    }

    /// The same body again, written the way a brace language writes it.
    fn brace_body(name: &str, total: &str, item: &str) -> String {
        format!(
            "export function {name}(rows: Row[], limit: number): number {{\n  let {total} = 0;\n  \
             for (const {item} of rows) {{\n    if ({item}.value > limit) {{\n      {total} = \
             {total} + {item}.value * 2;\n    }} else {{\n      {total} = {total} - 1;\n    }}\n  \
             }}\n  if ({total} < 0) {{\n    return 0;\n  }}\n  return {total};\n}}\n"
        )
    }

    /// The same body once more, written the way Rust writes it.
    fn rust_body(name: &str, total: &str, item: &str) -> String {
        format!(
            "fn {name}(rows: &[Row], limit: i64) -> i64 {{\n    let mut {total} = 0;\n    for \
             {item} in rows {{\n        if {item}.value > limit {{\n            {total} = {total} \
             + {item}.value * 2;\n        }} else {{\n            {total} = {total} - 1;\n        \
             }}\n    }}\n    if {total} < 0 {{\n        return 0;\n    }}\n    {total}\n}}\n"
        )
    }

    fn paths(facts: &[Value]) -> Vec<Vec<String>> {
        facts
            .iter()
            .map(|fact| {
                fact["fragments"]
                    .as_array()
                    .expect("fragments")
                    .iter()
                    .map(|fragment| fragment["path"].as_str().unwrap_or_default().to_string())
                    .collect()
            })
            .collect()
    }

    #[test]
    fn a_copy_whose_locals_were_renamed_is_still_one_clone() {
        let facts = scan(&[
            document("left.py", &body("total_over", "total", "row")),
            document("right.py", &body("sum_above", "carried", "item")),
        ]);

        assert_eq!(paths(&facts), vec![vec!["left.py", "right.py"]]);
        assert_eq!(facts[0]["fragments"][0]["start_line"], 1);
        assert_eq!(facts[0]["fragments"][0]["end_line"], 10);
        assert_eq!(facts[0]["language"], "python");
    }

    #[test]
    fn two_bodies_that_do_different_work_are_never_one_clone() {
        let other = "def report(rows):\n    for row in rows:\n        print(row.name, row.value, \
                     row.owner, row.state, row.updated, row.created, row.id, row.kind)\n";

        let facts = scan(&[
            document("left.py", &body("total_over", "total", "row")),
            document("right.py", other),
        ]);

        assert!(facts.is_empty());
    }

    #[test]
    fn a_repeat_shorter_than_the_window_is_left_alone() {
        let short = "def add(left, right):\n    return left + right\n";

        assert!(scan(&[document("a.py", short), document("b.py", short)]).is_empty());
    }

    #[test]
    fn one_copied_run_is_reported_once_rather_than_once_per_window() {
        let source = body("total_over", "total", "row");
        let facts = scan(&[document("left.py", &source), document("right.py", &source)]);

        assert_eq!(facts.len(), 1);
        let length = facts[0]["token_length"].as_u64().expect("token length");
        assert!(
            length > WINDOW as u64,
            "{length} should have grown past {WINDOW}"
        );
    }

    #[test]
    fn a_third_copy_joins_the_group_it_belongs_to() {
        let source = body("total_over", "total", "row");
        let facts = scan(&[
            document("a.py", &source),
            document("b.py", &source),
            document("c.py", &source),
        ]);

        assert_eq!(paths(&facts), vec![vec!["a.py", "b.py", "c.py"]]);
        assert_eq!(facts[0]["repository_line_count"], 30);
    }

    #[test]
    fn a_typescript_copy_is_found_by_the_brace_reader() {
        let facts = scan(&[
            document("left.ts", &brace_body("totalOver", "total", "row")),
            document("right.ts", &brace_body("sumAbove", "carried", "item")),
        ]);

        assert_eq!(paths(&facts), vec![vec!["left.ts", "right.ts"]]);
        assert_eq!(facts[0]["language"], "typescript");
    }

    #[test]
    fn a_rust_copy_is_found_through_its_own_token_stream() {
        let facts = scan(&[
            document("left.rs", &rust_body("total_over", "total", "row")),
            document("right.rs", &rust_body("sum_above", "carried", "item")),
        ]);

        assert_eq!(paths(&facts), vec![vec!["left.rs", "right.rs"]]);
        assert_eq!(facts[0]["language"], "rust");
    }

    #[test]
    fn a_rust_doc_comment_never_makes_two_items_copies_of_each_other() {
        let commented = |explanation: &str| {
            format!(
                "/// {explanation}\n/// {explanation}\n/// {explanation}\n/// {explanation}\n/// \
                 {explanation}\n/// {explanation}\n/// {explanation}\n/// {explanation}\npub const \
                 LIMIT: i64 = 3;\n"
            )
        };

        let facts = scan(&[
            document("left.rs", &commented("one explanation")),
            document("right.rs", &commented("another explanation entirely")),
        ]);

        assert!(facts.is_empty());
    }

    #[test]
    fn a_comment_and_a_spacing_choice_never_decide_whether_two_bodies_are_copies() {
        let plain = body("total_over", "total", "row");
        let dressed = format!(
            "# an explanation the other copy never wrote down\n{}",
            body("total_over", "total", "row").replace(" = 0", "  =  0")
        );

        let facts = scan(&[document("left.py", &plain), document("right.py", &dressed)]);

        assert_eq!(paths(&facts), vec![vec!["left.py", "right.py"]]);
    }

    #[test]
    fn a_file_this_kernel_has_no_reader_for_is_skipped() {
        let facts = scan(&[
            document("notes.md", "the same sentence twice"),
            document("other.md", "the same sentence twice"),
        ]);

        assert!(facts.is_empty());
    }

    #[test]
    fn a_file_that_does_not_parse_contributes_nothing_rather_than_failing() {
        let broken = "def totals(:::\n";

        assert!(scan(&[document("a.py", broken), document("b.py", broken)]).is_empty());
        assert!(scan(&[document("a.rs", broken), document("b.rs", broken)]).is_empty());
    }

    #[test]
    fn the_brace_reader_drops_comments_and_flattens_every_literal() {
        let mut alphabet = Alphabet::default();
        let source = "/* gone\n   also gone */\nconst a = \"text\"; // gone\nconst b = 0x1f;\n\
                      const c = true;\nconst d = null;\n";

        let tokens = braces(&document("a.ts", source), &mut alphabet);
        let written: Vec<String> = tokens
            .iter()
            .map(|(symbol, _)| {
                alphabet
                    .ids
                    .iter()
                    .find(|(_, id)| *id == symbol)
                    .map(|(text, _)| text.clone())
                    .expect("interned")
            })
            .collect();

        assert_eq!(
            written,
            [
                "const", IDENTIFIER, "=", TEXT, ";", "const", IDENTIFIER, "=", NUMBER, ";",
                "const", IDENTIFIER, "=", TRUTH, ";", "const", IDENTIFIER, "=", NOTHING, ";",
            ]
        );
        assert_eq!(tokens[0].1, 3);
        assert_eq!(tokens[5].1, 4);
    }

    #[test]
    fn a_body_pasted_twice_into_one_file_is_a_clone_of_itself() {
        let twice = format!(
            "{}\n\ndef unrelated(rows):\n    return len(rows)\n\n\n{}",
            body("total_over", "total", "row"),
            body("sum_above", "carried", "item")
        );

        let facts = scan(&[document("a.py", &twice)]);

        assert_eq!(paths(&facts), vec![vec!["a.py", "a.py"]]);
        let fragments = facts[0]["fragments"].as_array().expect("fragments");
        let first = fragments[0]["end_line"].as_u64().expect("end");
        let second = fragments[1]["start_line"].as_u64().expect("start");
        assert!(second > first, "{second} overlaps a copy ending at {first}");
    }

    #[test]
    fn a_self_similar_run_never_reports_a_copy_that_overlaps_another() {
        let source = format!("def repeated():\n{}", "    run(a, b)\n".repeat(40));
        let facts = scan(&[document("a.py", &source)]);

        assert!(!facts.is_empty());
        for fact in &facts {
            let mut covered = 0;
            for fragment in fact["fragments"].as_array().expect("fragments") {
                let start = fragment["start_line"].as_u64().expect("start");
                assert!(
                    start > covered,
                    "{start} overlaps a copy ending at {covered}"
                );
                covered = fragment["end_line"].as_u64().expect("end");
            }
        }
    }

    #[test]
    fn matching_top_level_scaffolding_is_not_an_implementation_clone() {
        let values = (0..80)
            .map(|index| format!("name_{index}"))
            .collect::<Vec<_>>()
            .join(", ");
        let left = format!("VALUES = [{values}]\n");
        let right = format!("OPTIONS = [{values}]\n");

        assert!(scan(&[document("left.py", &left), document("right.py", &right)]).is_empty());
    }
}
