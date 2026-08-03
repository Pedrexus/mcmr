/// Return the command one declared task runs, however the manifest spells the declaration.
pub(super) fn commands_of(declared: &toml::Value) -> Vec<String> {
    let stated = ["run", "cmd"]
        .iter()
        .find_map(|key| declared.get(key))
        .or(Some(declared));
    match stated {
        Some(toml::Value::String(command)) => vec![command.clone()],
        Some(toml::Value::Array(parts)) => joined(parts, " ").into_iter().collect(),
        _ => depends_on(declared),
    }
}

fn depends_on(declared: &toml::Value) -> Vec<String> {
    ["depends", "depends-on", "depends_on"]
        .iter()
        .find_map(|key| declared.get(key))
        .and_then(toml::Value::as_array)
        .filter(|named| !named.is_empty())
        .and_then(|named| joined(named, " && ").map(|command| vec![command]))
        .unwrap_or_default()
}

fn joined(parts: &[toml::Value], separator: &str) -> Option<String> {
    parts
        .iter()
        .map(toml::Value::as_str)
        .collect::<Option<Vec<_>>>()
        .map(|words| words.join(separator))
}

/// Whether one command operates this checkout through the environment the manifest declares.
pub(super) fn stays_inside(command: &str) -> bool {
    const ELSEWHERE: &[&str] = &[
        "sudo", "doas", "su", "ssh", "scp", "apt", "apt-get", "brew", "dnf", "yum", "pacman",
        "apk", "choco", "winget", "snap", "curl", "wget",
    ];
    !heads(command)
        .any(|head| ELSEWHERE.contains(&head) || head.starts_with('/') || head.starts_with('~'))
        && !command.contains("$HOME")
        && !command.contains("~/")
}

/// Whether one command completes with nobody at the terminal.
pub(super) fn runs_unattended(command: &str) -> bool {
    const ATTENDED: &[&str] = &["vi", "vim", "nano", "emacs", "less", "more", "gdb", "lldb"];
    const SESSION: &[&str] = &["-it", "-ti", "--interactive", "--pdb", "--edit"];
    !heads(command).any(|head| ATTENDED.contains(&head))
        && !words(command).any(|word| SESSION.contains(&word))
}

/// Return the words one shell command states, with the operators that join them dropped.
fn words(command: &str) -> impl Iterator<Item = &str> {
    segments(command).flat_map(str::split_whitespace)
}

/// Return the program each part of one shell command runs.
fn heads(command: &str) -> impl Iterator<Item = &str> {
    segments(command).filter_map(|segment| segment.split_whitespace().next())
}

/// Split one command wherever a shell would start reading a new one.
fn segments(command: &str) -> impl Iterator<Item = &str> {
    command
        .split(['&', '|', ';', '\n'])
        .filter(|part| !part.is_empty())
}
