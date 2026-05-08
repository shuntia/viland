use libc::{close, ioctl, write as libc_write, timeval, O_WRONLY, O_NONBLOCK};

use crate::event::{EV_KEY, KeyState};
use crate::errors::VilandError;
use tracing::info;

const UINPUT_PATH: &str = "/dev/uinput";

const UINPUT_IOCTL_BASE: u64 = b'U' as u64;

const fn _IO(ty: u64, nr: u64) -> u64 {
    (1 << 31) | ((ty & 0xff) << 8) | (nr & 0xff)
}

const fn _IOW(ty: u64, nr: u64, size: u64) -> u64 {
    (1 << 31) | ((ty & 0xff) << 8) | (nr & 0xff) | ((size & 0xfff) << 16)
}

const UI_DEV_SETUP: u64 = _IOW(UINPUT_IOCTL_BASE, 0, 80);
const UI_DEV_CREATE: u64 = _IO(UINPUT_IOCTL_BASE, 1);
const UI_DEV_DESTROY: u64 = _IO(UINPUT_IOCTL_BASE, 2);

const UI_SET_EVBIT: u64 = _IOW(UINPUT_IOCTL_BASE, 0x10, 4);
const UI_SET_KEYBIT: u64 = _IOW(UINPUT_IOCTL_BASE, 0x11, 4);

const BUS_USB: u16 = 0x03;

#[repr(C)]
struct InputEvent {
    time: libc::timeval,
    type_: u16,
    code: u16,
    value: i32,
}

#[repr(C)]
struct UinputSetup {
    id: UinputId,
    name: [u8; 80],
}

#[repr(C)]
struct UinputId {
    bustype: u16,
    vendor: u16,
    product: u16,
    version: u16,
}

pub struct UinputDevice {
    fd: i32,
}

impl UinputDevice {
    pub fn new() -> Result<Self, VilandError> {
        let c_path = std::ffi::CString::new(UINPUT_PATH)
            .map_err(|_| VilandError::UinputCreateFailed)?;
        let fd = unsafe {
            libc::open(c_path.as_ptr(), O_WRONLY | O_NONBLOCK)
        };
        if fd < 0 {
            return Err(VilandError::UinputCreateFailed);
        }

        unsafe {
            let mut ev_bits: u32 = EV_KEY as u32;
            if ioctl(fd, UI_SET_EVBIT as _, &mut ev_bits as *mut _ as *mut libc::c_void) != 0 {
                return Err(VilandError::UinputCreateFailed);
            }
        }

        for code in 0..256u16 {
            unsafe {
                let mut key_bit: u32 = code as u32;
                if ioctl(fd, UI_SET_KEYBIT as _, &mut key_bit as *mut _ as *mut libc::c_void) != 0 {
                    return Err(VilandError::UinputCreateFailed);
                }
            }
        }

        let mut name = [0u8; 80];
        let dev_name = b"Viland Virtual Keyboard\0";
        name[..dev_name.len()].copy_from_slice(dev_name);

        let setup = UinputSetup {
            id: UinputId {
                bustype: BUS_USB,
                vendor: 0x1234,
                product: 0x5678,
                version: 1,
            },
            name,
        };

        unsafe {
            if ioctl(fd, UI_DEV_SETUP as _, &setup as *const _ as *mut libc::c_void) != 0 {
                return Err(VilandError::UinputCreateFailed);
            }
        }

        unsafe {
            if ioctl(fd, UI_DEV_CREATE as _, std::ptr::null::<libc::c_void>()) != 0 {
                return Err(VilandError::UinputCreateFailed);
            }
        }

        info!("Created uinput device");
        Ok(Self { fd })
    }

    pub fn emit_key(&mut self, key: u16, state: KeyState) -> Result<(), VilandError> {
        let event = InputEvent {
            time: timeval {
                tv_sec: 0,
                tv_usec: 0,
            },
            type_: EV_KEY,
            code: key,
            value: match state {
                KeyState::Press => 1,
                KeyState::Release => 0,
                KeyState::Repeat => 2,
            },
        };

        unsafe {
            let ptr = &event as *const InputEvent as *const libc::c_void;
            let len = std::mem::size_of::<InputEvent>();
            if libc_write(self.fd, ptr, len) != len as isize {
                return Err(VilandError::UinputCreateFailed);
            }
        }
        Ok(())
    }

    pub fn syn(&self) -> Result<(), VilandError> {
        let event = InputEvent {
            time: timeval {
                tv_sec: 0,
                tv_usec: 0,
            },
            type_: 0,
            code: 0,
            value: 0,
        };

        unsafe {
            let ptr = &event as *const InputEvent as *const libc::c_void;
            let len = std::mem::size_of::<InputEvent>();
            if libc_write(self.fd, ptr, len) != len as isize {
                return Err(VilandError::UinputCreateFailed);
            }
        }
        Ok(())
    }
}

impl Drop for UinputDevice {
    fn drop(&mut self) {
        unsafe {
            let _ = ioctl(self.fd, UI_DEV_DESTROY as _, std::ptr::null::<libc::c_void>());
            close(self.fd);
        }
    }
}