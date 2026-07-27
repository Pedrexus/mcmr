use crate::comments;
use crate::discovery::Document;
use crate::graph::{
    Edge, EdgeKind, Language, Node, NodeKind, ParameterKind, Reference, Resolution, Stated,
    Visibility, attach, identity, node, parameter, stray,
};
use crate::protocol::Stats;
use crate::source::Source;
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};
use tree_sitter::{Node as Syntax, Parser, Tree};

/// Build every requested fact family from one C, C++, or CUDA document.
///
/// These three are one frontend because they are one language with three dialects. A header
/// declares what a translation unit defines, a CUDA source is C++ with kernels added, and all
/// three link into one program where a name means one thing. What differs is small enough to be a
/// few branches: `static` is how C narrows a name, an access specifier is how C++ does it, and a
/// kernel is a function with an execution space written in front of it.
pub fn extract(document: &Document, facts: &mut BTreeMap<String, Vec<Value>>, stats: &mut Stats) {
    let language = Language::of(&document.relative).unwrap_or(Language::Cpp);
    let Some(tree) = parse(&document.source, &document.relative) else {
        stats.parse_failure_count += 1;
        return;
    };
    let unit = Unit {
        source: Source::new(&document.relative, &document.source),
        language,
    };
    let root = tree.root_node();
    if let Some(stream) = facts.get_mut("ModuleFact") {
        stream.push(unit.module_fact(root));
    }
    if let Some(stream) = facts.get_mut("ImportBindingFact") {
        stream.extend(unit.import_facts(root));
    }
    if let Some(stream) = facts.get_mut("FunctionFact") {
        stream.extend(unit.function_facts(root));
    }
    if let Some(stream) = facts.get_mut("ClassFact") {
        stream.push(unit.class_fact(root));
    }
    if let Some(stream) = facts.get_mut("CallFact") {
        stream.push(unit.call_fact(root));
    }
    if let Some(stream) = facts.get_mut("KernelLaunchFact") {
        stream.extend(unit.launch_facts(root));
    }
    if let Some(stream) = facts.get_mut("CommentFact") {
        stream.push(comments::fact(
            &unit.source,
            dialect(language),
            walk(root)
                .into_iter()
                .filter(|node| node.kind() == "comment")
                .map(|node| comments::at(node.start_byte(), node.end_byte())),
            &mut Notes::of(&document.relative),
        ));
    }
    if let Some(stream) = facts.get_mut("SyntaxFact") {
        stream.extend(unit.syntax_facts(root));
    }
}

/// What C, C++, and CUDA say about their own comments, past what the shared reader settles.
///
/// The parser is held across the whole document rather than built per comment, because deciding
/// whether a comment is code means parsing it and a header states hundreds of them.
struct Notes {
    parser: Parser,
}

impl Notes {
    fn of(relative: &str) -> Self {
        let mut parser = Parser::new();
        let _ = parser.set_language(&grammar(relative));
        Self { parser }
    }

    /// Whether one fragment is something this dialect would accept as written.
    fn compiles(&mut self, text: &str) -> bool {
        self.parser
            .parse(text, None)
            .is_some_and(|tree| !tree.root_node().has_error())
    }
}

impl comments::Dialect for Notes {
    /// Whether one comment addresses a tool rather than a reader.
    ///
    /// These are the switches the tools around the compiler read out of a comment, since the
    /// language itself has no way to state one. All of them open the comment they sit in.
    fn is_directive(&mut self, body: &str) -> bool {
        comments::opens_with(
            body,
            &[
                "nolint",
                "clang-format",
                "cppcheck-suppress",
                "iwyu pragma",
                "coverity",
                "lcov_excl",
                "codecov",
                "cspell",
                "nosonar",
            ],
        )
    }

    /// Whether one comment body is source this dialect would compile rather than prose.
    ///
    /// A function body is tried first and a translation unit second, because a commented-out
    /// statement is far and away the common case and settling it takes one parse. A declaration
    /// needs the second, since this language does not let one sit inside a body.
    ///
    /// Every statement this language has ends in a semicolon or opens a brace, so a note holding
    /// neither is prose and never reaches the parser at all.
    fn is_source(&mut self, body: &str) -> bool {
        comments::holds_code(body, &[';', '{'])
            && (self.compiles(&format!("void mcmr_probe() {{\n{body}\n}}")) || self.compiles(body))
    }
}

/// How far down a declaration's tree a syntax fact reaches, matching every other frontend.
const SYNTAX_DEPTH: usize = 6;

/// Whether this frontend reads one file, which is every dialect and every inline implementation.
///
/// A C++ template library keeps its bodies in `.inl`, `.ipp`, and `.tpp` rather than in a
/// translation unit, and those are exactly the files a rule about a function body has to read.
/// Leaving them out hid 26 files and 18 percent of the lines of one header-only library. The
/// graph's language map names the six languages that carry node identity and knows none of them,
/// so the frontend states which suffixes its own grammars accept.
pub fn reads(relative: &str) -> bool {
    matches!(
        relative.rsplit('.').next().unwrap_or_default(),
        "c" | "h"
            | "cc"
            | "cpp"
            | "cxx"
            | "hpp"
            | "hh"
            | "hxx"
            | "inl"
            | "ipp"
            | "tpp"
            | "cu"
            | "cuh"
    )
}

/// Parse one translation unit with the grammar its own dialect is written in.
///
/// CUDA is the one that matters. Its grammar extends the C++ one with the execution space
/// qualifiers and the launch bracket, so `__global__`, `__shared__`, and
/// `kernel<<<grid, block>>>(...)` arrive as real nodes rather than as syntax the parser recovered
/// around, which is the difference between reading a launch and guessing at one.
///
/// A `.h` is read as C++ whatever its project calls itself. A header cannot say which of the two
/// languages wrote it, and the C++ grammar reads a C header correctly while the C grammar reads a
/// class as an error.
fn parse(text: &str, relative: &str) -> Option<Tree> {
    let mut parser = Parser::new();
    parser.set_language(&grammar(relative)).ok()?;
    parser.parse(text, None)
}

/// Return the grammar one file's own dialect is written in.
fn grammar(relative: &str) -> tree_sitter::Language {
    match relative.rsplit('.').next().unwrap_or_default() {
        "cu" | "cuh" => tree_sitter_cuda::LANGUAGE.into(),
        "c" => tree_sitter_c::LANGUAGE.into(),
        _ => tree_sitter_cpp::LANGUAGE.into(),
    }
}

/// One translation unit and everything the fact families read out of it.
struct Unit {
    source: Source,
    language: Language,
}

impl Unit {
    fn text(&self, node: Syntax) -> &str {
        self.source
            .text
            .get(node.byte_range())
            .unwrap_or_default()
            .trim()
    }

    fn locate(&self, node: Syntax) -> Value {
        let (start, end) = (node.start_position(), node.end_position());
        json!({
            "path": self.source.relative,
            "start_line": start.row + 1,
            "start_column": start.column,
            "end_line": end.row + 1,
            "end_column": end.column,
        })
    }

    fn base(&self, key: &str, node: Syntax) -> Value {
        json!({
            "key": key,
            "span": self.locate(node),
            "language": dialect(self.language),
        })
    }

    fn module_fact(&self, root: Syntax) -> Value {
        let declared = declarations(root);
        merge(
            self.base(&format!("module:{}", self.source.relative), root),
            json!({
                "physical_line_count": self.source.text.lines().count(),
                "class_count": declared.iter().filter(|node| is_type(**node)).count(),
                "function_count": declared
                    .iter()
                    .filter(|node| node.kind() == "function_definition")
                    .count(),
                "is_package_initializer": false,
                "members": declared
                    .iter()
                    .filter_map(|node| self.declared_name(*node))
                    .map(|name| json!({"name": name, "responsibility": ""}))
                    .collect::<Vec<_>>(),
            }),
        )
    }

    /// Return the name one declaration states, whichever shape it states it in.
    fn declared_name(&self, node: Syntax) -> Option<String> {
        if is_type(node) {
            return child(node, "type_identifier").map(|name| self.text(name).to_string());
        }
        self.declarator_name(node.child_by_field_name("declarator")?)
    }

    /// Return the name one declarator finally binds, past every wrapper this language puts on it.
    ///
    /// A declaration here wraps its name in whatever it is being declared as, so a pointer to an
    /// array of functions buries the identifier several layers down and the only way to the name
    /// is to keep opening the wrapper.
    fn declarator_name(&self, node: Syntax) -> Option<String> {
        if is_name(node) {
            return Some(self.text(node).to_string());
        }
        self.declarator_name(wrapped(node)?)
    }

    fn import_facts(&self, root: Syntax) -> Vec<Value> {
        walk(root)
            .into_iter()
            .filter(|node| node.kind() == "preproc_include")
            .filter_map(|node| {
                let path = node.child_by_field_name("path")?;
                let owned = path.kind() == "string_literal";
                let named = trim_include(self.text(path));
                let bound = named.rsplit('/').next().unwrap_or(named).to_string();
                Some(merge(
                    self.base(&format!("import:{}:{named}", self.source.relative), node),
                    json!({
                        "name": bound,
                        "module": named,
                        "importer_module": self.source.relative.clone(),
                        "reference_count": self.source.text.matches(named).count().saturating_sub(1),
                        "has_qualifying_use": true,
                        "is_relative": owned,
                        "is_project_owned": owned,
                        "is_external": !owned,
                    }),
                ))
            })
            .collect()
    }

