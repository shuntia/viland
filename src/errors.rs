use std::fmt;

#[derive(Debug)]
pub enum VilandError {
    Io(std::io::Error),
    DeviceNotFound,
}

impl fmt::Display for VilandError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            VilandError::Io(e) => write!(f, "IO error: {}", e),
            VilandError::DeviceNotFound => write!(f, "No suitable input device found"),
        }
    }
}

impl std::error::Error for VilandError {}

impl From<std::io::Error> for VilandError {
    fn from(e: std::io::Error) -> Self {
        VilandError::Io(e)
    }
}