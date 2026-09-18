//! One-hop, DNS-pinned HTTP acquisition with bounded atomic staging.
use std::net::{IpAddr, SocketAddr};
use std::path::{Path, PathBuf};
use std::sync::Once;
use std::time::Duration;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyAny;
use reqwest::header::{ACCEPT_ENCODING, CONTENT_DISPOSITION, CONTENT_LENGTH, LOCATION};
#[cfg(test)]
use reqwest::StatusCode;
use reqwest::{Client, Url};
use sha2::{Digest, Sha256};
use tempfile::NamedTempFile;
use tokio::io::AsyncWriteExt;

static TLS_PROVIDER: Once = Once::new();

fn install_tls_provider() {
    TLS_PROVIDER.call_once(|| {
        let _ = rustls::crypto::ring::default_provider().install_default();
    });
}

struct PendingFile {
    file: Option<NamedTempFile>,
}

impl PendingFile {
    async fn create(directory: PathBuf) -> Result<Self, &'static str> {
        let file = tokio::task::spawn_blocking(move || NamedTempFile::new_in(directory))
            .await
            .map_err(|_| "download_staging_failed")?
            .map_err(|_| "download_staging_failed")?;
        Ok(Self { file: Some(file) })
    }

    fn writer(&self) -> Result<std::fs::File, &'static str> {
        self.file
            .as_ref()
            .ok_or("download_staging_failed")?
            .as_file()
            .try_clone()
            .map_err(|_| "download_staging_failed")
    }

    fn publish(mut self, destination: PathBuf) -> Result<(), &'static str> {
        let file = self.file.take().ok_or("download_staging_failed")?;
        file.persist_noclobber(destination).map_err(|error| {
            if error.error.kind() == std::io::ErrorKind::AlreadyExists {
                "download_destination_exists"
            } else {
                "download_staging_failed"
            }
        })?;
        Ok(())
    }
}

/// A completed one-hop request whose body remains private until explicitly published.
///
/// Keeping the temporary file owned by this object lets Python derive the final suffix
/// from response headers without moving the response body through Python. Dropping an
/// unpublished result removes the temporary file.
#[pyclass]
pub struct NativeDownload {
    status: u16,
    location: Option<String>,
    content_disposition: Option<String>,
    written: u64,
    digest: Option<String>,
    directory: PathBuf,
    pending: Option<PendingFile>,
}

#[pymethods]
impl NativeDownload {
    #[getter]
    fn status(&self) -> u16 {
        self.status
    }

    #[getter]
    fn location(&self) -> Option<&str> {
        self.location.as_deref()
    }

    #[getter]
    fn content_disposition(&self) -> Option<&str> {
        self.content_disposition.as_deref()
    }

    #[getter]
    fn written(&self) -> u64 {
        self.written
    }

    #[getter]
    fn digest(&self) -> Option<&str> {
        self.digest.as_deref()
    }

    fn publish(&mut self, destination: PathBuf) -> PyResult<String> {
        if destination.file_name().is_none() || destination.parent() != Some(&self.directory) {
            return Err(PyValueError::new_err("download_invalid_destination"));
        }
        let pending = self
            .pending
            .take()
            .ok_or_else(|| PyValueError::new_err("download_not_publishable"))?;
        pending
            .publish(destination)
            .map_err(PyValueError::new_err)?;
        self.digest
            .clone()
            .ok_or_else(|| PyValueError::new_err("download_staging_failed"))
    }
}

fn validate_target(
    url: &str,
    host: &str,
    ip: &str,
    port: u16,
    directory: &Path,
    byte_limit: u64,
    timeout_seconds: f64,
) -> Result<(Url, IpAddr), &'static str> {
    let parsed = Url::parse(url).map_err(|_| "url_invalid")?;
    if !matches!(parsed.scheme(), "http" | "https")
        || parsed.host_str() != Some(host)
        || parsed.port_or_known_default() != Some(port)
        || !parsed.username().is_empty()
        || parsed.password().is_some()
    {
        return Err("download_target_mismatch");
    }
    let ip = ip.parse().map_err(|_| "download_target_mismatch")?;
    if directory.as_os_str().is_empty()
        || byte_limit == 0
        || !timeout_seconds.is_finite()
        || !(1.0..=300.0).contains(&timeout_seconds)
    {
        return Err("download_invalid_request");
    }
    Ok((parsed, ip))
}