    fn function_facts(&self, root: Syntax) -> Vec<Value> {
        walk(root)
            .into_iter()
            .filter(|node| node.kind() == "function_definition")
            .filter_map(|node| {
                let declarator = node.child_by_field_name("declarator")?;
                let name = self.declarator_name(declarator)?;
                let held = enclosing_type(node).is_some() || name.contains("::");
                let lines = node.end_position().row - node.start_position().row + 1;
                let increments = node
                    .child_by_field_name("body")
                    .map(control_increments)
                    .unwrap_or_default();
                Some(merge(
                    self.base(&format!("function:{}:{name}", self.source.relative), node),
                    json!({
                        "name": name,
                        "scope": if held { "method" } else { "module" },
                        "visibility": visibility(self.reach(node)),
                        "is_async": false,
                        "implementation_lines": lines,
                        "direct_statement_count": node
                            .child_by_field_name("body")
                            .map_or(0, |body| body.named_child_count()),
                        "conditional_count": increments
                            .iter()
                            .filter(|value| value["kind"] == "conditional")
                            .count(),
                        "control_increments": increments,
                        "parameters": self.parameters(declarator),
                    }),
                ))
            })
            .collect()
    }

    /// Return every position one signature declares, in the order a caller fills them.
    ///
    /// A position a caller may leave out is still a position, so the list holds it and says a
    /// caller need not fill it. Dropping it instead would close the gap between two parameters
    /// that are not adjacent and make a rule about transposable neighbours compare a pair no
    /// caller ever writes side by side.
    fn parameters(&self, declarator: Syntax) -> Vec<Value> {
        let Some(list) = descendant(declarator, "parameter_list") else {
            return Vec::new();
        };
        children(list)
            .into_iter()
            .filter_map(native_parameter)
            .map(|(node, _, has_default)| {
                json!({
                    "name": node
                        .child_by_field_name("declarator")
                        .and_then(|inner| self.declarator_name(inner))
                        .unwrap_or_default(),
                    "type_name": self.declared_type(node),
                    "is_required_by_external_contract": !has_default,
                })
            })
            .collect()
    }

    /// Return the type one parameter declares, as the caller filling that position sees it.
    ///
    /// Half of a type in this language sits in the declarator rather than in the type the
    /// declaration names, so `int32_t *__restrict__ tokens` and `int32_t seg_start` write the same
    /// word and share no type at all. Reading the named type alone makes a rule about
    /// interchangeable positions report a pointer beside a value, which no caller could transpose
    /// and no compiler would accept.
    ///
    /// A qualifier written at the level that binds the name is the one a caller never sees. `int
    /// *const` and `int *` accept the same argument, a by-value `const int` is an undertaking by
    /// the body rather than a demand on the caller, and `__restrict__` promises the callee
    /// something about aliasing. Every other qualifier reaches the value being handed over, so
    /// `const int32_t *` stays apart from `int32_t *` the way a compiler keeps them apart.
    fn declared_type(&self, node: Syntax) -> String {
        let Some(stated) = node.child_by_field_name("type") else {
            return String::new();
        };
        let bound = binding_level(node);
        let mut written = self.visible_qualifiers(node, bound);
        written.push(self.text(stated).to_string());
        let mut level = wrapped(node);
        while let Some(held) = level {
            if let Some(mark) = self.shape(held) {
                written.push(mark);
                written.extend(self.visible_qualifiers(held, bound));
            }
            level = wrapped(held);
        }
        written.join(" ")
    }

    /// Return the qualifiers one declarator level states that a caller of the signature can see.
    fn visible_qualifiers(&self, level: Syntax, bound: Syntax) -> Vec<String> {
        if level == bound {
            return Vec::new();
        }
        children(level)
            .into_iter()
            .filter(|held| held.kind() == "type_qualifier")
            .map(|held| self.text(held).to_string())
            .collect()
    }

    /// Return what one declarator level adds to the type it wraps, as this language writes it.
    ///
    /// An array keeps its extent and a function keeps its parameter list, because `int (&)[4]` and
    /// `int (&)[8]` are two types and so are two callbacks that differ only in what they take.
    fn shape(&self, level: Syntax) -> Option<String> {
        match level.kind() {
            "pointer_declarator" => Some("*".to_string()),
            "reference_declarator" => Some(self.text(level.child(0)?).to_string()),
            "variadic_declarator" => Some("...".to_string()),
            "array_declarator" => Some(format!(
                "[{}]",
                level
                    .child_by_field_name("size")
                    .map(|size| self.text(size))
                    .unwrap_or_default()
            )),
            "function_declarator" => level
                .child_by_field_name("parameters")
                .map(|list| self.text(list).to_string()),
            _ => None,
        }
    }

    /// Return how widely one declaration reaches, by the way this language family states it.
    ///
    /// C narrows a name with `static` or an anonymous namespace, and C++ adds an access specifier
    /// that governs every member after it until the next one. Both are the same idea written in
    /// two places, and both land on the four levels every frontend fills.
    fn reach(&self, node: Syntax) -> Visibility {
        if let Some(holder) = enclosing_type(node) {
            return self.member_reach(holder, node);
        }
        if self.text(node).starts_with("static ") || in_anonymous_namespace(node) {
            return Visibility::Internal;
        }
        Visibility::Public
    }

    /// Return the access one member inherits from the specifier that most recently preceded it.
    fn member_reach(&self, holder: Syntax, member: Syntax) -> Visibility {
        let opening = holder.child(0).map(|keyword| self.text(keyword));
        let mut reach = match opening {
            Some("class") => Visibility::Private,
            _ => Visibility::Public,
        };
        let Some(body) = descendant(holder, "field_declaration_list") else {
            return reach;
        };
        for child in children(body) {
            if child.start_byte() > member.start_byte() {
                break;
            }
            if child.kind() == "access_specifier" {
                reach = match self.text(child).trim_end_matches(':').trim() {
                    "private" => Visibility::Private,
                    "protected" => Visibility::Protected,
                    _ => Visibility::Public,
                };
            }
        }
        reach
    }

    fn class_fact(&self, root: Syntax) -> Value {
        let classes: Vec<Value> = walk(root)
            .into_iter()
            .filter(|node| is_type(*node))
            .filter_map(|node| {
                let name =
                    child(node, "type_identifier").map(|item| self.text(item).to_string())?;
                let members = descendant(node, "field_declaration_list");
                Some(json!({
                    "name": name,
                    "path": self.source.relative.clone(),
                    "span": self.locate(node),
                    "scope": "module",
                    "visibility": visibility(self.reach(node)),
                    "direct_bases": self.bases(node),
                    "methods": members.map(|body| self.methods(node, body)).unwrap_or_default(),
                    "field_count": members.map_or(0, |body| {
                        children(body)
                            .into_iter()
                            .filter(|member| {
                                member.kind() == "field_declaration"
                                    && descendant(*member, "function_declarator").is_none()
                            })
                            .count()
                    }),
                }))
            })
            .collect();
        merge(
            self.base(&format!("classes:{}", self.source.relative), root),
            json!({"classes": classes}),
        )
    }

    fn bases(&self, node: Syntax) -> Vec<String> {
        let Some(clause) = child(node, "base_class_clause") else {
            return Vec::new();
        };
        children(clause)
            .into_iter()
            .filter(|item| is_name(*item))
            .map(|item| self.text(item).to_string())
            .collect()
    }

    fn methods(&self, holder: Syntax, body: Syntax) -> Vec<Value> {
        children(body)
            .into_iter()
            .filter(|member| {
                matches!(
                    member.kind(),
                    "field_declaration" | "function_definition" | "declaration"
                )
            })
            .filter_map(|member| {
                let declarator = descendant(member, "function_declarator")?;
                let name = self.declarator_name(declarator)?;
                let holder_name = child(holder, "type_identifier").map(|item| self.text(item));
                Some(json!({
                    "name": name.clone(),
                    "kind": if Some(name.as_str()) == holder_name {
                        "constructor"
                    } else if name.starts_with('~') {
                        "destructor"
                    } else if self.text(member).starts_with("static ") {
                        "static_method"
                    } else {
                        "method"
                    },
                    "visibility": visibility(self.member_reach(holder, member)),
                }))
            })
            .collect()
    }

    fn call_fact(&self, root: Syntax) -> Value {
        let calls: Vec<Value> = walk(root)
            .into_iter()
            .filter(|node| node.kind() == "call_expression")
            .filter_map(|node| {
                let function = node.child_by_field_name("function")?;
                Some(json!({
                    "qualified_name": self.callee(function),
                    "path": self.source.relative.clone(),
                    "result_is_discarded": node
                        .parent()
                        .is_some_and(|parent| parent.kind() == "expression_statement"),
                }))
            })
            .collect();
        merge(
            self.base(&format!("callfact:{}", self.source.relative), root),
            json!({"calls": calls, "module_bindings": []}),
        )
    }

    /// Return every kernel launch this translation unit states, with the configuration it sets.
    ///
    /// A launch carries four things between its brackets and only the first two are required, so
    /// the two that are usually left out are exactly the two worth reporting: a launch with no
    /// stream runs on the default stream and serializes against everything, and one with no
    /// dynamic shared memory that a kernel expects is a silent misconfiguration.
    fn launch_facts(&self, root: Syntax) -> Vec<Value> {
        let held = walk(root);
        let streamed = held.iter().any(|node| self.names_a_stream(*node));
        held.iter()
            .filter(|node| node.kind() == "call_expression")
            .filter_map(|node| {
                let configuration = child(*node, "kernel_call_syntax")?;
                let function = node.child_by_field_name("function")?;
                let arguments: Vec<&str> = children(configuration)
                    .into_iter()
                    .map(|item| self.text(item))
                    .collect();
                Some(merge(
                    self.base(
                        &format!("launch:{}:{}", self.source.relative, self.text(function)),
                        *node,
                    ),
                    json!({
                        "kernel": self.text(function),
                        "grid": arguments.first().copied().unwrap_or_default(),
                        "block": arguments.get(1).copied().unwrap_or_default(),
                        "dynamic_shared_bytes": arguments.get(2).copied().unwrap_or_default(),
                        "stream": arguments.get(3).copied().unwrap_or_default(),
                        "enclosing_function": self.enclosing_name(*node),
                        "unit_uses_streams": streamed,
                    }),
                ))
            })
            .collect()
    }

