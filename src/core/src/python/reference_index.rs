use crate::walk::qualified_name;
use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, ExprContext, ModModule, Stmt};
use ruff_text_size::{Ranged, TextRange};
use std::collections::BTreeMap;
/// Every name one module reads, counted where the interpreter would read it.
///
/// A resolver that misses one position invents an unused import out of live code, and the
/// positions that were missed were never exotic. A name tested by an `elif`, named as the type an
/// `except` catches, or matched by a `case` are all ordinary Python that a hand-written list of
/// interesting expressions simply did not reach. Riding the parser's own traversal is what keeps
/// that list from being written again, and the day the language grows a position the traversal
/// grows with it.
///
/// Reading a name and mentioning it are counted apart, because they answer different questions. A
/// forward reference written inside a string and a later binding of the same name both mean that
/// deleting the import is not the repair, while neither says the module treats the name as a
/// value, which is the only thing a first-class reference is about.
#[derive(Default)]
pub(super) struct ReferenceIndex {
    pub(super) loads: BTreeMap<String, usize>,
    mentions: BTreeMap<String, usize>,
    locations: BTreeMap<String, Vec<TextRange>>,
    typed: usize,
}

impl ReferenceIndex {
    pub(super) fn of(module: &ModModule) -> Self {
        let mut index = Self::default();
        index.visit_body(&module.body);
        index
    }

    /// Return every exact syntax range contributing to one binding's read count.
    pub(super) fn locations(&self, name: &str) -> &[TextRange] {
        self.locations
            .get(name)
            .map(Vec::as_slice)
            .unwrap_or_default()
    }

    /// Return how many times one name is read or otherwise mentioned outside its own import.
    pub(super) fn reads(&self, name: &str) -> usize {
        self.loads.get(name).copied().unwrap_or_default()
            + self.mentions.get(name).copied().unwrap_or_default()
    }

    /// Read the arguments of one typing constructor, which state types written as text.
    ///
    /// `cast` takes its type first and the rest take a name first, and reading a name string as a
    /// type expression only ever counts the name a declaration is giving itself, so all of them
    /// are read the same way rather than each being given its own argument positions.
    fn constructor(&mut self, item: &ruff_python_ast::ExprCall) {
        self.visit_expr(&item.func);
        for argument in &item.arguments.args {
            self.read_type(argument);
        }
        for keyword in &item.arguments.keywords {
            self.read_type(&keyword.value);
        }
    }

    /// Count the names one string spells, which is how a forward reference is written.
    ///
    /// The string is parsed rather than scanned, so text that is not an expression contributes
    /// nothing and a nested reference contributes what it names.
    fn forward_reference(&mut self, text: &str, range: TextRange) {
        let Ok(parsed) = ruff_python_parser::parse_expression(text) else {
            return;
        };
        let mut inner = Self {
            typed: 1,
            ..Self::default()
        };
        inner.visit_expr(&parsed.syntax().body);
        for (name, count) in inner.loads.into_iter().chain(inner.mentions) {
            *self.mentions.entry(name.clone()).or_default() += count;
            self.locations
                .entry(name)
                .or_default()
                .extend(vec![range; count]);
        }
    }

    fn read_at_depth(&mut self, expression: &Expr, depth: usize) {
        let outer = self.typed;
        self.typed = depth;
        self.visit_expr(expression);
        self.typed = outer;
    }

    /// Read one expression as a type expression.
    fn read_type(&mut self, expression: &Expr) {
        self.read_at_depth(expression, self.typed + 1);
    }

    /// Read one expression as ordinary runtime code.
    fn read_value(&mut self, expression: &Expr) {
        self.read_at_depth(expression, 0);
    }

    /// Read the slice of one subscript, which is a type expression unless the base says otherwise.
    ///
    /// `Literal` states values rather than types, and only the first argument of `Annotated` is
    /// the type it qualifies, so a string under either of those is text rather than a name.
    fn subscript(&mut self, item: &ruff_python_ast::ExprSubscript) {
        self.visit_expr(&item.value);
        let base = qualified_name(&item.value);
        match base.rsplit('.').next().unwrap_or_default() {
            "Literal" => self.read_value(&item.slice),
            "Annotated" => {
                match item.slice.as_ref() {
                    Expr::Tuple(tuple) => tuple.elts.iter().enumerate().for_each(
                        |(position, element)| match position {
                            0 => self.read_type(element),
                            _ => self.read_value(element),
                        },
                    ),
                    slice => self.read_type(slice),
                }
            }
            _ => self.read_type(&item.slice),
        }
    }
}

impl<'a> Visitor<'a> for ReferenceIndex {
    fn visit_annotation(&mut self, expression: &'a Expr) {
        self.read_type(expression);
    }

    fn visit_expr(&mut self, expression: &'a Expr) {
        match expression {
            // A delete reads an existing binding. A store replaces it, as a runtime placeholder
            // does for a type-only import, so deleting that import breaks the type checker.
            Expr::Name(name) if matches!(name.ctx, ExprContext::Load | ExprContext::Del) => {
                *self.loads.entry(name.id.to_string()).or_default() += 1;
                self.locations
                    .entry(name.id.to_string())
                    .or_default()
                    .push(name.range());
            }
            Expr::Name(name) => {
                *self.mentions.entry(name.id.to_string()).or_default() += 1;
                self.locations
                    .entry(name.id.to_string())
                    .or_default()
                    .push(name.range());
            }
            Expr::StringLiteral(literal) if self.typed > 0 => {
                self.forward_reference(literal.value.to_str(), literal.range());
            }
            Expr::Subscript(item) => return self.subscript(item),
            Expr::Call(item) if states_types(&item.func) => return self.constructor(item),
            _ => {}
        }
        visitor::walk_expr(self, expression);
    }

    fn visit_stmt(&mut self, statement: &'a Stmt) {
        match statement {
            Stmt::TypeAlias(item) => {
                self.read_type(&item.value);
                if let Some(parameters) = &item.type_params {
                    self.visit_type_params(parameters);
                }
            }
            // The default traversal visits an `elif` test from both its statement and clause.
            // Visit it once so one call does not become a first-class reference.
            Stmt::If(item) => {
                self.visit_expr(&item.test);
                self.visit_body(&item.body);
                for clause in &item.elif_else_clauses {
                    if let Some(test) = &clause.test {
                        self.visit_expr(test);
                    }
                    self.visit_body(&clause.body);
                }
            }
            _ => visitor::walk_stmt(self, statement),
        }
    }
}

/// Whether one callee is a typing constructor stating a type where a traversal reads ordinary code.
///
/// Every entry is named in the typing specification, which is what keeps this a closed vocabulary
/// rather than a list that grows with taste. Without it a forward reference handed to `cast` or
/// listed as a `TypeVar` constraint is text, and the import it names reads as dead.
fn states_types(callee: &Expr) -> bool {
    matches!(
        qualified_name(callee)
            .rsplit('.')
            .next()
            .unwrap_or_default(),
        "cast"
            | "NamedTuple"
            | "NewType"
            | "ParamSpec"
            | "TypeAliasType"
            | "TypeVar"
            | "TypeVarTuple"
            | "TypedDict"
    )
}
