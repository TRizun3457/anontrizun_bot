use std::process::ExitCode;

#[tokio::main]
async fn main() -> ExitCode {
    anontrizun_bot::init_tracing();

    match anontrizun_bot::run().await {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            tracing::error!("{error:#}");
            ExitCode::FAILURE
        }
    }
}
