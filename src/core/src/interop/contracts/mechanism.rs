use serde::Serialize;

/// How one language reaches another.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize)]
#[serde(rename_all = "kebab-case")]
pub(crate) enum Mechanism {
    Binary,
    ConsoleScript,
    NativeModule,
    SharedLibrary,
    Kernel,
}

pub(in crate::interop) type Declaration = (String, Mechanism, &'static str);

impl Mechanism {
    pub(in crate::interop) fn label(self) -> &'static str {
        match self {
            Mechanism::Binary => "binary",
            Mechanism::ConsoleScript => "console-script",
            Mechanism::NativeModule => "native-module",
            Mechanism::SharedLibrary => "shared-library",
            Mechanism::Kernel => "kernel",
        }
    }
}
