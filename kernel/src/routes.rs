use crate::lexical::Corpus;
use serde::Serialize;
use serde_json::{Value, json};
use std::collections::BTreeSet;
use std::path::Path;

/// How far down a served surface is worth looking for, which is past the nesting a file-routed
/// framework reaches and short of the trees a build leaves behind.
const DEPTH: usize = 14;

/// One route a framework declares, and everywhere else in the repository that names its path.
#[derive(Clone, Debug, Serialize)]
pub struct Route {
    pub method: String,
    pub path: String,
    pub framework: String,
    pub declared_in: String,
    pub line: usize,
    pub is_prefix_composed: bool,
    pub references: Vec<Reference>,
}

/// One place that names the path of a route as a literal.
#[derive(Clone, Debug, Serialize)]
pub struct Reference {
    pub path: String,
    pub language: String,
    pub line: usize,
}

/// Find every route this repository declares and everything that names one.
///
/// A path has no general detector and looking for one is the mistake. FastAPI writes it in a
/// decorator, Express writes it in a call, Axum writes it in a builder, and SvelteKit does not
/// write it at all because the directory is the path. What generalizes is the route, not the
/// extraction, so each framework gets its own small reader and they all produce the same thing.
///
/// A reference is only claimed where the other side states the same path as a literal, which is
/// the rule the interop scan reaches for too, so both ask the corpus for it rather than each
/// spelling it out. That leaves a parameterized route unmatched, which is the honest answer:
/// `/users/{id}` and `/users/7` are not the same string and no lexical reader can prove they are
/// the same route.
pub fn scan(root: &Path, scope: &crate::discovery::Scope) -> Vec<Route> {
    let sources = Corpus::read(root, DEPTH, scope, |path| language_of(path) != "other");
    let mut routes: Vec<Route> = sources
        .files()
        .iter()
        .flat_map(|(path, text)| declared(path, text))
        .collect();
    for route in &mut routes {
        route.references = sources
            .mentions(&route.path, &route.declared_in)
            .map(|(path, line)| Reference {
                path: path.to_string(),
                language: language_of(path).to_string(),
                line,
            })
            .collect();
    }
    routes.sort_by(|left, right| {
        (&left.path, &left.method, &left.declared_in).cmp(&(
            &right.path,
            &right.method,
            &right.declared_in,
        ))
    });
    routes
}

/// Return every route one file declares, by the shape its own framework declares them in.
fn declared(path: &str, text: &str) -> Vec<Route> {
    if is_example(path) {
        return Vec::new();
    }
    let lines = code(text);
    let composed = states_prefix(text);
    let mut found = match language_of(path) {
        "python" => decorated(path, &lines),
        "typescript" => registered(path, &lines),
        "rust" => builder(path, &lines),
        _ => Vec::new(),
    };
    found.extend(conventional(path));
    for route in &mut found {
        route.is_prefix_composed = composed;
    }
    found
}

/// Whether one file states routes as illustrations rather than as a surface it actually serves.
fn is_example(path: &str) -> bool {
    let name = path.rsplit('/').next().unwrap_or(path);
    path.starts_with("tests/")
        || path.contains("/tests/")
        || name.starts_with("test_")
        || name.contains(".test.")
        || name.contains(".spec.")
}

/// Return the lines of one file that are code, each with the line number it had.
///
/// A route written in a docstring, a comment, or a test module is an example, and a reader tells
/// it from a declaration at a glance. A lexical adapter cannot, so everything that is not code is
/// dropped before any adapter sees it.
fn code(text: &str) -> Vec<(usize, &str)> {
    let body = text.split("#[cfg(test)]").next().unwrap_or(text);
    let mut quoted = false;
    let mut kept = Vec::new();
    for (index, line) in body.lines().enumerate() {
        let trimmed = line.trim();
        let opened = quoted;
        if (trimmed.matches("\"\"\"").count() + trimmed.matches("'''").count()) % 2 == 1 {
            quoted = !quoted;
        }
        // A leading hash is a comment in one language and an attribute in another, and the
        // bracket is what tells them apart.
        let commented = (trimmed.starts_with('#') && !trimmed.starts_with("#["))
            || trimmed.starts_with("//")
            || trimmed.starts_with('*')
            || trimmed.starts_with("/*");
        if opened || quoted || commented {
            continue;
        }
        kept.push((index + 1, line));
    }
    kept
}

/// The verbs a framework names a route with, which every one of them spells the same way.
const VERBS: &[&str] = &[
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "head",
    "options",
    "route",
    "websocket",
    "ws",
];

