use mcmr_kernel::protocol::Request;
use std::io::Read;

/// Read one request, build the requested fact families, and write the response.
///
/// The request arrives on standard input so a caller never has to quote a path or a glob through
/// a shell, and the response leaves on standard output as one document.
fn main() {
    let mut input = String::new();
    if std::io::stdin().read_to_string(&mut input).is_err() {
        fail("the request could not be read from standard input");
    }
    let request: Request = match serde_json::from_str(&input) {
        Ok(request) => request,
        Err(failure) => return fail(&format!("the request is not valid: {failure}")),
    };
    match mcmr_kernel::run(&request) {
        Ok(response) => println!("{}", serde_json::to_string(&response).unwrap_or_default()),
        Err(failure) => fail(&failure),
    }
}

fn fail(message: &str) {
    eprintln!("mcmr-kernel: {message}");
    std::process::exit(1);
}
