/// Return the longest dotted package every one of these packages sits inside.
pub(in crate::classes) fn common_package(packages: &[&str]) -> String {
    let Some((first, rest)) = packages.split_first() else {
        return String::new();
    };
    let mut shared: Vec<&str> = first.split('.').collect();
    for package in rest {
        let held: Vec<&str> = package.split('.').collect();
        let kept = shared
            .iter()
            .zip(held.iter())
            .take_while(|(left, right)| left == right)
            .count();
        shared.truncate(kept);
    }
    shared.join(".")
}

/// Split one class name into the words its capitals separate.
pub(in crate::classes) fn camel_words(name: &str) -> Vec<String> {
    let mut words: Vec<String> = Vec::new();
    for character in name.chars() {
        if character.is_uppercase() || words.is_empty() {
            words.push(String::new());
        }
        if let Some(word) = words.last_mut() {
            word.push(character);
        }
    }
    words.into_iter().filter(|word| !word.is_empty()).collect()
}

/// Return the file name a class of this name would be given.
pub(in crate::classes) fn snake_case(name: &str) -> String {
    camel_words(name)
        .into_iter()
        .map(|word| word.to_lowercase())
        .collect::<Vec<_>>()
        .join("_")
}
