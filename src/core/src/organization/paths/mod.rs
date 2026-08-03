pub(super) trait DirectoryPath {
    fn holds(&self, path: &str) -> bool;
    fn joined(&self, name: &str) -> String;
    fn branch_below<'a>(&self, path: &'a str) -> Option<&'a str>;
}

impl DirectoryPath for str {
    fn holds(&self, path: &str) -> bool {
        self.is_empty()
            || directory_of(path) == self
            || directory_of(path).starts_with(&format!("{self}/"))
    }

    fn joined(&self, name: &str) -> String {
        match self.is_empty() {
            true => name.to_string(),
            false => format!("{self}/{name}"),
        }
    }

    fn branch_below<'a>(&self, path: &'a str) -> Option<&'a str> {
        let inside = path
            .strip_prefix(self)
            .unwrap_or(path)
            .trim_start_matches('/');
        inside.split('/').next()
    }
}

pub(super) fn common_directory<'a>(paths: impl Iterator<Item = &'a str>) -> String {
    let mut paths = paths.map(directory_of);
    let Some(first) = paths.next() else {
        return String::new();
    };
    let mut shared = first.split('/').collect::<Vec<_>>();
    for path in paths {
        let parts = path.split('/').collect::<Vec<_>>();
        shared.truncate(
            shared
                .iter()
                .zip(parts.iter())
                .take_while(|(left, right)| left == right)
                .count(),
        );
    }
    shared.join("/")
}

pub(super) fn directory_of(path: &str) -> &str {
    path.rsplit_once('/').map(|(head, _)| head).unwrap_or("")
}

pub(super) fn enum_package_parent(path: &str) -> &str {
    let directory = directory_of(path);
    directory
        .split_once("/enums")
        .map(|(parent, _)| parent)
        .unwrap_or("")
}

pub(super) fn tail(name: &str) -> &str {
    name.rsplit('.').next().unwrap_or(name)
}
