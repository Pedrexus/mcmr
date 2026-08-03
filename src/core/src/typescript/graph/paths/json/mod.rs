use jsonc_parser::ParseOptions;
use serde::de::DeserializeOwned;
use std::path::Path;

pub(super) fn read_config<Config: DeserializeOwned>(path: &Path) -> Result<Config, String> {
    let text = std::fs::read_to_string(path)
        .map_err(|failure| format!("{} could not be read: {failure}", path.display()))?;
    parse_config(&text)
        .map_err(|failure| format!("{} is not valid JSONC: {failure}", path.display()))
}

pub(in crate::typescript) fn parse_config<Config: DeserializeOwned>(
    text: &str,
) -> Result<Config, String> {
    let options = ParseOptions {
        allow_comments: true,
        allow_trailing_commas: true,
        allow_loose_object_property_names: false,
        allow_missing_commas: false,
        allow_single_quoted_strings: false,
        allow_hexadecimal_numbers: false,
        allow_unary_plus_numbers: false,
    };
    jsonc_parser::parse_to_serde_value(text, &options).map_err(|failure| failure.to_string())
}
