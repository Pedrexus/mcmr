use crate::walk::walk;
use ruff_python_ast::{ModModule, Stmt};
use std::collections::BTreeSet;

/// How one file spells the asyncio entry points a structured concurrency rule reads.
///
/// A project of its own can declare a function called `create_task`, and reading a bare name would
/// report every call to it as scheduling on the event loop. Only the names this file actually
/// bound to `asyncio` count, whether it imported the module or the entry points themselves.
pub(super) struct Asyncio {
    pub(super) creators: BTreeSet<String>,
    pub(super) gathers: BTreeSet<String>,
    pub(super) groups: BTreeSet<String>,
}

impl Asyncio {
    pub(super) fn of(module: &ModModule) -> Self {
        let mut held = Self {
            creators: BTreeSet::new(),
            gathers: BTreeSet::new(),
            groups: BTreeSet::new(),
        };
        for statement in walk(module) {
            held.read(statement);
        }
        held
    }

    fn bind_module(&mut self, alias: &ruff_python_ast::Alias) {
        let bound = alias
            .asname
            .as_ref()
            .map(ToString::to_string)
            .unwrap_or_else(|| "asyncio".to_string());
        self.creators.insert(format!("{bound}.create_task"));
        self.creators.insert(format!("{bound}.ensure_future"));
        self.gathers.insert(format!("{bound}.gather"));
        self.groups.insert(format!("{bound}.TaskGroup"));
    }

    fn bind_name(&mut self, alias: &ruff_python_ast::Alias) {
        let bound = alias
            .asname
            .as_ref()
            .map(ToString::to_string)
            .unwrap_or_else(|| alias.name.to_string());
        match alias.name.as_str() {
            "create_task" | "ensure_future" => self.creators.insert(bound),
            "gather" => self.gathers.insert(bound),
            "TaskGroup" => self.groups.insert(bound),
            _ => false,
        };
    }

    fn read(&mut self, statement: &Stmt) {
        match statement {
            Stmt::Import(item) => item
                .names
                .iter()
                .filter(|alias| alias.name.as_str() == "asyncio")
                .for_each(|alias| self.bind_module(alias)),
            Stmt::ImportFrom(item)
                if item
                    .module
                    .as_ref()
                    .is_some_and(|named| named.as_str() == "asyncio") =>
            {
                item.names.iter().for_each(|alias| self.bind_name(alias));
            }
            _ => {}
        }
    }
}
