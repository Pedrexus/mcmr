use crate::source::Source;
use jiff::civil::{Date, date};
use ruff_python_ast::token::{TokenKind, Tokens};
use ruff_text_size::Ranged;
use serde_json::{Value, json};
use std::collections::BTreeMap;

/// Every suppression one file carries, with the metadata it justifies itself by.
///
/// A waiver justifies itself where it is written, in `field=value` pairs after the marker, so
/// `reason=`, `since=`, and `expires=` are read from the line that carries the suppression. A
/// waiver stating no date has an unknown age rather than a young one, which is the reading a rule
/// counting debt already relies on.
pub fn waivers(source: &Source, tokens: &Tokens) -> Value {
    let suppressions: Vec<Value> = tokens
        .iter()
        .filter(|token| token.kind() == TokenKind::Comment)
        .filter_map(|token| {
            let text = source.slice(token.range());
            let marker = [
                "# noqa",
                "# type: ignore",
                "# pyrefly: ignore",
                "# ty: ignore",
            ]
            .iter()
            .find(|marker| text.contains(**marker))?;
            let offset = text
                .find(*marker)
                .expect("the selected waiver marker must occur in its comment");
            let tail = text[offset + marker.len()..]
                .split('\n')
                .next()
                .expect("splitting a comment always yields its first line");
            let stated = waiver_metadata(tail);
            Some(json!({
                "location": format!(
                    "{}:{}",
                    source.relative,
                    source.line_of(token.range().start())
                ),
                "is_overly_broad": text.contains(&format!("{marker}\n"))
                    || text.ends_with(*marker),
                "age_days": stated.get("since").and_then(|held| days_since(held)),
                "expires_in_days": stated
                    .get("expires")
                    .and_then(|held| days_since(held).map(|days| -days)),
                "metadata": stated,
            }))
        })
        .collect();
    json!({"waivers": suppressions})
}

/// Return the `field=value` pairs one suppression states, each value running to the next field.
fn waiver_metadata(tail: &str) -> BTreeMap<String, String> {
    let mut found = BTreeMap::new();
    let mut field: Option<String> = None;
    let mut value = String::new();
    for token in tail.split_whitespace() {
        match token.split_once('=') {
            Some((name, first)) if !name.is_empty() && name.chars().all(char::is_alphabetic) => {
                if let Some(held) = field.take() {
                    found.insert(held, value.trim().to_string());
                }
                field = Some(name.to_string());
                value = first.to_string();
            }
            _ => {
                value.push(' ');
                value.push_str(token);
            }
        }
    }
    if let Some(held) = field {
        found.insert(held, value.trim().to_string());
    }
    found
}

/// Return how many days have passed since one written date, which is negative for a future one.
pub(super) fn days_since(written: &str) -> Option<i64> {
    let stated = civil_days(written)?;
    let today = i64::try_from(
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .ok()?
            .as_secs()
            / 86_400,
    )
    .ok()?;
    Some(today - stated)
}

/// Return how many days one valid `YYYY-MM-DD` date sits after the Unix epoch.
fn civil_days(written: &str) -> Option<i64> {
    let stated: Date = written.parse().ok()?;
    Some(stated.duration_since(date(1970, 1, 1)).as_hours() / 24)
}