    /// Whether one written name is a stream this unit creates, is handed, or waits on.
    ///
    /// A launch that takes the default stream costs nothing where no other stream exists to
    /// serialize against, and only the whole translation unit can answer that. Being handed a
    /// stream counts as much as creating one, since a function that receives a `cudaStream_t` and
    /// launches without it drains exactly the overlap its caller set up.
    fn names_a_stream(&self, node: Syntax) -> bool {
        if !matches!(
            node.kind(),
            "identifier" | "type_identifier" | "qualified_identifier"
        ) {
            return false;
        }
        let written = self.text(node);
        written.starts_with("cudaStream") || written.ends_with("stream_ref")
    }

    /// Return the name of the function one node sits inside, when it sits inside one.
    fn enclosing_name(&self, node: Syntax) -> String {
        let mut walker = node.parent();
        while let Some(found) = walker {
            if found.kind() == "function_definition"
                && let Some(declarator) = found.child_by_field_name("declarator")
                && let Some(named) = self.declarator_name(declarator)
            {
                return named;
            }
            walker = found.parent();
        }
        String::new()
    }

    /// Return the name one call reaches for, which is the whole path when it goes through a
    /// receiver.
    ///
    /// A member call names its receiver as much as its member, and dropping the receiver leaves
    /// `state.exec` reading as the bare `exec` that several languages spell a scope builtin with.
    /// Every general rule matching a builtin by name then answers yes for any object holding a
    /// method of that name. The reference frontend keeps the path, so this one does too, and a
    /// receiver no lexical reader can name leaves the call unnamed rather than named after its
    /// member alone.
    fn callee(&self, function: Syntax) -> String {
        match function.kind() {
            "field_expression" => {
                let Some(field) = function.child_by_field_name("field") else {
                    return String::new();
                };
                let reached = function
                    .child_by_field_name("argument")
                    .map(|receiver| self.callee(receiver))
                    .unwrap_or_default();
                match reached.is_empty() {
                    true => String::new(),
                    false => format!("{reached}.{}", self.text(field)),
                }
            }
            // A call reached through another call names the callable that produced it, which is
            // the same reduction the reference frontend performs on the same shape.
            "call_expression" => function
                .child_by_field_name("function")
                .map(|inner| self.callee(inner))
                .unwrap_or_default(),
            _ => self.text(function).to_string(),
        }
    }

    /// Every declaration this translation unit states, each with its source and its tree.
    ///
    /// The kinds are the shared vocabulary rather than this grammar's own, so a rule written
    /// against a Python declaration reads a C++ one without learning what a
    /// `field_declaration_list` is. A namespace and a type qualify what they hold, which is what
    /// makes a method named for the type that declares it.
    fn syntax_facts(&self, root: Syntax) -> Vec<Value> {
        let mut facts = Vec::new();
        self.declared(root, "", &mut facts);
        facts
    }

    fn declared(&self, node: Syntax, owner: &str, facts: &mut Vec<Value>) {
        for held in children(node) {
            if is_type(held) {
                let Some(named) = child(held, "type_identifier") else {
                    continue;
                };
                let qualname = qualify(owner, self.text(named));
                facts.push(self.declaration(held, &qualname, "type"));
                if let Some(body) = descendant(held, "field_declaration_list") {
                    self.declared(body, &qualname, facts);
                }
                continue;
            }
            match held.kind() {
                "function_definition" => {
                    if let Some(named) = self.declared_name(held) {
                        facts.push(self.declaration(held, &qualify(owner, &named), "callable"));
                    }
                }
                "namespace_definition" => {
                    let named = held
                        .child_by_field_name("name")
                        .map(|name| self.text(name).to_string())
                        .unwrap_or_default();
                    if let Some(body) = held.child_by_field_name("body") {
                        self.declared(body, &qualify(owner, &named), facts);
                    }
                }
                "linkage_specification"
                | "template_declaration"
                | "declaration_list"
                | "field_declaration_list"
                | "preproc_ifdef"
                | "preproc_if" => {
                    self.declared(held, owner, facts);
                }
                _ => {}
            }
        }
    }

    fn declaration(&self, node: Syntax, qualname: &str, kind: &str) -> Value {
        let tree = json!({
            "kind": crate::syntax::known(kind),
            "name": qualname.rsplit("::").next().unwrap_or(qualname),
            "text": self.text(node),
            "span": self.locate(node),
            "children": self.contents(node, SYNTAX_DEPTH),
        });
        crate::syntax::fact(
            &self.source,
            dialect(self.language),
            qualname,
            tree,
            self.locate(node),
        )
    }

    /// Return what one declaration holds, which is the type it states and the body it opens.
    ///
    /// Parameters are deliberately left out. Every frontend carries them in `FunctionFact`
    /// already, and no other one puts them in the tree, so listing them here would make a rule
    /// about local names answer differently for this language than for any other.
    fn contents(&self, node: Syntax, depth: usize) -> Vec<Value> {
        let mut found: Vec<Value> = node
            .child_by_field_name("type")
            .filter(|stated| !is_type(*stated))
            .map(|stated| self.branch(stated, 0))
            .into_iter()
            .collect();
        if let Some(body) = node.child_by_field_name("body") {
            found.extend(self.spliced(body, depth));
        }
        found
    }

    fn branch(&self, node: Syntax, depth: usize) -> Value {
        let at = located(node);
        json!({
            "kind": crate::syntax::known(kind_of(node)),
            "name": self.stated_name(node),
            "text": self.text(at),
            "span": self.locate(at),
            "children": match depth {
                0 => Vec::new(),
                _ => self.spliced(node, depth),
            },
        })
    }

    /// Return the nodes one node contributes, walking through the wrappers that carry no meaning.
    fn spliced(&self, node: Syntax, depth: usize) -> Vec<Value> {
        let restated = named_by(node);
        let mut found = Vec::new();
        for held in children(node) {
            if held.kind() == "comment" {
                // A comment sits anywhere a token does and the grammar hands it over as a child.
                // It is what the comment family reads, and code is what this tree states.
                continue;
            }
            if is_transparent(held) {
                found.extend(self.spliced(held, depth));
            } else if restated == Some(held) {
                continue;
            } else if is_declaration(held) {
                // A nested declaration carries its own fact, so its body stops here. Walking into
                // it would count every defect inside a method twice, once for the method and
                // again for the type that holds it.
                found.push(self.branch(held, 0));
            } else {
                found.push(self.branch(held, depth - 1));
            }
        }
        found
    }

    /// Return the name one piece of syntax states, when it states one.
    fn stated_name(&self, node: Syntax) -> String {
        if is_type(node) || is_name(node) {
            return child(node, "type_identifier")
                .map(|named| self.text(named))
                .unwrap_or_else(|| self.text(node))
                .to_string();
        }
        match node.kind() {
            "function_definition"
            | "declaration"
            | "field_declaration"
            | "parameter_declaration"
            | "init_declarator" => self
                .declared_name(node)
                .or_else(|| self.declarator_name(node.child_by_field_name("declarator")?))
                .unwrap_or_default(),
            "call_expression" | "new_expression" => node
                .child_by_field_name("function")
                .or_else(|| node.child_by_field_name("type"))
                .map(|function| self.callee(function))
                .unwrap_or_default(),
            "field_expression" => node
                .child_by_field_name("field")
                .map(|field| self.text(field).to_string())
                .unwrap_or_default(),
            "assignment_expression" | "expression_statement" => self.assigned(node),
            "primitive_type" | "sized_type_specifier" | "namespace_identifier" => {
                self.text(node).to_string()
            }
            _ => String::new(),
        }
    }

    /// Return the name one statement assigns to, looking through the statement that wraps it.
    fn assigned(&self, node: Syntax) -> String {
        let stated = match node.kind() {
            "expression_statement" => child(node, "assignment_expression"),
            _ => Some(node),
        };
        stated
            .and_then(|held| held.child_by_field_name("left"))
            .map(|left| self.text(left).to_string())
            .unwrap_or_default()
    }
}

/// Return the repository-wide name one written name carries inside the scope holding it.
fn qualify(owner: &str, named: &str) -> String {
    match owner.is_empty() {
        true => named.to_string(),
        false => format!("{owner}::{named}"),
    }
}

/// What one node in a declaration's own tree is, in terms every language shares.
///
/// This is deliberately not a parse tree. A rule reading it asks what a body binds, what it calls,
/// and what it writes down, and this grammar buries all three under the shapes it needs to parse
/// C++. Anything the language adds beyond the shared kinds arrives as children rather than as a
/// kind nobody else has.
fn kind_of(node: Syntax) -> &'static str {
    if is_type(node) {
        return "type";
    }
    match node.kind() {
        "function_definition" | "lambda_expression" => "callable",
        // A member whose declarator is a function states a method rather than a field, and the
        // rules that read the two read them for opposite reasons.
        "declaration" | "field_declaration" | "parameter_declaration" => {
            match descendant(node, "function_declarator") {
                Some(_) => "callable",
                None => "binding",
            }
        }
        "assignment_expression" | "init_declarator" => "binding",
        "return_statement" | "co_return_statement" => "return",
        "if_statement" | "switch_statement" | "case_statement" | "conditional_expression" => {
            "branch"
        }
        "for_statement" | "for_range_loop" | "while_statement" | "do_statement" => "loop",
        "try_statement" => "guard",
        "throw_statement" => "raise",
        "preproc_include" | "using_declaration" | "namespace_alias_definition" => "import",
        "expression_statement" => "effect",
        "call_expression" | "new_expression" => "call",
        "identifier"
        | "qualified_identifier"
        | "type_identifier"
        | "field_identifier"
        | "namespace_identifier"
        | "primitive_type"
        | "sized_type_specifier" => "name",
        "field_expression" => "member",
        "string_literal" | "raw_string_literal" | "concatenated_string" | "char_literal" => "text",
        "number_literal" | "true" | "false" | "null" | "nullptr" => "literal",
        "initializer_list" => "collection",
        "binary_expression" | "unary_expression" | "update_expression" | "pointer_expression" => {
            "operation"
        }
        "subscript_expression" => "index",
        "co_await_expression" => "await",
        "compound_statement" => "scope",
        _ => "statement",
    }
}

