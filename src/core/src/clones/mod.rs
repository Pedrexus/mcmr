use crate::discovery::Document;
use serde_json::Value;
use std::collections::HashMap;

mod matching;
mod query_plans;
mod streams;
mod tokens;

use matching::{maximal, repeated};
use streams::Stream;
use tokens::Alphabet;

#[cfg(test)]
use streams::braces;
#[cfg(test)]
use tokens::{IDENTIFIER, NOTHING, NUMBER, TEXT, TRUTH, WINDOW};

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
    let sources: HashMap<&str, &str> = documents
        .iter()
        .map(|document| (document.relative.as_str(), document.source.as_str()))
        .collect();
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
        .map(|group| group.fact(&streams, repository_line_count, &sources))
        .collect()
}

#[cfg(test)]
mod tests;
