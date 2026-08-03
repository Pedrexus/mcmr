/// Text that may open with a word one language reserves for its tools.
pub trait CommentText {
    fn opens_with(&self, markers: &[&str]) -> bool;
}

/// Return what one comment says without the markers that made it a comment.
pub(super) fn body(text: &str) -> String {
    let Some(inner) = text.strip_prefix("/*") else {
        let opened = text.trim_start_matches('/');
        return opened
            .strip_prefix('!')
            .unwrap_or(opened)
            .trim()
            .to_string();
    };
    inner
        .trim_end_matches("*/")
        .lines()
        .map(|line| line.trim().trim_start_matches('*').trim_start())
        .collect::<Vec<_>>()
        .join("\n")
        .trim()
        .to_string()
}

impl CommentText for str {
    fn opens_with(&self, markers: &[&str]) -> bool {
        let lowered = self.to_ascii_lowercase();
        markers.iter().any(|marker| lowered.starts_with(marker))
    }
}
