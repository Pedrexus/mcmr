use super::*;

#[test]
fn a_cargo_manifest_declares_the_binaries_it_ships() {
    let manifest = "[package]\nname = \"kernel\"\n\n[[bin]]\nname = \"mcmr-kernel\"\npath = \"src/main.rs\"\n";
    let file = CorpusFile {
        path: "Cargo.toml".to_string(),
        text: manifest.to_string(),
    };

    assert_eq!(
        binaries(&file, manifest).expect("the manifest is valid"),
        vec!["mcmr-kernel"]
    );
}

#[test]
fn a_project_manifest_declares_its_console_scripts_as_commands_rather_than_binaries() {
    // A console script names a callable the declaring language already holds, so it is a command
    // a person runs rather than an executable another language has to reach for.
    let manifest = "[project.scripts]\nmcmr = \"mcmr.cli:app\"\n\n[tool.ruff]\nline-length = 99\n";
    let file = CorpusFile {
        path: "pyproject.toml".to_string(),
        text: manifest.to_string(),
    };

    assert_eq!(
        console_scripts(&file, manifest).expect("the manifest is valid"),
        vec!["mcmr"]
    );
    assert_eq!(
        declarations(&file).expect("the manifest is valid"),
        vec![("mcmr".to_string(), Mechanism::ConsoleScript, "python")]
    );
    assert!(
        binaries(&file, manifest)
            .expect("the manifest is valid")
            .is_empty()
    );
}

#[test]
fn a_cargo_binary_and_a_node_command_keep_the_mechanism_each_one_is_reached_through() {
    let cargo = CorpusFile {
        path: "Cargo.toml".to_string(),
        text: "[[bin]]\nname = \"mcmr-kernel\"\npath = \"src/main.rs\"\n".to_string(),
    };
    let package = CorpusFile {
        path: "package.json".to_string(),
        text: r#"{"name":"tools","bin":{"one":"one.js"}}"#.to_string(),
    };

    assert_eq!(
        declarations(&cargo).expect("the manifest is valid"),
        vec![("mcmr-kernel".to_string(), Mechanism::Binary, "rust")]
    );
    assert_eq!(
        declarations(&package).expect("the manifest is valid"),
        vec![("one".to_string(), Mechanism::ConsoleScript, "typescript")]
    );
}

#[test]
fn a_node_manifest_reads_every_binary_from_json_structure() {
    let object = r#"{"name":"tools","bin":{"one":"one.js","two":"two.js"}}"#;
    let single = r#"{"name":"tools","bin":"cli.js"}"#;
    let file = CorpusFile {
        path: "package.json".to_string(),
        text: object.to_string(),
    };

    assert_eq!(
        node_binaries(&file, object).expect("the manifest is valid"),
        vec!["one", "two"]
    );
    assert_eq!(
        node_binaries(&file, single).expect("the manifest is valid"),
        vec!["tools"]
    );
}

#[test]
fn malformed_binary_manifests_fail_instead_of_yielding_partial_names() {
    let invalid = [
        CorpusFile {
            path: "Cargo.toml".to_string(),
            text: "[[bin]]\nname = 3\n".to_string(),
        },
        CorpusFile {
            path: "pyproject.toml".to_string(),
            text: "[project.scripts]\ntool = 3\n".to_string(),
        },
    ];
    let invalid_node = [
        "{ invalid",
        r#"{"bin": ["tool"]}"#,
        r#"{"bin": "cli.js"}"#,
        r#"{"bin": {"tool": 3}}"#,
    ];

    assert!(binaries(&invalid[0], &invalid[0].text).is_err());
    assert!(console_scripts(&invalid[1], &invalid[1].text).is_err());
    let package = CorpusFile {
        path: "package.json".to_string(),
        text: String::new(),
    };
    assert!(
        invalid_node
            .into_iter()
            .all(|text| node_binaries(&package, text).is_err())
    );
}

#[test]
fn a_binding_attribute_names_the_module_it_exports() {
    let source =
        "#[pymodule]\nfn engine(module: &Bound<Module>) -> PyResult<()> {\n    Ok(())\n}\n";
    let pattern = IdentifierPattern {
        marker: "#[pymodule]",
        separator: "fn ",
    };

    assert_eq!(after(source, pattern).collect::<Vec<_>>(), vec!["engine"]);
}

#[test]
fn a_loaded_library_names_the_object_it_opens() {
    let loader = "handle = ctypes.CDLL(\"libfastops.so\")\n";
    let pattern = DelimitedPattern {
        marker: "CDLL(",
        closing: ')',
    };

    assert_eq!(
        between(loader, pattern).collect::<Vec<_>>(),
        vec!["libfastops.so"]
    );
}

#[test]
fn a_pybind_macro_and_a_cuda_kernel_name_themselves() {
    let native = "PYBIND11_MODULE(fastops, module) {\n}\n";
    let kernel = "__global__ void scale(float* data) {}\n";
    let pattern = DelimitedPattern {
        marker: "PYBIND11_MODULE(",
        closing: ',',
    };

    assert_eq!(
        between(native, pattern).collect::<Vec<_>>(),
        vec!["fastops"]
    );
    assert_eq!(kernels(kernel).collect::<Vec<_>>(), vec!["scale"]);
}

#[test]
fn a_kernel_is_named_past_everything_written_between_the_marker_and_its_parameters() {
    let source = concat!(
        "__global__ void scale(float* data) {}\n",
        "__global__ void __launch_bounds__(256, 4) classify_segments(int* out) {}\n",
        "template <typename T>\n__global__ void merge<T>(T* left, T* right) {}\n",
        "__global__ void inline kernels::rank(int* order);\n",
        "extern \"C\" __global__ void __launch_bounds__(128) pack(char* bytes) {}\n",
    );

    assert_eq!(
        kernels(source).collect::<Vec<_>>(),
        vec!["scale", "classify_segments", "merge", "rank", "pack"]
    );
}

#[test]
fn a_marker_with_no_declaration_behind_it_names_nothing() {
    // A qualifier written on a variable and one written on nothing at all both have to answer
    // nothing, since an artifact list is only worth having when every entry is reachable.
    assert!(kernels("__global__ int limit = 4;\n").next().is_none());
    assert!(kernels("__global__\n").next().is_none());
    assert!(
        kernels("__global__ void ] scale(int* out) {}\n")
            .next()
            .is_none()
    );
}

#[test]
fn a_note_about_the_kernels_a_file_holds_declares_none_of_them() {
    let source = concat!(
        "// Four __global__ kernels dispatched from the launcher:\n",
        "//   count_thread_kernel -> per document lengths (1 thread each)\n",
        "/* the __global__ ones below take a stream */\n",
        "__global__ void count_thread_kernel(int* out) {}\n",
    );

    assert_eq!(
        kernels(source).collect::<Vec<_>>(),
        vec!["count_thread_kernel"]
    );
}
