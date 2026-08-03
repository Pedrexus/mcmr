#[derive(Clone, Copy)]
pub(super) struct CommandLine<'command>(&'command str);

impl<'command> CommandLine<'command> {
    pub(super) fn new(command: &'command str) -> Self {
        Self(command)
    }

    pub(super) fn has_flag(self, wanted: &str) -> bool {
        self.0
            .split_whitespace()
            .any(|option| option == wanted || option.starts_with(&format!("{wanted}=")))
    }

    pub(super) fn option(self, wanted: &str) -> Option<String> {
        let words = self.0.split_whitespace().collect::<Vec<_>>();
        words.iter().enumerate().find_map(|(index, word)| {
            word.strip_prefix(&format!("{wanted}="))
                .map(str::to_string)
                .or_else(|| {
                    (*word == wanted)
                        .then(|| words.get(index + 1).map(|value| (*value).to_string()))
                        .flatten()
                })
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_longer_option_with_the_same_prefix_is_not_the_requested_flag() {
        let command = CommandLine::new("-q --cov-report=term --import-mode importlib");

        assert!(!command.has_flag("--cov"));
        assert_eq!(
            command.option("--import-mode").as_deref(),
            Some("importlib")
        );
    }
}
