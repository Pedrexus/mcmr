//! Where the kernel spends its time, measured per phase rather than guessed at.
//!
//! An end-to-end number says the kernel is fast enough and nothing about which part to improve.
//! These run each phase over the same real corpus so the expensive ones are visible, and they are
//! statistical rather than a single stopwatch reading, so a change of a few percent is legible.

use criterion::{BatchSize, Criterion, criterion_group, criterion_main};
use mcmr_kernel::discovery::{Document, Packages};
use mcmr_kernel::protocol::{Request, Stats};
use mcmr_kernel::source::Source;
use ruff_python_parser::parse_module;
use std::collections::BTreeMap;
use std::hint::black_box;
use std::path::Path;

/// Read this repository's own Python as the corpus, since a synthetic one measures nothing real.
fn corpus() -> Vec<Document> {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../src");
    let request = Request {
        root: root.to_string_lossy().into_owned(),
        families: Vec::new(),
        exclude: vec!["**/__pycache__/**".to_string()],
        suffixes: vec![".py".to_string()],
        graph: false,
    };
    let scope = mcmr_kernel::discovery::Scope::of(&request.exclude, &request.suffixes)
        .expect("the patterns compile");
    mcmr_kernel::discovery::collect(&request, &scope)
        .expect("the corpus reads")
        .documents
}

fn parsing(criterion: &mut Criterion) {
    let documents = corpus();
    criterion.bench_function("parse every file", |bencher| {
        bencher.iter(|| {
            for document in &documents {
                black_box(parse_module(&document.source).ok());
            }
        })
    });
    criterion.bench_function("index every file for spans", |bencher| {
        bencher.iter(|| {
            for document in &documents {
                black_box(Source::new(&document.relative, &document.source));
            }
        })
    });
}

/// Measure one family over the whole corpus, parse included, the way a request pays for it.
fn family(criterion: &mut Criterion) {
    let documents = corpus();
    let packages = Packages::of(&documents);
    let mut group = criterion.benchmark_group("family");
    for name in [
        "ModuleFact",
        "FunctionFact",
        "ClassFact",
        "CallFact",
        "ImportBindingFact",
        "AttributeAccessFact",
        "StringExpressionFact",
        "TypeAnnotationFact",
        "SyntaxFact",
    ] {
        group.bench_function(name, |bencher| {
            bencher.iter_batched(
                || BTreeMap::from([(name.to_string(), Vec::new())]),
                |mut facts| {
                    let mut stats = Stats::default();
                    for document in &documents {
                        mcmr_kernel::python::extract(document, &packages, &mut facts, &mut stats);
                    }
                    black_box(facts)
                },
                BatchSize::SmallInput,
            )
        });
    }
    group.finish();
}

fn graph(criterion: &mut Criterion) {
    let documents = corpus();
    criterion.bench_function("build the repository graph", |bencher| {
        bencher.iter(|| black_box(mcmr_kernel::graph::build("src", &documents)))
    });
    let built = mcmr_kernel::graph::build("src", &documents);
    criterion.bench_function("summarize reach from the graph", |bencher| {
        bencher.iter(|| black_box(mcmr_kernel::graph::reach(&built)))
    });
}

fn serializing(criterion: &mut Criterion) {
    let documents = corpus();
    let packages = Packages::of(&documents);
    let mut facts = BTreeMap::from([("SyntaxFact".to_string(), Vec::new())]);
    let mut stats = Stats::default();
    for document in &documents {
        mcmr_kernel::python::extract(document, &packages, &mut facts, &mut stats);
    }
    criterion.bench_function("serialize the syntax trees", |bencher| {
        bencher.iter(|| black_box(serde_json::to_string(&facts).unwrap_or_default()))
    });
}

criterion_group!(benches, parsing, family, graph, serializing);
criterion_main!(benches);