async fn download_one(
    url: String,
    host: String,
    ip: String,
    port: u16,
    directory: PathBuf,
    byte_limit: u64,
    timeout_seconds: f64,
) -> Result<NativeDownload, &'static str> {
    let (url, ip) = validate_target(
        &url,
        &host,
        &ip,
        port,
        &directory,
        byte_limit,
        timeout_seconds,
    )?;
    install_tls_provider();
    let client = Client::builder()
        .redirect(reqwest::redirect::Policy::none())
        .no_proxy()
        .timeout(Duration::from_secs_f64(timeout_seconds))
        .resolve(&host, SocketAddr::new(ip, port))
        .build()
        .map_err(|_| "download_failed")?;
    let mut response = client
        .get(url)
        .header(ACCEPT_ENCODING, "identity")
        .send()
        .await
        .map_err(|error| {
            if error.is_timeout() {
                "download_timeout"
            } else {
                "download_failed"
            }
        })?;
    let status = response.status();
    let location = response
        .headers()
        .get(LOCATION)
        .and_then(|value| value.to_str().ok())
        .map(str::to_owned);
    let disposition = response
        .headers()
        .get(CONTENT_DISPOSITION)
        .and_then(|value| value.to_str().ok())
        .map(str::to_owned);
    if status.is_redirection() {
        return Ok(NativeDownload {
            status: status.as_u16(),
            location,
            content_disposition: disposition,
            written: 0,
            digest: None,
            directory,
            pending: None,
        });
    }
    if !status.is_success() {
        return Err("download_http_status");
    }
    if response
        .headers()
        .get(CONTENT_LENGTH)
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.parse::<u64>().ok())
        .is_some_and(|length| length > byte_limit)
    {
        return Err("download_too_large");
    }
    let pending = PendingFile::create(directory.clone()).await?;
    let mut output = tokio::fs::File::from_std(pending.writer()?);
    let mut written = 0u64;
    let mut digest = Sha256::new();
    while let Some(chunk) = response.chunk().await.map_err(|error| {
        if error.is_timeout() {
            "download_timeout"
        } else {
            "download_failed"
        }
    })? {
        written = written
            .checked_add(chunk.len() as u64)
            .ok_or("download_too_large")?;
        if written > byte_limit {
            return Err("download_too_large");
        }
        output
            .write_all(&chunk)
            .await
            .map_err(|_| "download_staging_failed")?;
        digest.update(&chunk);
    }
    output
        .flush()
        .await
        .map_err(|_| "download_staging_failed")?;
    output
        .sync_all()
        .await
        .map_err(|_| "download_staging_failed")?;
    drop(output);
    let digest = digest.finalize();
    let mut digest_hex = String::with_capacity(digest.len() * 2);
    for byte in digest {
        use std::fmt::Write as _;
        write!(&mut digest_hex, "{byte:02x}").map_err(|_| "download_staging_failed")?;
    }
    Ok(NativeDownload {
        status: status.as_u16(),
        location,
        content_disposition: disposition,
        written,
        digest: Some(digest_hex),
        directory,
        pending: Some(pending),
    })
}

#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn download_to_staging<'py>(
    py: Python<'py>,
    url: String,
    host: String,
    ip: String,
    port: u16,
    directory: PathBuf,
    byte_limit: u64,
    timeout_seconds: f64,
) -> PyResult<Bound<'py, PyAny>> {
    pyo3_async_runtimes::tokio::future_into_py(py, async move {
        download_one(url, host, ip, port, directory, byte_limit, timeout_seconds)
            .await
            .map_err(PyValueError::new_err)
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_a_target_that_does_not_match_the_url() {
        let path = Path::new("/tmp");
        assert_eq!(
            validate_target(
                "https://example.com/model.stl",
                "other.example",
                "192.0.2.1",
                443,
                path,
                1024,
                60.0,
            ),
            Err("download_target_mismatch")
        );
    }

    #[test]
    fn rejects_credentials_and_invalid_limits() {
        let path = Path::new("/tmp");
        assert_eq!(
            validate_target(
                "https://user@example.com/model.stl",
                "example.com",
                "192.0.2.1",
                443,
                path,
                1024,
                60.0,
            ),
            Err("download_target_mismatch")
        );
        assert_eq!(
            validate_target(
                "https://example.com/model.stl",
                "example.com",
                "192.0.2.1",
                443,
                path,
                0,
                60.0,
            ),
            Err("download_invalid_request")
        );
    }

    #[test]
    fn recognizes_redirect_statuses() {
        for status in [
            StatusCode::MOVED_PERMANENTLY,
            StatusCode::FOUND,
            StatusCode::SEE_OTHER,
            StatusCode::TEMPORARY_REDIRECT,
            StatusCode::PERMANENT_REDIRECT,
        ] {
            assert!(status.is_redirection());
        }
    }

    #[test]
    fn create_only_publication_preserves_an_existing_destination() {
        use std::io::Write as _;

        let directory = tempfile::tempdir().unwrap();
        let runtime = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .unwrap();
        let pending = runtime
            .block_on(PendingFile::create(directory.path().to_path_buf()))
            .unwrap();
        pending.writer().unwrap().write_all(b"new bytes").unwrap();
        let destination = directory.path().join("model.stl");
        std::fs::write(&destination, b"existing bytes").unwrap();

        assert_eq!(
            pending.publish(destination.clone()),
            Err("download_destination_exists")
        );
        assert_eq!(std::fs::read(destination).unwrap(), b"existing bytes");
    }
}
