use crate::graph::{Language, Visibility};

pub(crate) fn dialect(language: Language) -> &'static str {
    match language {
        Language::C => "c",
        Language::Cuda => "cuda",
        _ => "cpp",
    }
}

pub(crate) fn visibility(reach: Visibility) -> &'static str {
    match reach {
        Visibility::Public => "public",
        Visibility::Protected => "protected",
        Visibility::Internal => "internal",
        Visibility::Private => "private",
    }
}

pub(crate) fn trim_include(written: &str) -> &str {
    written.trim_matches(|letter| matches!(letter, '"' | '<' | '>'))
}

/// Return one written name without the template arguments applied to it.
pub(crate) fn bare(written: &str) -> String {
    written
        .split_once('<')
        .map(|(name, _)| name)
        .unwrap_or(written)
        .trim()
        .to_string()
}

/// Whether one word in a type position qualifies a declaration rather than naming a type.
pub(crate) fn is_qualifier(written: &str) -> bool {
    const WORDS: &[&str] = &[
        "__device__",
        "__global__",
        "__host__",
        "__forceinline__",
        "__restrict__",
        "__shared__",
        "__constant__",
        "__managed__",
        "__launch_bounds__",
        "static",
        "extern",
        "inline",
        "const",
        "constexpr",
        "volatile",
        "mutable",
        "typename",
        "template",
    ];
    WORDS.contains(&written) || written.is_empty()
}