/// Read a decorated route, which is how FastAPI, Flask, and Starlette state one.
///
/// The decorator names the verb and the first literal names the path, so `@app.get("/users")` and
/// `@router.post("/users")` differ only in which object they hang from, and neither of those names
/// is worth reading.
fn decorated(path: &str, lines: &[(usize, &str)]) -> Vec<Route> {
    lines
        .iter()
        .filter_map(|(number, line)| {
            let trimmed = line.trim();
            let rest = trimmed.strip_prefix('@')?;
            let (_, called) = rest.split_once('.')?;
            let (verb, arguments) = called.split_once('(')?;
            if !VERBS.contains(&verb) {
                return None;
            }
            let stated = literal(arguments)?;
            Some(Route {
                method: verb.to_string(),
                path: stated,
                framework: "decorator".to_string(),
                declared_in: path.to_string(),
                line: *number,
                is_prefix_composed: false,
                references: Vec::new(),
            })
        })
        .collect()
}

/// Read a registered route, which is how Express, Hono, and Koa state one.
///
/// The call names the verb and passes the path first, and what separates it from a client request
/// written the same way is that a registration hands over a handler as well.
fn registered(path: &str, lines: &[(usize, &str)]) -> Vec<Route> {
    lines
        .iter()
        .filter_map(|(number, line)| {
            let (before, arguments) = line.split_once('(')?;
            let (_, verb) = before.rsplit_once('.')?;
            if !VERBS.contains(&verb.trim()) || !arguments.contains(',') {
                return None;
            }
            let stated = literal(arguments)?;
            Some(Route {
                method: verb.trim().to_string(),
                path: stated,
                framework: "registration".to_string(),
                declared_in: path.to_string(),
                line: *number,
                is_prefix_composed: false,
                references: Vec::new(),
            })
        })
        .collect()
}

/// Read a builder route, which is how Axum and the Actix macro state one.
///
/// Axum writes the path and the verb in one call, `route("/users", get(list))`, and Actix writes
/// the verb as the attribute and the path as its only argument.
fn builder(path: &str, lines: &[(usize, &str)]) -> Vec<Route> {
    lines
        .iter()
        .flat_map(|(number, line)| {
            let line_number = *number;
            let trimmed = line.trim();
            if let Some(rest) = trimmed.strip_prefix("#[")
                && let Some((verb, arguments)) = rest.split_once('(')
                && VERBS.contains(&verb)
                && let Some(stated) = literal(arguments)
            {
                return vec![Route {
                    method: verb.to_string(),
                    path: stated,
                    framework: "attribute".to_string(),
                    declared_in: path.to_string(),
                    line: line_number,
                    is_prefix_composed: false,
                    references: Vec::new(),
                }];
            }
            let Some((_, arguments)) = trimmed.split_once(".route(") else {
                return Vec::new();
            };
            let Some(stated) = literal(arguments) else {
                return Vec::new();
            };
            VERBS
                .iter()
                .filter(|verb| arguments.contains(&format!("{verb}(")))
                .map(|verb| Route {
                    method: (*verb).to_string(),
                    path: stated.clone(),
                    framework: "builder".to_string(),
                    declared_in: path.to_string(),
                    line: line_number,
                    is_prefix_composed: false,
                    references: Vec::new(),
                })
                .collect()
        })
        .collect()
}

/// Read a route the directory layout states, which is how SvelteKit and the Next app router do it.
///
/// There is nothing in the source to read here. The path is the directory the file sits in, with
/// the group and parameter spellings each convention uses turned back into the path they serve.
fn conventional(path: &str) -> Vec<Route> {
    let name = path.rsplit('/').next().unwrap_or_default();
    let anchor = match name {
        "+server.ts" | "+server.js" | "+page.svelte" | "+page.ts" => "routes",
        "route.ts" | "route.js" | "page.tsx" | "page.ts" => "app",
        _ => return Vec::new(),
    };
    let Some((_, inside)) = path.split_once(&format!("{anchor}/")) else {
        return Vec::new();
    };
    let mut segments: Vec<String> = Vec::new();
    for step in inside.split('/') {
        if step == name {
            break;
        }
        // A parenthesised segment groups files without serving a path, and a bracketed or
        // prefixed one is a parameter, which every convention writes its own way.
        if step.starts_with('(') {
            continue;
        }
        segments.push(match step.strip_prefix('[') {
            Some(rest) => format!("{{{}}}", rest.trim_end_matches(']')),
            None => step.to_string(),
        });
    }
    vec![Route {
        method: "any".to_string(),
        path: format!("/{}", segments.join("/")),
        framework: "convention".to_string(),
        declared_in: path.to_string(),
        line: 1,
        is_prefix_composed: false,
        references: Vec::new(),
    }]
}