/// Whether one node carries no meaning of its own and hands its children to whatever holds it.
///
/// A grammar names every shape it needs to parse, and several of those exist only to group: the
/// block a body opens, the list an argument sits in, the parentheses around an expression, and the
/// clause a catch or an else introduces. A rule asks what a body does rather than which brackets
/// it used, so these contribute their children in place and cost the tree no depth.
fn is_transparent(node: Syntax) -> bool {
    match node.kind() {
        // A statement that assigns is the binding it holds rather than a wrapper around one, so
        // it steps aside and lets the assignment be what the tree states.
        "expression_statement" => child(node, "assignment_expression").is_some(),
        "compound_statement"
        | "declaration_list"
        | "argument_list"
        | "parameter_list"
        | "subscript_argument_list"
        | "parenthesized_expression"
        | "condition_clause"
        | "init_declarator"
        | "else_clause"
        | "catch_clause"
        | "template_declaration"
        | "linkage_specification"
        | "attributed_statement"
        | "kernel_call_syntax" => true,
        _ => false,
    }
}

/// Whether one node is a declaration that carries a fact of its own.
fn is_declaration(node: Syntax) -> bool {
    is_type(node) || node.kind() == "function_definition"
}

/// Return the child one node takes its own name from, which the tree never repeats beneath it.
fn named_by(node: Syntax<'_>) -> Option<Syntax<'_>> {
    match node.kind() {
        "assignment_expression" => node.child_by_field_name("left"),
        "declaration" | "field_declaration" | "parameter_declaration" | "init_declarator" => {
            node.child_by_field_name("declarator")
        }
        _ => None,
    }
}

/// Return the node one statement is located at, which drops the punctuation that ends it.
///
/// A statement here ends in a semicolon where the expression it holds does not, and the rule
/// asking whether a statement produced only a value finds it by matching the child that covers
/// the whole statement. Locating an effect at its expression is what makes that match, and the
/// semicolon is punctuation rather than content.
fn located(node: Syntax<'_>) -> Syntax<'_> {
    match node.kind() {
        "expression_statement" => children(node).into_iter().next().unwrap_or(node),
        _ => node,
    }
}

fn dialect(language: Language) -> &'static str {
    match language {
        Language::C => "c",
        Language::Cuda => "cuda",
        _ => "cpp",
    }
}

fn visibility(reach: Visibility) -> &'static str {
    match reach {
        Visibility::Public => "public",
        Visibility::Protected => "protected",
        Visibility::Internal => "internal",
        Visibility::Private => "private",
    }
}

fn merge(mut left: Value, right: Value) -> Value {
    if let (Some(target), Some(extra)) = (left.as_object_mut(), right.as_object()) {
        for (name, value) in extra {
            target.insert(name.clone(), value.clone());
        }
    }
    left
}

fn trim_include(written: &str) -> &str {
    written.trim_matches(|letter| matches!(letter, '"' | '<' | '>'))
}

/// Return one written name without the template arguments applied to it.
///
/// `count_run<do_compose>` and `count_run<other>` are one function used twice, and the graph is
/// about which function that is rather than which instantiation this line asked for.
fn bare(written: &str) -> String {
    written
        .split_once('<')
        .map(|(name, _)| name)
        .unwrap_or(written)
        .trim()
        .to_string()
}

/// Whether one word in a type position qualifies a declaration rather than naming a type.
///
/// CUDA writes the execution space in front of a function and C writes storage and lifetime the
/// same way. The parser hands them over where a type would be, and a rule that read them as
/// dependencies would be counting keywords.
fn is_qualifier(written: &str) -> bool {
    const WORDS: &[&str] = &[
        "__device__",
        "__global__",
        "__host__",
        "__forceinline__",
        "__restrict__",
        "__shared__",
        "__constant__",
        "__managed__",
        "__launch_bounds__",
        "static",
        "extern",
        "inline",
        "const",
        "constexpr",
        "volatile",
        "mutable",
        "typename",
        "template",
    ];
    WORDS.contains(&written) || written.is_empty()
}

/// Whether one type declares a member every derived type has to write, which is `= 0`.
///
/// This is how C++ states a contract, and the grammar carries it exactly. A member declaration
/// whose declarator is a function and whose default value is written is a pure virtual, since a
/// function declaration is the only member the language lets anybody assign zero to. Reading the
/// declarator rather than the text is what keeps `int limit = 0;` out of the answer.
fn declares_pure_virtual(node: Syntax) -> bool {
    let Some(body) = child(node, "field_declaration_list") else {
        return false;
    };
    children(body).into_iter().any(|member| {
        member.kind() == "field_declaration"
            && member
                .child_by_field_name("declarator")
                .is_some_and(|declarator| {
                    declarator.kind() == "function_declarator"
                        || descendant(declarator, "function_declarator").is_some()
                })
            && member.child_by_field_name("default_value").is_some()
    })
}

fn is_type(node: Syntax) -> bool {
    matches!(
        node.kind(),
        "class_specifier" | "struct_specifier" | "union_specifier" | "enum_specifier"
    )
}

fn is_name(node: Syntax) -> bool {
    matches!(
        node.kind(),
        "identifier"
            | "field_identifier"
            | "type_identifier"
            | "qualified_identifier"
            | "destructor_name"
            | "operator_name"
    )
}

/// Return every named node under one root, in the order the source states them.
fn walk(root: Syntax<'_>) -> Vec<Syntax<'_>> {
    let mut found = Vec::new();
    let mut pending = vec![root];
    while let Some(node) = pending.pop() {
        found.push(node);
        let mut held = children(node);
        held.reverse();
        pending.extend(held);
    }
    found
}

fn children(node: Syntax<'_>) -> Vec<Syntax<'_>> {
    let mut cursor = node.walk();
    node.named_children(&mut cursor).collect()
}

fn child<'tree>(node: Syntax<'tree>, kind: &str) -> Option<Syntax<'tree>> {
    children(node).into_iter().find(|item| item.kind() == kind)
}

/// Return what one declarator wraps, which is the next step toward the name it finally binds.
///
/// Most wrappers name the thing they wrap through a `declarator` field. A reference, a parameter
/// pack, and the parentheses a function pointer needs do not, and all three are ordinary shapes
/// rather than corners, so opening them by their only child is what keeps `const Frame& frame`,
/// `Rest... rest`, and `void (*hook)(int)` from vanishing.
fn wrapped(node: Syntax<'_>) -> Option<Syntax<'_>> {
    match node.kind() {
        "reference_declarator" | "variadic_declarator" | "parenthesized_declarator" => {
            children(node).into_iter().next()
        }
        _ => node.child_by_field_name("declarator"),
    }
}

/// Return the declarator level that binds the name, which is the one level a caller never sees.
///
/// A cv-qualifier written beside the name qualifies the parameter itself rather than the value it
/// carries, so `int *const p` and `int *p` accept exactly the same argument and `const int limit`
/// demands nothing of anybody. Finding that level is what tells those apart from a `const` that
/// reaches the pointee, which every caller has to respect.
fn binding_level(node: Syntax<'_>) -> Syntax<'_> {
    let mut level = node;
    while let Some(held) = wrapped(level).filter(|held| !is_name(*held)) {
        level = held;
    }
    level
}

/// Return one entry of a parameter list beside the way it binds, when it declares a parameter.
///
/// A C ellipsis carries no name and no type, so it declares nothing a graph can hold and never
/// arrives here. Everything else in the list is a position, and the grammar separates the three
/// shapes a position takes.
fn native_parameter(node: Syntax<'_>) -> Option<(Syntax<'_>, ParameterKind, bool)> {
    match node.kind() {
        "parameter_declaration" => Some((node, ParameterKind::PositionalOnly, false)),
        "optional_parameter_declaration" => Some((node, ParameterKind::PositionalOnly, true)),
        "variadic_parameter_declaration" => Some((node, ParameterKind::VarPositional, false)),
        _ => None,
    }
}

/// Return the shallowest node of one kind under this one, without reading the rest of the tree.
///
/// The parameter list of a declarator and the body of a class are both a step or two down, and a
/// translation unit can be very large, so the search widens one level at a time and stops at the
/// first match rather than collecting everything first.
fn descendant<'tree>(node: Syntax<'tree>, kind: &str) -> Option<Syntax<'tree>> {
    let mut pending = std::collections::VecDeque::from(children(node));
    while let Some(item) = pending.pop_front() {
        if item.kind() == kind {
            return Some(item);
        }
        pending.extend(children(item));
    }
    None
}

