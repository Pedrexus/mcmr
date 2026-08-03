/// Return the name of every kernel one CUDA source declares.
pub(crate) fn kernels(text: &str) -> impl Iterator<Item = String> {
    text.match_indices("__global__")
        .filter(|(position, _)| !is_commented(text, *position))
        .filter_map(|(position, marker)| declared_name(&text[position + marker.len()..]))
}

fn is_commented(text: &str, position: usize) -> bool {
    let before = &text[..position];
    let line = before.rsplit_once('\n').map_or(before, |(_, tail)| tail);
    if line.contains("//") {
        return true;
    }
    match (before.rfind("/*"), before.rfind("*/")) {
        (Some(opened), closed) => closed.is_none_or(|closed| closed < opened),
        _ => false,
    }
}

/// Return the name one declaration binds before its parameter list.
pub(crate) fn declared_name(rest: &str) -> Option<String> {
    DeclarationName::default().read(rest)
}

#[derive(Default)]
struct DeclarationName {
    named: String,
    word: String,
    held: String,
    depth: usize,
}

impl DeclarationName {
    fn accept_word_character(&mut self, letter: char) -> bool {
        if letter.is_alphanumeric() || letter == '_' {
            self.word.push(letter);
            true
        } else {
            false
        }
    }

    fn close(&mut self) -> Option<()> {
        self.depth = self.depth.checked_sub(1)?;
        if self.depth == 0 {
            self.named = std::mem::take(&mut self.held);
        }
        Some(())
    }

    fn finish_word(&mut self) {
        if !self.word.is_empty() {
            self.named = std::mem::take(&mut self.word);
        }
    }

    fn open(&mut self, letter: char) {
        if self.depth == 0 {
            self.held = match letter {
                '(' => String::new(),
                _ => self.named.clone(),
            };
        }
        self.depth += 1;
    }

    fn read(mut self, rest: &str) -> Option<String> {
        for letter in rest.chars() {
            if self.accept_word_character(letter) {
                continue;
            }
            self.finish_word();
            match letter {
                '(' if self.depth == 0 && self.named != "__launch_bounds__" => {
                    return (!self.named.is_empty()).then_some(self.named);
                }
                '(' | '<' | '[' => self.open(letter),
                ')' | '>' | ']' => self.close()?,
                ';' | '{' | '}' if self.depth == 0 => return None,
                _ => {}
            }
        }
        None
    }
}