/// Whether one file composes a prefix onto the routes it declares.
///
/// A router mounted under a prefix serves a path no line of it states, so the declared path is
/// only part of the answer and a rule that judged it as the whole answer would be wrong. Saying so
/// is what lets that rule decline instead.
fn states_prefix(text: &str) -> bool {
    [
        "prefix=",
        ".nest(",
        "app.use(",
        "include_router(",
        ".scope(",
        "url_prefix=",
    ]
    .iter()
    .any(|marker| text.contains(marker))
}

/// Return the first quoted path one argument list states, when it states one.
fn literal(arguments: &str) -> Option<String> {
    let opening = arguments.find(['"', '\'', '`'])?;
    let quote = arguments.as_bytes()[opening] as char;
    let rest = &arguments[opening + 1..];
    let closing = rest.find(quote)?;
    let stated = &rest[..closing];
    (stated.starts_with('/') && !stated.contains(' ')).then(|| stated.to_string())
}

/// Return which framework reader one file gets, since a path is written per language.
fn language_of(path: &str) -> &'static str {
    match path.rsplit('.').next().unwrap_or_default() {
        "py" => "python",
        "rs" => "rust",
        "ts" | "tsx" | "js" | "jsx" | "mjs" | "svelte" => "typescript",
        "go" => "go",
        _ => "other",
    }
}

/// Return every route as the one fact a rule reads, since every route question is repository-wide.
///
/// A duplicate, a route nothing reaches, and a path that disagrees with its neighbours are all
/// statements about the set rather than about any single route, so the set is what arrives and the
/// rule decides what it means.
pub fn facts(routes: &[Route]) -> Vec<Value> {
    let frameworks: BTreeSet<&str> = routes
        .iter()
        .map(|route| route.framework.as_str())
        .collect();
    vec![json!({
        "key": "routes",
        "span": {"path": ""},
        "frameworks": frameworks,
        "routes": routes,
    })]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_decorator_names_the_verb_and_the_path_it_serves() {
        let source = "@app.get(\"/users\")\nasync def list_users():\n    ...\n\n@router.post('/users/{id}')\nasync def create(id: int):\n    ...\n";

        let found = decorated("api/main.py", &code(source));

        assert_eq!(found.len(), 2);
        assert_eq!(found[0].method, "get");
        assert_eq!(found[0].path, "/users");
        assert_eq!(found[1].method, "post");
        assert_eq!(found[1].path, "/users/{id}");
    }

    #[test]
    fn a_registration_is_told_from_a_request_by_the_handler_it_hands_over() {
        let registration = "app.get('/health', (request, response) => response.send('ok'));\n";
        let request = "const data = await client.get('/health');\n";

        assert_eq!(registered("server.ts", &code(registration)).len(), 1);
        assert!(registered("client.ts", &code(request)).is_empty());
    }

    #[test]
    fn a_builder_and_an_attribute_both_name_the_route_they_add() {
        let axum =
            "let app = Router::new().route(\"/items\", get(list_items).post(create_item));\n";
        let actix = "#[get(\"/items\")]\nasync fn list_items() -> impl Responder {}\n";

        let built = builder("src/api.rs", &code(axum));
        assert_eq!(built.len(), 2);
        assert_eq!(built[0].path, "/items");
        assert_eq!(builder("src/handlers.rs", &code(actix))[0].method, "get");
    }

    #[test]
    fn a_directory_is_the_path_when_the_convention_says_it_is() {
        let sveltekit = conventional("src/routes/(app)/users/[id]/+server.ts");
        let next = conventional("app/api/users/[id]/route.ts");

        assert_eq!(sveltekit[0].path, "/users/{id}");
        assert_eq!(next[0].path, "/api/users/{id}");
        assert!(conventional("src/lib/helpers.ts").is_empty());
    }

    #[test]
    fn a_mounted_router_says_so_because_its_declared_path_is_not_the_whole_path() {
        let mounted = "router = APIRouter(prefix=\"/v1\")\n\n@router.get(\"/users\")\ndef read():\n    ...\n";

        assert!(declared("api/v1.py", mounted)[0].is_prefix_composed);
        assert!(
            !declared(
                "api/main.py",
                "@app.get(\"/users\")\ndef read():\n    ...\n"
            )[0]
            .is_prefix_composed
        );
    }

    #[test]
    fn only_a_quoted_path_counts_as_one() {
        assert_eq!(literal("\"/users\", handler").as_deref(), Some("/users"));
        assert_eq!(literal("'/a/b'").as_deref(), Some("/a/b"));
        assert_eq!(literal("path, handler"), None);
        assert_eq!(literal("\"users\""), None);
        assert_eq!(literal("\"/a b\""), None);
    }
}