/// Return the type declaration one node sits inside, when it sits inside one.
fn enclosing_type(node: Syntax<'_>) -> Option<Syntax<'_>> {
    let mut walker = node.parent();
    while let Some(found) = walker {
        if is_type(found) {
            return Some(found);
        }
        walker = found.parent();
    }
    None
}

/// Return every control structure one native body holds and how deeply it is nested.
///
/// The shared complexity and nesting rules own the scoring model. This frontend only states the
/// same primitive evidence the Python, Rust, and TypeScript frontends state, so one program keeps
/// one meaning across languages and clang-tidy can serve as a differential oracle for the result.
fn control_increments(body: Syntax<'_>) -> Vec<Value> {
    let mut found = Control::default();
    found.read(body);
    found.increments
}

/// Every control structure one body states, collected at the depth visible in the source.
#[derive(Default)]
struct Control {
    depth: usize,
    increments: Vec<Value>,
}

impl Control {
    fn record(&mut self, kind: &str) {
        self.increments
            .push(json!({"kind": kind, "nesting_depth": self.depth}));
    }

    fn inside(&mut self, node: Syntax<'_>) {
        self.depth += 1;
        self.read(node);
        self.depth -= 1;
    }

    /// Read one arm following `else` without charging an `else if` as a nested condition.
    fn alternative(&mut self, clause: Syntax<'_>) {
        self.record("alternative");
        let Some(body) = children(clause).into_iter().next() else {
            return;
        };
        match body.kind() {
            "if_statement" => {
                if let Some(consequence) = body.child_by_field_name("consequence") {
                    self.inside(consequence);
                }
                if let Some(otherwise) = body.child_by_field_name("alternative") {
                    self.alternative(otherwise);
                }
            }
            _ => self.inside(body),
        }
    }

    /// Read one syntax node for the structures it opens and the bodies they govern.
    fn read(&mut self, node: Syntax<'_>) {
        match node.kind() {
            "if_statement" => {
                self.record("conditional");
                if let Some(consequence) = node.child_by_field_name("consequence") {
                    self.inside(consequence);
                }
                if let Some(otherwise) = node.child_by_field_name("alternative") {
                    self.alternative(otherwise);
                }
            }
            "for_statement" | "for_range_loop" | "while_statement" | "do_statement" => {
                self.record("loop");
                if let Some(body) = node.child_by_field_name("body") {
                    self.inside(body);
                }
            }
            "switch_statement" => {
                self.record("switch");
                if let Some(body) = node.child_by_field_name("body") {
                    self.inside(body);
                }
            }
            "try_statement" => {
                self.record("catch");
                for held in children(node) {
                    self.inside(held);
                }
            }
            "function_definition" | "lambda_expression" => {}
            _ => {
                for held in children(node) {
                    self.read(held);
                }
            }
        }
    }
}

fn in_anonymous_namespace(node: Syntax) -> bool {
    let mut walker = node.parent();
    while let Some(found) = walker {
        if found.kind() == "namespace_definition" && found.child_by_field_name("name").is_none() {
            return true;
        }
        walker = found.parent();
    }
    false
}

/// Return every top-level declaration of one translation unit, looking through its namespaces.
fn declarations(root: Syntax<'_>) -> Vec<Syntax<'_>> {
    children(root)
        .into_iter()
        .flat_map(|node| match node.kind() {
            "namespace_definition" => node
                .child_by_field_name("body")
                .map(children)
                .unwrap_or_default(),
            _ => vec![node],
        })
        .collect()
}

/// Build the part of the repository graph one C, C++, or CUDA file states.
pub fn graph(source: Source, module: &str, language: Language) -> Option<Stated> {
    let tree = parse(&source.text, &source.relative)?;
    let root = tree.root_node();
    let mut collector = Collector {
        owners: vec![identity(language, NodeKind::Module, module)],
        scopes: vec![module.to_string()],
        source,
        language,
        nodes: Vec::new(),
        edges: Vec::new(),
        references: Vec::new(),
    };
    collector.scoped(root);
    Some(Stated {
        nodes: collector.nodes,
        edges: collector.edges,
        references: collector.references,
        aliases: BTreeMap::new(),
    })
}

/// Collect every definition and reference one translation unit states.
struct Collector {
    source: Source,
    language: Language,
    scopes: Vec<String>,
    owners: Vec<String>,
    nodes: Vec<Node>,
    edges: Vec<Edge>,
    references: Vec<Reference>,
}

impl Collector {
    fn scope(&self) -> String {
        self.scopes.last().cloned().unwrap_or_default()
    }

    fn owner(&self) -> String {
        self.owners.last().cloned().unwrap_or_default()
    }

    /// Walk one scope, declaring what it holds and recording what its bodies reach.
    ///
    /// A namespace and a type both open a scope that qualifies every name inside it, a function
    /// owns every call its body makes, and anything else is walked through to whatever it holds.
    fn scoped(&mut self, node: Syntax) {
        for child in children(node) {
            match child.kind() {
                "preproc_include" => self.include(child),
                "namespace_definition" => self.namespace(child),
                "function_definition" => self.callable(child),
                "declaration" | "field_declaration" => self.declared(child),
                "call_expression" => {
                    self.call(child);
                    self.scoped(child);
                }
                _ if is_type(child) => self.datatype(child),
                _ => self.scoped(child),
            }
        }
    }

    fn include(&mut self, node: Syntax) {
        let Some(path) = node.child_by_field_name("path") else {
            return;
        };
        let written = trim_include(self.text(path)).to_string();
        // A quoted include is written from where the including file sits and a bracketed one is
        // written from wherever the toolchain looks, so only the first is walked against a path.
        let named = match path.kind() {
            "string_literal" => header_module(&self.source.relative, &written),
            _ => header_module("", &written),
        };
        let owner = self.owner();
        self.push(&owner, &named, EdgeKind::Import, node);
    }

    fn namespace(&mut self, node: Syntax) {
        let named = node
            .child_by_field_name("name")
            .map(|name| self.text(name).to_string())
            .unwrap_or_else(|| "anonymous".to_string());
        let qualname = format!("{}::{named}", self.scope());
        let mut declared = self.place(NodeKind::Module, &qualname, node);
        declared.is_package = true;
        let id = declared.id.clone();
        self.declare(declared, node);
        self.enter(qualname, id);
        if let Some(body) = node.child_by_field_name("body") {
            self.scoped(body);
        }
        self.leave();
    }

    fn datatype(&mut self, node: Syntax) {
        let Some(named) = child(node, "type_identifier").map(|name| self.text(name).to_string())
        else {
            return;
        };
        let qualname = format!("{}::{named}", self.scope());
        let mut declared = self.place(NodeKind::Class, &qualname, node);
        declared.is_abstract = declares_pure_virtual(node);
        let id = declared.id.clone();
        self.declare(declared, node);
        if let Some(clause) = child(node, "base_class_clause") {
            for base in children(clause).into_iter().filter(|item| is_name(*item)) {
                let named = self.text(base).to_string();
                self.push(&id, &named, EdgeKind::Inherit, base);
            }
        }
        self.enter(qualname, id);
        if let Some(body) = descendant(node, "field_declaration_list") {
            self.scoped(body);
        }
        self.leave();
    }

    fn callable(&mut self, node: Syntax) {
        let Some(declarator) = node.child_by_field_name("declarator") else {
            return;
        };
        let Some(named) = self.declarator_name(declarator) else {
            return;
        };
        let qualname = self.qualify(&named);
        let kind = self.member_or_free(&named);
        let declared = self.place(kind, &qualname, node);
        let id = declared.id.clone();
        self.declare(declared, node);
        self.signature(&id, declarator);
        self.named_type(&id, node);
        self.owners.push(id);
        if let Some(body) = node.child_by_field_name("body") {
            self.scoped(body);
        }
        self.owners.pop();
    }

    /// Record the parameters one signature takes and the types it names.
    ///
    /// None of these three dialects lets a caller name an argument, so every parameter binds by
    /// position. What they do state is a C++ default argument and a C++ parameter pack, and the
    /// grammar names both, so a signature says which of its positions a caller may leave out.
    fn signature(&mut self, owner: &str, declarator: Syntax) {
        let Some(list) = descendant(declarator, "parameter_list") else {
            return;
        };
        let held = owner.rsplit(':').next().unwrap_or_default().to_string();
        for (ordinal, (stated, kind, has_default)) in children(list)
            .into_iter()
            .filter_map(native_parameter)
            .enumerate()
        {
            self.named_type(owner, stated);
            let Some(named) = stated
                .child_by_field_name("declarator")
                .and_then(|inner| self.declarator_name(inner))
            else {
                continue;
            };
            let mut declared = parameter(
                self.language,
                &format!("{held}::{named}"),
                ordinal,
                kind,
                has_default,
            );
            declared.path = Some(self.source.relative.clone());
            declared.line = Some(stated.start_position().row + 1);
            let id = declared.id.clone();
            self.nodes.push(declared);
            self.relate(owner, &id, EdgeKind::Define, stated);
        }
    }

    /// Record one declared member, which is a prototype, a field, or a variable.
    fn declared(&mut self, node: Syntax) {
        if let Some(declarator) = descendant(node, "function_declarator") {
            let Some(named) = self.declarator_name(declarator) else {
                return;
            };
            let qualname = self.qualify(&named);
            let kind = self.member_or_free(&named);
            let declared = self.place(kind, &qualname, node);
            let id = declared.id.clone();
            self.declare(declared, node);
            self.signature(&id, declarator);
            return;
        }
        let owner = self.owner();
        self.named_type(&owner, node);
        let Some(named) = node
            .child_by_field_name("declarator")
            .and_then(|inner| self.declarator_name(inner))
        else {
            return;
        };
        let kind = if self.owner().contains(":class:") {
            NodeKind::Attribute
        } else {
            NodeKind::Variable
        };
        let qualname = self.qualify(&named);
        let declared = self.place(kind, &qualname, node);
        self.declare(declared, node);
    }

    fn call(&mut self, node: Syntax) {
        let Some(function) = node.child_by_field_name("function") else {
            return;
        };
        let named = match function.kind() {
            "field_expression" => function
                .child_by_field_name("field")
                .map(|field| self.text(field).to_string())
                .unwrap_or_default(),
            _ => bare(self.text(function)),
        };
        let owner = self.owner();
        self.push(&owner, &named, EdgeKind::Call, node);
    }

    /// Record the type one declaration names, and declare the type it states inline.
    ///
    /// A declaration either names a type that already exists somewhere, which is a dependency, or
    /// writes a whole enum or struct in the type position, which is a declaration that happens to
    /// sit where a name usually goes. Only the first is an edge, and the second is walked into so
    /// what it declares still reaches the graph.
    fn named_type(&mut self, owner: &str, node: Syntax) {
        let Some(stated) = node.child_by_field_name("type") else {
            return;
        };
        if is_type(stated) {
            self.datatype(stated);
            return;
        }
        let named = bare(self.text(stated));
        if is_qualifier(&named) {
            return;
        }
        self.push(owner, &named, EdgeKind::Typed, stated);
    }

    fn member_or_free(&self, named: &str) -> NodeKind {
        if self.owner().contains(":class:") || named.contains("::") {
            NodeKind::Method
        } else {
            NodeKind::Function
        }
    }

    /// Return the repository-wide name one written name stands for inside the current scope.
    fn qualify(&self, written: &str) -> String {
        format!("{}::{written}", self.scope())
    }

    fn place(&self, kind: NodeKind, qualname: &str, at: Syntax) -> Node {
        let mut declared = node(self.language, kind, qualname);
        declared.path = Some(self.source.relative.clone());
        declared.line = Some(at.start_position().row + 1);
        declared
    }

    fn enter(&mut self, qualname: String, owner: String) {
        self.scopes.push(qualname);
        self.owners.push(owner);
    }

    fn leave(&mut self) {
        self.owners.pop();
        self.scopes.pop();
    }

    fn text(&self, node: Syntax) -> &str {
        self.source
            .text
            .get(node.byte_range())
            .unwrap_or_default()
            .trim()
    }

    fn declarator_name(&self, node: Syntax) -> Option<String> {
        if is_name(node) {
            return Some(self.text(node).to_string());
        }
        self.declarator_name(wrapped(node)?)
    }

    fn declare(&mut self, declared: Node, node: Syntax) {
        let owner = self.owner();
        let id = declared.id.clone();
        self.nodes.push(declared);
        self.relate(&owner, &id, EdgeKind::Define, node);
    }

    fn relate(&mut self, source: &str, target: &str, kind: EdgeKind, node: Syntax) {
        self.edges.push(Edge {
            source: source.to_string(),
            target: target.to_string(),
            kind,
            path: self.source.relative.clone(),
            line: node.start_position().row + 1,
            resolution: Resolution::Exact,
        });
    }

    fn push(&mut self, source: &str, expression: &str, kind: EdgeKind, node: Syntax) {
        if expression.is_empty() {
            return;
        }
        self.references.push(Reference {
            source: source.to_string(),
            expression: expression.to_string(),
            language: self.language,
            module: self.scope(),
            owner: None,
            receiver_type: None,
            kind,
            path: self.source.relative.clone(),
            line: node.start_position().row + 1,
        });
    }
}

/// Return the module one included header names, read from where the including file sits.
///
/// A quoted include is written relative to the file that states it, so `../detail/algo.cuh` means
/// something different in every directory it appears in. Walking the path against the including
/// file is what turns all of those into the one module they all name.
fn header_module(including: &str, written: &str) -> String {
    let mut parts: Vec<&str> = including.split('/').collect();
    parts.pop();
    for step in written.split('/') {
        match step {
            "." | "" => {}
            ".." => {
                parts.pop();
            }
            name => parts.push(name),
        }
    }
    let joined = parts.join("/");
    joined
        .rsplit_once('.')
        .map(|(stem, _)| stem)
        .unwrap_or(&joined)
        .replace('/', "::")
}

/// Where the repository states each declared name, indexed by the last segment of it.
///
/// A qualified name is resolved here by namespace lookup rather than by where the file sits, and
/// asking that question of every declared name once per reference is what makes a large generated
/// translation unit unbearable. The last segment narrows the search to a handful before the
/// qualified tail decides.
#[derive(Debug, Default)]
pub struct Lookup {
    by_tail: BTreeMap<String, Vec<String>>,
}

impl Lookup {
    pub fn of(reachable: &BTreeSet<String>) -> Self {
        let mut by_tail: BTreeMap<String, Vec<String>> = BTreeMap::new();
        for known in reachable {
            let tail = known.rsplit("::").next().unwrap_or(known);
            by_tail
                .entry(tail.to_string())
                .or_default()
                .push(known.clone());
        }
        Self { by_tail }
    }

    /// Return the one declaration this written name can mean, when the repository states only one.
    ///
    /// Two matches mean the lookup needs more than this kernel knows, so the reference stays
    /// unresolved rather than being attached to whichever one came first.
    fn only(&self, written: &str) -> Option<&String> {
        let tail = written.rsplit("::").next().unwrap_or(written);
        let suffix = format!("::{written}");
        let mut matching = self
            .by_tail
            .get(tail)?
            .iter()
            .filter(|known| known.ends_with(&suffix));
        match (matching.next(), matching.next()) {
            (Some(only), None) => Some(only),
            _ => None,
        }
    }
}

/// Resolve one native reference against the repository, leaving what cannot be proved visible.
///
/// This language family resolves by name rather than by path, so the question is which enclosing
/// scope declares the name. A header and the unit that implements it land in the same module,
/// which is what makes a declaration in one and a definition in the other the same node.
pub fn resolve(
    reference: &Reference,
    reachable: &BTreeSet<String>,
    lookup: &Lookup,
    nodes: &mut BTreeMap<String, Node>,
    edges: &mut Vec<Edge>,
) {
    let written = reference.expression.trim_start_matches("::");
    let mut candidates = Vec::new();
    let mut scope: Vec<&str> = reference.module.split("::").collect();
    while !scope.is_empty() {
        candidates.push(format!("{}::{written}", scope.join("::")));
        scope.pop();
    }
    candidates.push(written.to_string());
    candidates.extend(lookup.only(written).cloned());
    if attach(reference, &candidates, reachable, nodes, edges) {
        return;
    }
    // An include this repository does not hold is a header the toolchain supplies, which is a
    // dependency rather than a gap.
    if reference.kind == EdgeKind::Import {
        stray(reference, NodeKind::ExternalModule, written, nodes, edges);
        return;
    }
    // A name written with a namespace that this repository does not declare comes from a library
    // it links against, which is a dependency worth naming. A bare name that resolved to nothing
    // is a gap in what this kernel can see, and says so.
    if is_provided(written) {
        stray(
            reference,
            NodeKind::ExternalSymbol,
            &format!("std::{written}"),
            nodes,
            edges,
        );
    } else if written.contains("::") {
        stray(reference, NodeKind::ExternalSymbol, written, nodes, edges);
    } else {
        stray(
            reference,
            NodeKind::UnresolvedSymbol,
            &format!("{}::{written}", reference.module),
            nodes,
            edges,
        );
    }
}

/// Whether one name is something the language, its runtime, or its standard library provides.
///
/// A double underscore is how this family spells a compiler intrinsic, a cast is a keyword that
/// looks like a call, and a name under a standard namespace comes from a header nobody asked this
/// kernel to read. All three are outside the repository rather than missing from it.
fn is_provided(name: &str) -> bool {
    const NAMES: &[&str] = &[
        "static_cast",
        "reinterpret_cast",
        "const_cast",
        "dynamic_cast",
        "sizeof",
        "alignof",
        "decltype",
        "auto",
        "bool",
        "char",
        "double",
        "float",
        "int",
        "long",
        "short",
        "signed",
        "unsigned",
        "void",
        "size_t",
        "ssize_t",
        "ptrdiff_t",
        "uint8_t",
        "uint16_t",
        "uint32_t",
        "uint64_t",
        "int8_t",
        "int16_t",
        "int32_t",
        "int64_t",
        "nullptr_t",
        "wchar_t",
        "dim3",
        "half",
        "half2",
        "char2",
        "char3",
        "char4",
        "uchar2",
        "uchar3",
        "uchar4",
        "short2",
        "short3",
        "short4",
        "ushort2",
        "ushort3",
        "ushort4",
        "int2",
        "int3",
        "int4",
        "uint2",
        "uint3",
        "uint4",
        "long2",
        "long3",
        "long4",
        "ulong2",
        "ulong3",
        "ulong4",
        "float2",
        "float3",
        "float4",
        "double2",
        "double3",
        "double4",
    ];
    NAMES.contains(&name)
        || name.starts_with("__")
        || name.starts_with("std::")
        || name.starts_with("cuda::")
        || name.starts_with("cooperative_groups::")
        || name.starts_with("thrust::")
        || name.starts_with("cub::")
}

#[cfg(test)]
mod tests {
    use super::*;

    const SOURCE: &str = "#include <cuda_runtime.h>\n#include \"engine.h\"\n\nnamespace app {\n\nclass Engine : public Base {\n public:\n  Engine();\n  int run(float value);\n private:\n  int limit;\n};\n\nint Engine::run(float value) {\n  return helper(value);\n}\n\n}\n\nstatic int helper(int amount) { return amount; }\n\n__global__ void scale(float* data) {\n  __syncthreads();\n  cudaMemcpy(data, data, 4, cudaMemcpyHostToDevice);\n}\n";

    fn facts_for(source: &str, relative: &str, family: &str) -> Vec<Value> {
        let document = Document {
            relative: relative.to_string(),
            source: source.to_string(),
        };
        let mut facts = BTreeMap::from([(family.to_string(), Vec::new())]);
        extract(&document, &mut facts, &mut Stats::default());
        facts.remove(family).unwrap_or_default()
    }

    /// Return each parameter of the one function a source states, as name and declared type.
    fn signature_of(source: &str) -> Vec<(String, String)> {
        facts_for(source, "src/engine.cu", "FunctionFact")[0]["parameters"]
            .as_array()
            .expect("a parameter list")
            .iter()
            .map(|item| {
                (
                    item["name"].as_str().unwrap_or_default().to_string(),
                    item["type_name"].as_str().unwrap_or_default().to_string(),
                )
            })
            .collect()
    }

    #[test]
    fn a_parameter_carries_the_type_a_caller_sees_rather_than_the_word_beside_it() {
        let stated = signature_of(concat!(
            "__global__ void merge(int32_t *__restrict__ tokens, int32_t seg_start,\n",
            "                      const int32_t *counts, int32_t &out, float const *weights,\n",
            "                      const int limit, int *const fixed) {}\n"
        ));

        assert_eq!(
            stated,
            vec![
                ("tokens".to_string(), "int32_t *".to_string()),
                ("seg_start".to_string(), "int32_t".to_string()),
                ("counts".to_string(), "const int32_t *".to_string()),
                ("out".to_string(), "int32_t &".to_string()),
                // `float const *` and `const float *` are one type spelled two ways, so both
                // arrive as one string or a rule comparing them misses a real pair.
                ("weights".to_string(), "const float *".to_string()),
                // A qualifier sharing the level that binds the name is one no caller observes,
                // so neither of these is separated from a plain `int` or a plain `int *`.
                ("limit".to_string(), "int".to_string()),
                ("fixed".to_string(), "int *".to_string()),
            ]
        );
    }

    #[test]
    fn two_positions_a_caller_cannot_transpose_never_read_as_one_type() {
        let stated = signature_of(concat!(
            "__global__ void probe(int **flat, int *const *deep, char buf[8], char other[16],\n",
            "                      void (*hook)(int), void (*report)(float),\n",
            "                      int (&grid)[4], int (&block)[8], float &&moved) {}\n"
        ));
        let held: Vec<&str> = stated.iter().map(|(_, kind)| kind.as_str()).collect();

        assert_eq!(
            held,
            vec![
                "int * *",
                "int * const *",
                "char [8]",
                "char [16]",
                "void (int) *",
                "void (float) *",
                "int [4] &",
                "int [8] &",
                "float &&",
            ]
        );
        assert_eq!(held.len(), held.iter().collect::<BTreeSet<_>>().len());
    }

    #[test]
    fn a_position_a_caller_may_leave_out_is_still_a_position() {
        let stated = signature_of("__global__ void run(int value, float scale = 1.0f) {}\n");
        let required: Vec<bool> = facts_for(
            "__global__ void run(int value, float scale = 1.0f) {}\n",
            "src/engine.cu",
            "FunctionFact",
        )[0]["parameters"]
            .as_array()
            .expect("a parameter list")
            .iter()
            .map(|item| item["is_required_by_external_contract"] == true)
            .collect();

        // Dropping the optional one closed the gap between two parameters that never sit side by
        // side, so a rule about transposable neighbours compared a pair no caller can write.
        assert_eq!(stated.len(), 2);
        assert_eq!(stated[1].0, "scale");
        assert_eq!(required, vec![true, false]);
    }

    #[test]
    fn a_call_through_a_receiver_keeps_the_receiver_the_source_wrote() {
        let facts = facts_for(
            concat!(
                "void bench(nvbench::state& state) {\n",
                "  state.exec(timer);\n",
                "  self->read(name);\n",
                "  helper(name);\n",
                "  cuda::std::move(name);\n",
                "}\n"
            ),
            "src/engine.cu",
            "CallFact",
        );
        let named: Vec<&str> = facts[0]["calls"]
            .as_array()
            .expect("a call list")
            .iter()
            .map(|call| call["qualified_name"].as_str().unwrap_or_default())
            .collect();

        // `exec` alone reads as the scope builtin several languages spell that way, and every
        // general rule matching a builtin by name then answers yes for any object holding one.
        assert_eq!(
            named,
            vec!["state.exec", "self.read", "helper", "cuda::std::move"]
        );
    }

    #[test]
    fn a_native_call_credits_the_declaration_it_reaches() {
        let graph = crate::graph::build(
            "repo",
            &[Document {
                relative: "beta.cpp".to_string(),
                source: concat!(
                    "int beta(int value) { return value + 2; }\n",
                    "int caller(int value) { return beta(value); }\n"
                )
                .to_string(),
            }],
        );
        let reached = crate::graph::reach(&graph);
        let declarations = &reached[0].declarations;
        let beta = declarations
            .iter()
            .find(|declared| declared.qualname.ends_with("::beta"))
            .expect("the called declaration");

        assert_eq!(beta.own_file_references, 1);
        assert_eq!(beta.call_count, 1);
    }

    #[test]
    fn control_increments_record_their_nesting_depth() {
        let source = concat!(
            "int score(int value) {\n",
            "  if (value > 0) {\n",
            "    for (int i = 0; i < value; ++i) {\n",
            "      while (value > i) { value--; }\n",
            "    }\n",
            "  } else if (value < 0) {\n",
            "    value = 0;\n",
            "  } else {\n",
            "    value = 1;\n",
            "  }\n",
            "  return value;\n",
            "}\n"
        );
        let facts = facts_for(source, "src/score.cpp", "FunctionFact");
        let increments: Vec<(&str, i64)> = facts[0]["control_increments"]
            .as_array()
            .expect("control increments")
            .iter()
            .map(|item| {
                (
                    item["kind"].as_str().unwrap_or_default(),
                    item["nesting_depth"].as_i64().unwrap_or_default(),
                )
            })
            .collect();

        assert_eq!(
            increments,
            vec![
                ("conditional", 0),
                ("loop", 1),
                ("loop", 2),
                ("alternative", 0),
                ("alternative", 0),
            ]
        );
        assert_eq!(facts[0]["conditional_count"], 1);
    }

    #[test]
    fn a_launch_says_whether_its_own_unit_meets_a_stream_at_all() {
        let alone = facts_for(
            "void run(float* data) {\n  scale<<<grid, block>>>(data);\n}\n",
            "src/engine.cu",
            "KernelLaunchFact",
        );
        let overlapped = facts_for(
            concat!(
                "void run(cudaStream_t stream, float* data) {\n",
                "  scale<<<grid, block>>>(data);\n",
                "}\n"
            ),
            "src/engine.cu",
            "KernelLaunchFact",
        );

        // A default-stream launch drains an overlap only where there is one, and whether there is
        // one is a question about the whole translation unit rather than about the launch.
        assert_eq!(alone[0]["unit_uses_streams"], false);
        assert_eq!(overlapped[0]["unit_uses_streams"], true);
    }

    #[test]
    fn an_access_specifier_is_what_visibility_means_in_this_language() {
        let facts = facts_for(SOURCE, "src/engine.cu", "ClassFact");
        let classes = facts[0]["classes"].as_array().unwrap();
        let methods = classes[0]["methods"].as_array().unwrap();

        assert_eq!(classes[0]["name"], "Engine");
        assert_eq!(classes[0]["direct_bases"][0], "Base");
        assert_eq!(classes[0]["field_count"], 1);
        assert_eq!(methods[0]["kind"], "constructor");
        assert_eq!(methods[0]["visibility"], "public");
        assert_eq!(methods[1]["name"], "run");
        assert_eq!(methods[1]["visibility"], "public");
    }

    #[test]
    fn static_is_how_this_language_narrows_a_free_function() {
        let facts = facts_for(SOURCE, "src/engine.cu", "FunctionFact");
        let named: BTreeMap<&str, &Value> = facts
            .iter()
            .map(|fact| (fact["name"].as_str().unwrap_or_default(), fact))
            .collect();

        assert_eq!(named["helper"]["visibility"], "internal");
        assert_eq!(named["scale"]["visibility"], "public");
        assert_eq!(named["Engine::run"]["scope"], "method");
    }

    #[test]
    fn an_include_records_whether_it_stays_inside_the_project() {
        let facts = facts_for(SOURCE, "src/engine.cu", "ImportBindingFact");

        assert_eq!(facts[0]["module"], "cuda_runtime.h");
        assert_eq!(facts[0]["is_external"], true);
        assert_eq!(facts[1]["module"], "engine.h");
        assert_eq!(facts[1]["is_project_owned"], true);
    }

    #[test]
    fn every_call_a_kernel_makes_is_named_for_the_rules_that_read_them() {
        let facts = facts_for(SOURCE, "src/engine.cu", "CallFact");
        let names: Vec<&str> = facts[0]["calls"]
            .as_array()
            .unwrap()
            .iter()
            .map(|call| call["qualified_name"].as_str().unwrap_or_default())
            .collect();

        assert!(names.contains(&"__syncthreads"));
        assert!(names.contains(&"cudaMemcpy"));
        assert!(names.contains(&"helper"));
        assert_eq!(facts[0]["language"], "cuda");
    }

    #[test]
    fn the_cuda_grammar_reads_a_launch_the_cpp_grammar_cannot_see() {
        let source = "__global__ void scale(float* data) {\n  __shared__ float tile[32];\n}\n\nvoid host(cudaStream_t stream) {\n  scale<<<grid, block>>>(data);\n  scale<<<grid, block, 1024, stream>>>(data);\n}\n";
        let facts = facts_for(source, "src/scale.cu", "KernelLaunchFact");

        assert_eq!(facts.len(), 2);
        assert_eq!(facts[0]["kernel"], "scale");
        assert_eq!(facts[0]["grid"], "grid");
        assert_eq!(facts[0]["block"], "block");
        assert_eq!(facts[0]["stream"], "");
        assert_eq!(facts[0]["enclosing_function"], "host");
        assert_eq!(facts[1]["dynamic_shared_bytes"], "1024");
        assert_eq!(facts[1]["stream"], "stream");
        assert!(facts_for(source, "src/scale.cpp", "KernelLaunchFact").is_empty());
    }

    #[test]
    fn a_header_and_the_unit_that_implements_it_declare_one_module() {
        let graph = crate::graph::build(
            "repo",
            &[
                Document {
                    relative: "src/engine.cpp".to_string(),
                    source:
                        "#include \"engine.h\"\n\nint Engine::run(float value) { return 1; }\n"
                            .to_string(),
                },
                Document {
                    relative: "src/engine.h".to_string(),
                    source: "class Engine {\n public:\n  int run(float value);\n};\n".to_string(),
                },
            ],
        );
        let modules: Vec<&str> = graph
            .nodes
            .iter()
            .filter(|item| item.kind == NodeKind::Module)
            .map(|item| item.qualname.as_str())
            .collect();

        assert_eq!(modules, vec!["src::engine"]);
        assert!(
            graph
                .nodes
                .iter()
                .any(|item| item.id == "cpp:class:src::engine::Engine")
        );
        assert!(graph.edges.iter().any(|edge| edge.kind == EdgeKind::Define
            && edge.target == "cpp:method:src::engine::Engine::run"));
    }

    /// Return every comment group one source states, which is what the family carries.
    fn groups_for(source: &str, relative: &str) -> Vec<Value> {
        let facts = facts_for(source, relative, "CommentFact");
        facts[0]["groups"].as_array().cloned().unwrap_or_default()
    }

    /// Return every kind one tree uses, so a frontend cannot invent one quietly.
    fn kinds_used(tree: &Value) -> BTreeSet<String> {
        let mut found = BTreeSet::new();
        let mut pending = vec![tree];
        while let Some(node) = pending.pop() {
            if let Some(kind) = node["kind"].as_str() {
                found.insert(kind.to_string());
            }
            pending.extend(node["children"].as_array().into_iter().flatten());
        }
        found
    }

    #[test]
    fn both_ways_this_language_opens_a_comment_reach_the_family() {
        let groups = groups_for(SOURCE, "src/engine.cu");

        assert!(groups.is_empty(), "this fixture states none");
        let held = groups_for(
            "/* what this unit is */\n\n// what the next line does\nint run() { return 1; }\n",
            "src/engine.cpp",
        );
        let said: Vec<&str> = held
            .iter()
            .map(|group| group["node"]["text"].as_str().unwrap_or_default())
            .collect();

        assert_eq!(
            said,
            vec!["/* what this unit is */", "// what the next line does"]
        );
        assert_eq!(held[0]["token_count"], 6);
    }

    #[test]
    fn commented_out_native_source_is_told_apart_from_prose_about_it() {
        let groups = groups_for(
            concat!(
                "int run(int count) {\n",
                "  // int stale = count * 2;\n",
                "\n",
                "  // retry twice before giving up\n",
                "  return count;\n",
                "}\n",
                "\n",
                "// static int dead(int value) {\n",
                "//   return value + 1;\n",
                "// }\n",
            ),
            "src/engine.c",
        );
        let read: Vec<bool> = groups
            .iter()
            .map(|group| group["parses_as_source"].as_bool().unwrap_or_default())
            .collect();

        // A statement and a whole declaration are both source; the sentence between them is not.
        assert_eq!(read, vec![true, false, true]);
    }

    #[test]
    fn a_tool_switch_is_marked_and_never_absorbed_into_the_prose_beside_it() {
        let groups = groups_for(
            "// NOLINTNEXTLINE(readability)\n// what this really does\nint run() { return 1; }\n",
            "src/engine.cpp",
        );

        assert_eq!(groups.len(), 2);
        assert_eq!(groups[0]["is_directive"], true);
        assert_eq!(groups[0]["parses_as_source"], false);
        assert_eq!(groups[1]["is_directive"], false);
    }

    #[test]
    fn a_comment_marker_inside_a_literal_is_text_rather_than_a_comment() {
        let groups = groups_for(
            "const char* url = \"https://example.com/a//b\";\n// the only note\n",
            "src/engine.cpp",
        );

        assert_eq!(groups.len(), 1);
        assert_eq!(groups[0]["node"]["text"], "// the only note");
    }

    #[test]
    fn a_declaration_carries_its_own_source_and_its_own_tree() {
        let facts = facts_for(
            "int rename(int count) {\n  int bare = count + 1;\n  return bare;\n}\n",
            "src/engine.cpp",
            "SyntaxFact",
        );
        let body = facts[0]["tree"]["children"].as_array().unwrap();
        let kinds: Vec<&str> = body
            .iter()
            .map(|item| item["kind"].as_str().unwrap_or_default())
            .collect();

        assert_eq!(facts.len(), 1);
        assert_eq!(facts[0]["qualname"], "rename");
        assert_eq!(facts[0]["kind"], "callable");
        assert_eq!(facts[0]["language"], "cpp");
        assert!(
            facts[0]["source"]
                .as_str()
                .unwrap_or_default()
                .starts_with("int rename")
        );
        // The stated return type comes first, then the body, in the order the source states it.
        assert_eq!(kinds, vec!["name", "binding", "return"]);
        assert_eq!(body[1]["name"], "bare");
    }

    #[test]
    fn a_type_tree_stops_at_the_members_that_carry_their_own_facts() {
        let facts = facts_for(SOURCE, "src/engine.cu", "SyntaxFact");
        let named: Vec<&str> = facts
            .iter()
            .map(|fact| fact["qualname"].as_str().unwrap_or_default())
            .collect();
        let held = facts
            .iter()
            .find(|fact| fact["qualname"] == "app::Engine")
            .expect("the type carries a fact");

        assert_eq!(
            named,
            vec!["app::Engine", "app::Engine::run", "helper", "scale"]
        );
        let members = held["tree"]["children"].as_array().unwrap();
        let methods: Vec<&Value> = members
            .iter()
            .filter(|item| item["kind"] == "callable")
            .collect();
        assert_eq!(methods.len(), 2);
        assert!(
            methods[0]["children"].as_array().unwrap().is_empty(),
            "a method body inside a type tree would count every defect in it twice"
        );
    }

    #[test]
    fn a_kernel_is_named_by_the_namespace_and_the_type_that_hold_it() {
        let facts = facts_for(
            "namespace app {\nnamespace inner {\nclass Engine {\n public:\n  int run() { return 1; }\n};\n}\n}\n",
            "src/engine.cu",
            "SyntaxFact",
        );
        let named: Vec<&str> = facts
            .iter()
            .map(|fact| fact["qualname"].as_str().unwrap_or_default())
            .collect();

        assert_eq!(named, vec!["app::inner::Engine", "app::inner::Engine::run"]);
    }

    #[test]
    fn the_tree_reaches_the_names_the_calls_and_the_branches_a_body_states() {
        let facts = facts_for(
            concat!(
                "int run(int count) {\n",
                "  int total = 0;\n",
                "  if (count > 0) {\n",
                "    total = helper(count);\n",
                "  }\n",
                "  count;\n",
                "  return total;\n",
                "}\n",
            ),
            "src/engine.cpp",
            "SyntaxFact",
        );
        let mut seen = Vec::new();
        let mut pending = vec![&facts[0]["tree"]];
        while let Some(node) = pending.pop() {
            seen.push((
                node["kind"].as_str().unwrap_or_default().to_string(),
                node["name"].as_str().unwrap_or_default().to_string(),
            ));
            pending.extend(node["children"].as_array().into_iter().flatten());
        }

        assert!(seen.contains(&("call".to_string(), "helper".to_string())));
        assert!(seen.contains(&("binding".to_string(), "total".to_string())));
        assert!(seen.contains(&("branch".to_string(), String::new())));
        assert!(seen.contains(&("return".to_string(), String::new())));
    }

    #[test]
    fn a_statement_that_only_produces_a_value_is_located_at_that_value() {
        let facts = facts_for(
            "int run(int count) {\n  count;\n  return count;\n}\n",
            "src/engine.cpp",
            "SyntaxFact",
        );
        let body = facts[0]["tree"]["children"].as_array().unwrap();
        let effect = body
            .iter()
            .find(|item| item["kind"] == "effect")
            .expect("a bare expression is an effect");

        // The rule finding a useless statement matches the child covering the statement exactly,
        // so the semicolon has to stay out of the effect's own span.
        assert_eq!(effect["span"], effect["children"][0]["span"]);
        assert_eq!(effect["children"][0]["kind"], "name");
    }

    #[test]
    fn a_comment_is_never_a_node_of_the_code_around_it() {
        let facts = facts_for(
            "int run() {\n  // a note between statements\n  return 1;\n}\n",
            "src/engine.cpp",
            "SyntaxFact",
        );
        let said: Vec<&str> = facts[0]["tree"]["children"]
            .as_array()
            .unwrap()
            .iter()
            .map(|item| item["text"].as_str().unwrap_or_default())
            .collect();

        assert_eq!(said, vec!["int", "return 1;"]);
    }

    #[test]
    fn every_kind_a_tree_uses_is_in_the_shared_vocabulary() {
        let facts = facts_for(SOURCE, "src/engine.cu", "SyntaxFact");
        let known: BTreeSet<&str> = crate::syntax::KINDS.iter().copied().collect();

        assert!(!facts.is_empty());
        for fact in &facts {
            for kind in kinds_used(&fact["tree"]) {
                assert!(
                    known.contains(kind.as_str()),
                    "{kind} is not in the vocabulary"
                );
            }
        }
    }

    #[test]
    fn a_parameter_binds_by_position_and_says_when_a_caller_may_leave_it_out() {
        let graph = crate::graph::build(
            "repo",
            &[Document {
                relative: "src/engine.cpp".to_string(),
                source: concat!(
                    "template <typename... Rest>\n",
                    "int run(int value, float scale = 1.0, Rest&&... rest) { return value; }\n"
                )
                .to_string(),
            }],
        );
        let stated: Vec<(&str, Option<ParameterKind>, bool)> = graph
            .nodes
            .iter()
            .filter(|item| item.kind == NodeKind::Parameter)
            .map(|item| {
                (
                    item.qualname.as_str(),
                    item.parameter_kind,
                    item.has_default,
                )
            })
            .collect();

        assert_eq!(
            stated,
            vec![
                ("run::rest", Some(ParameterKind::VarPositional), false),
                ("run::scale", Some(ParameterKind::PositionalOnly), true),
                ("run::value", Some(ParameterKind::PositionalOnly), false),
            ]
        );
    }
}
