pub(super) trait QuotedText {
    fn quoted_line(&self, name: &str) -> Option<usize>;
}

impl QuotedText for str {
    fn quoted_line(&self, name: &str) -> Option<usize> {
        let needles = [
            format!("\"{name}\""),
            format!("'{name}'"),
            format!("`{name}`"),
        ];
        self.lines()
            .enumerate()
            .find(|(_, line)| needles.iter().any(|needle| line.contains(needle.as_str())))
            .map(|(index, _)| index + 1)
    }
}
