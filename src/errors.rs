use std::fmt;

#[derive(Debug)]
pub enum VilandError {
    Io(std::io::Error),
    DeviceNotFound,
    DeviceGrabFailed,
    UinputCreateFailed,
    EventNotSupported,
    InvalidState(String),
}

impl fmt::Display for VilandError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            VilandError::Io(e) => write!(f, "IO error: {}", e),
            VilandError::DeviceNotFound => write!(f, "Device not found"),
            VilandError::DeviceGrabFailed => write!(f, "Failed to grab device"),
            VilandError::UinputCreateFailed => write!(f, "Failed to create uinput device"),
            VilandError::EventNotSupported => write!(f, "Event type not supported"),
            VilandError::InvalidState(s) => write!(f, "Invalid state: {}", s),
        }
    }
}

impl std::error::Error for VilandError {}

impl From<std::io::Error> for VilandError {
    fn from(e: std::io::Error) -> Self {
        VilandError::Io(e)
    }
}