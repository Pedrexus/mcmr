use kernel_tables::protocol::{Request, Response, VERSION};
use serde::Serialize;
use std::io::{Read, Write};

/// Read one request, build the requested fact families, and write the response.
///
/// The request arrives on standard input so a caller never has to quote a path or a glob through
/// a shell. A graph leaves as one document, while fact families can leave as independent JSON
/// lines so the caller can validate and release one family before reading the next.
fn main() {
    let mut input = String::new();
    if std::io::stdin().read_to_string(&mut input).is_err() {
        fail("the request could not be read from standard input");
    }
    let request: Request = match serde_json::from_str(&input) {
        Ok(request) => request,
        Err(failure) => return fail(&format!("the request is not valid: {failure}")),
    };
    if request.stream {
        if let Err(failure) = write_stream(&request) {
            fail(&failure);
        }
        return;
    }
    match kernel_tables::run(&request) {
        Ok(response) => {
            if let Err(failure) = write_response(&response) {
                fail(&failure);
            }
        }
        Err(failure) => fail(&failure),
    }
}

fn write_response(response: &Response) -> Result<(), String> {
    let mut output = std::io::stdout().lock();
    serde_json::to_writer(&mut output, response)
        .map_err(|failure| format!("the response could not be serialized: {failure}"))?;
    writeln!(output).map_err(|failure| format!("the response could not be written: {failure}"))
}

fn write_stream(request: &Request) -> Result<(), String> {
    let stdout = std::io::stdout();
    let mut output = std::io::BufWriter::with_capacity(1024 * 1024, stdout.lock());
    writeln!(output, "H\t{VERSION}")
        .map_err(|failure| format!("the response could not be written: {failure}"))?;
    let stats = kernel_tables::run_stream(request, |family, facts| {
        write!(output, "B\t{family}\t")
            .map_err(|failure| format!("the response could not be written: {failure}"))?;
        write_line(&mut output, &facts)
    })?;
    write!(output, "F\t")
        .map_err(|failure| format!("the response could not be written: {failure}"))?;
    write_line(&mut output, &stats)?;
    output
        .flush()
        .map_err(|failure| format!("the response could not be written: {failure}"))
}

fn write_line(output: &mut impl Write, value: &impl Serialize) -> Result<(), String> {
    serde_json::to_writer(&mut *output, value)
        .map_err(|failure| format!("the response could not be serialized: {failure}"))?;
    writeln!(output).map_err(|failure| format!("the response could not be written: {failure}"))
}

fn fail(message: &str) {
    eprintln!("mcmr-kernel: {message}");
    std::process::exit(1);
}
