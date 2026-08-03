use crate::source::Source;
use crate::walk::{docstring, walk};
use ruff_python_ast::{ModModule, Stmt};
use serde_json::{Value, json};

/// Everything one file states about itself as prose, from its own docstrings.
///
/// Each docstring is one coherent section. Combining unrelated declarations into one section
/// would manufacture a rhythm no reader encounters. A paragraph is what a blank line separates,
/// and every sentence contributes its own opener and length inside that section.
pub fn prose(source: &Source, module: &ModModule) -> Value {
    let documented = walk(module)
        .into_iter()
        .filter_map(|statement| match statement {
            Stmt::FunctionDef(item) => docstring(&item.body).map(|text| (statement, text)),
            Stmt::ClassDef(item) => docstring(&item.body).map(|text| (statement, text)),
            _ => None,
        })
        .collect::<Vec<_>>();
    let sections = documented
        .iter()
        .map(|(statement, text)| {
            let sentences = text
                .split(['.', '!', '?'])
                .filter_map(|sentence| {
                    let words = sentence.split_whitespace().collect::<Vec<_>>();
                    (!words.is_empty()).then(|| (words.len(), words[0].to_lowercase()))
                })
                .collect::<Vec<_>>();
            let paragraphs = text
                .split("\n\n")
                .map(|paragraph| paragraph.split_whitespace().count())
                .filter(|count| *count > 0)
                .collect::<Vec<_>>();
            json!({
                "text": text,
                "character_count": text.chars().count(),
                "token_count": text.split_whitespace().count(),
                "sentence_word_counts": sentences
                    .iter()
                    .map(|(count, _)| *count)
                    .collect::<Vec<_>>(),
                "paragraph_word_counts": paragraphs,
                "sentence_openers": sentences
                    .into_iter()
                    .map(|(_, opener)| opener)
                    .collect::<Vec<_>>(),
                "node": source.node_of("docstring", *statement),
            })
        })
        .collect::<Vec<_>>();
    json!({"sections": sections})
}
