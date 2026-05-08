use std::collections::HashMap;
use std::fs;
use std::mem::MaybeUninit;
use std::os::unix::io::RawFd;
use std::path::PathBuf;

use libc::{close, ioctl, read, O_RDWR, O_NONBLOCK};

use crate::event::{Event, EV_KEY, KeyState};
use crate::errors::VilandError;
use crate::uinput::UinputDevice;
use tracing::{info, warn};

const EVIOCGRAB: u64 = 0x40044590;
const OUR_VENDOR: u16 = 0x1234;

const IN_CREATE: u32 = 0x00000100;
const IN_DELETE: u32 = 0x00000200;

const IOC_NRBITS: u64 = 8;
const IOC_TYPEBITS: u64 = 8;
const IOC_SIZEBITS: u64 = 14;

const IOC_NRSHIFT: u64 = 0;
const IOC_TYPESHIFT: u64 = IOC_NRSHIFT + IOC_NRBITS;
const IOC_SIZESHIFT: u64 = IOC_TYPESHIFT + IOC_TYPEBITS;
const IOC_DIRSHIFT: u64 = IOC_SIZESHIFT + IOC_SIZEBITS;

const IOC_READ: u64 = 2;

const fn ioc(dir: u64, ty: u64, nr: u64, size: u64) -> u64 {
    (dir << IOC_DIRSHIFT) | (ty << IOC_TYPESHIFT) | (nr << IOC_NRSHIFT) | (size << IOC_SIZESHIFT)
}

const fn ior(ty: u64, nr: u64, size: u64) -> u64 {
    ioc(IOC_READ, ty, nr, size)
}

const fn eviocgbit(ev: u64, len: u64) -> u64 {
    ior(b'E' as u64, 0x20 + ev, len)
}

const EVIOCGID: u64 = ior(b'E' as u64, 0x02, 8);

#[repr(C)]
struct InputEvent {
    time: libc::timeval,
    type_: u16,
    code: u16,
    value: i32,
}

#[repr(C)]
struct InputId {
    bustype: u16,
    vendor: u16,
    product: u16,
    version: u16,
}

pub struct DeviceManager {
    fd_to_id: HashMap<RawFd, u32>,
    uinput: Option<UinputDevice>,
    epoll_fd: RawFd,
    inotify_fd: RawFd,
    grabbed_fds: Vec<RawFd>,
}

impl DeviceManager {
    pub fn new() -> Result<Self, VilandError> {
        unsafe {
            let epoll_fd = libc::epoll_create1(0);
            if epoll_fd < 0 {
                return Err(VilandError::Io(std::io::Error::last_os_error()));
            }

            let inotify_fd = libc::inotify_init1(O_NONBLOCK);
            if inotify_fd < 0 {
                return Err(VilandError::Io(std::io::Error::last_os_error()));
            }

            Ok(Self {
                fd_to_id: HashMap::new(),
                uinput: None,
                epoll_fd,
                inotify_fd,
                grabbed_fds: Vec::new(),
            })
        }
    }

    pub fn init(&mut self) -> Result<(), VilandError> {
        let input_dir = PathBuf::from("/dev/input");
        let entries = fs::read_dir(&input_dir)?;

        for entry in entries.flatten() {
            let path = entry.path();
            if let Some(name) = path.file_name() {
                let name_str = name.to_string_lossy();
                if name_str.starts_with("event") {
                    if let Ok(fd) = self.try_open_device(&path) {
                        if self.is_keyboard(fd) {
                            if self.grab_device(fd).is_ok() {
                                let id = self.get_device_id(fd);
                                self.fd_to_id.insert(fd, id);
                                self.grabbed_fds.push(fd);
                                self.add_to_epoll(fd)?;
                                info!("Grabbed keyboard: {} (fd={}, id={})", name_str, fd, id);
                            }
                        } else {
                            unsafe { close(fd); }
                        }
                    }
                }
            }
        }

        if self.fd_to_id.is_empty() {
            let fds: Vec<RawFd> = self.grabbed_fds.drain(..).collect();
            for fd in fds {
                let _ = self.ungrab_device(fd);
                unsafe { close(fd); }
            }
            return Err(VilandError::DeviceNotFound);
        }

        match UinputDevice::new() {
            Ok(u) => self.uinput = Some(u),
            Err(e) => {
                let fds: Vec<RawFd> = self.grabbed_fds.drain(..).collect();
                for fd in fds {
                    let _ = self.ungrab_device(fd);
                    unsafe { close(fd); }
                }
                return Err(e);
            }
        }
        info!("uinput device created");

        let c_path = std::ffi::CString::new("/dev/input")
            .map_err(|_| VilandError::Io(std::io::Error::new(
                std::io::ErrorKind::InvalidInput,
                "path contains null byte",
            )))?;
        unsafe {
            let wd = libc::inotify_add_watch(self.inotify_fd, c_path.as_ptr(), IN_CREATE | IN_DELETE);
            if wd < 0 {
                warn!("Failed to add inotify watch: {}", std::io::Error::last_os_error());
            }
        }

        self.add_inotify_to_epoll()?;

        Ok(())
    }

    fn add_inotify_to_epoll(&self) -> Result<(), VilandError> {
        let mut event = libc::epoll_event {
            u64: self.inotify_fd as u64,
            events: (libc::EPOLLIN | libc::EPOLLHUP | libc::EPOLLERR) as u32,
        };
        unsafe {
            if libc::epoll_ctl(self.epoll_fd, libc::EPOLL_CTL_ADD, self.inotify_fd, &mut event) != 0 {
                return Err(VilandError::Io(std::io::Error::last_os_error()));
            }
        }
        Ok(())
    }

    fn handle_inotify_event(&mut self) -> Result<(), VilandError> {
        let mut buffer = [0u8; 1024];
        let size = unsafe { read(self.inotify_fd, buffer.as_mut_ptr() as *mut _, 1024) };
        if size <= 0 {
            return Ok(());
        }

        let mut offset = 0;
        while offset < size as usize {
            let event_ptr = unsafe { buffer.as_ptr().add(offset) as *const libc::inotify_event };
            let event = unsafe { &*event_ptr };

            if event.len > 0 {
                let name_offset = offset + std::mem::size_of::<libc::inotify_event>();
                let name_ptr = unsafe { buffer.as_ptr().add(name_offset) };

                if let Ok(name_cstr) = unsafe { std::ffi::CStr::from_ptr(name_ptr as *const libc::c_char).to_str() } {
                    if name_cstr.starts_with("event") {
                        if event.mask & IN_CREATE != 0 {
                            info!("New device created: {}", name_cstr);
                            let path = PathBuf::from("/dev/input").join(name_cstr);
                            if let Ok(fd) = self.try_open_device(&path) {
                                if self.is_keyboard(fd) {
                                    if self.grab_device(fd).is_ok() {
                                        let id = self.get_device_id(fd);
                                        self.fd_to_id.insert(fd, id);
                                        self.grabbed_fds.push(fd);
                                        self.add_to_epoll(fd)?;
                                        info!("Grabbed new keyboard: {} (fd={})", name_cstr, fd);
                                    }
                                } else {
                                    unsafe { close(fd); }
                                }
                            }
                        } else if event.mask & IN_DELETE != 0 {
                            info!("Device removed: {}", name_cstr);
                        }
                    }
                }
            }

            offset += (std::mem::size_of::<libc::inotify_event>() + event.len as usize) as usize;
        }

        Ok(())
    }

    fn try_open_device(&self, path: &PathBuf) -> Result<RawFd, VilandError> {
        let c_path = std::ffi::CString::new(path.to_string_lossy().as_ref())
            .map_err(|_| VilandError::Io(std::io::Error::new(
                std::io::ErrorKind::InvalidInput,
                "path contains null byte",
            )))?;
        let fd = unsafe {
            libc::open(c_path.as_ptr(), O_RDWR | libc::O_NONBLOCK)
        };
        if fd < 0 {
            return Err(VilandError::Io(std::io::Error::last_os_error()));
        }
        Ok(fd)
    }

    fn is_keyboard(&self, fd: RawFd) -> bool {
        let mut id = InputId {
            bustype: 0,
            vendor: 0,
            product: 0,
            version: 0,
        };
        unsafe {
            let _ = ioctl(fd, EVIOCGID, &mut id as *mut _ as *mut _);
        }
        if id.vendor == OUR_VENDOR {
            return false;
        }

        let mut ev_bits = [0u8; 64];
        let ioctl_code = eviocgbit(0, ev_bits.len() as u64);
        unsafe {
            if ioctl(fd, ioctl_code, ev_bits.as_mut_ptr() as *mut _) == -1 {
                return false;
            }
        }

        if ev_bits[EV_KEY as usize / 8] & (1 << (EV_KEY % 8)) == 0 {
            return false;
        }

        let mut key_bits = [0u8; 128];
        let key_ioctl_code = eviocgbit(1, key_bits.len() as u64);
        unsafe {
            if ioctl(fd, key_ioctl_code, key_bits.as_mut_ptr() as *mut _) == -1 {
                return false;
            }
        }

        let has_a = key_bits[(crate::event::KEY_A as usize) / 8] & (1 << (crate::event::KEY_A % 8)) != 0;
        let has_z = key_bits[(crate::event::KEY_Z as usize) / 8] & (1 << (crate::event::KEY_Z % 8)) != 0;
        let has_enter = key_bits[(crate::event::KEY_ENTER as usize) / 8] & (1 << (crate::event::KEY_ENTER % 8)) != 0;
        let has_space = key_bits[(crate::event::KEY_SPACE as usize) / 8] & (1 << (crate::event::KEY_SPACE % 8)) != 0;

        let alpha_count = (0..26).filter(|i| {
            let key = crate::event::KEY_A + *i;
            key_bits[(key as usize) / 8] & (1 << (key % 8)) != 0
        }).count();

        has_a && has_z && has_enter && has_space && alpha_count >= 10
    }

    fn grab_device(&self, fd: RawFd) -> Result<(), VilandError> {
        unsafe {
            let ret: i32 = ioctl(fd, EVIOCGRAB as _, 1);
            if ret != 0 {
                return Err(VilandError::DeviceGrabFailed);
            }
        }
        Ok(())
    }

    fn ungrab_device(&self, fd: RawFd) -> Result<(), VilandError> {
        unsafe {
            let ret: i32 = ioctl(fd, EVIOCGRAB as _, 0);
            if ret != 0 {
                return Err(VilandError::DeviceGrabFailed);
            }
        }
        Ok(())
    }

    fn get_device_id(&self, fd: RawFd) -> u32 {
        let mut id = InputId {
            bustype: 0,
            vendor: 0,
            product: 0,
            version: 0,
        };
        unsafe {
            let _ = ioctl(fd, EVIOCGID, &mut id as *mut _ as *mut _);
        }
        let mut hasher = std::collections::hash_map::DefaultHasher::new();
        std::hash::Hash::hash(&id.bustype, &mut hasher);
        std::hash::Hash::hash(&id.vendor, &mut hasher);
        std::hash::Hash::hash(&id.product, &mut hasher);
        std::hash::Hash::hash(&id.version, &mut hasher);
        (std::hash::Hasher::finish(&hasher) & 0xFFFFFFFF) as u32
    }

    fn add_to_epoll(&self, fd: RawFd) -> Result<(), VilandError> {
        let mut event = libc::epoll_event {
            u64: fd as u64,
            events: (libc::EPOLLIN | libc::EPOLLHUP | libc::EPOLLERR) as u32,
        };
        unsafe {
            if libc::epoll_ctl(self.epoll_fd, libc::EPOLL_CTL_ADD, fd, &mut event) != 0 {
                return Err(VilandError::Io(std::io::Error::last_os_error()));
            }
        }
        Ok(())
    }

    fn remove_from_epoll(&self, fd: RawFd) -> Result<(), VilandError> {
        unsafe {
            if libc::epoll_ctl(self.epoll_fd, libc::EPOLL_CTL_DEL, fd, std::ptr::null_mut()) != 0 {
                return Err(VilandError::Io(std::io::Error::last_os_error()));
            }
        }
        Ok(())
    }

    pub fn poll_events(&mut self) -> Result<Vec<Event>, VilandError> {
        let mut events = Vec::new();
        let event_size = std::mem::size_of::<InputEvent>();
        let mut ready_list = [libc::epoll_event { u64: 0, events: 0 }; 64];

        let n = unsafe {
            libc::epoll_wait(
                self.epoll_fd,
                ready_list.as_mut_ptr(),
                64,
                100,
            )
        };

        if n < 0 {
            return Err(VilandError::Io(std::io::Error::last_os_error()));
        }

        let mut fds_to_remove: Vec<RawFd> = Vec::new();

        for i in 0..n as usize {
            let fd = ready_list[i].u64 as RawFd;
            let revents = ready_list[i].events as i32;

            if revents & (libc::EPOLLHUP as i32 | libc::EPOLLERR as i32) != 0 {
                info!("Device fd {} disconnected or error, removing", fd);
                self.ungrab_device(fd).ok();
                self.remove_from_epoll(fd).ok();
                fds_to_remove.push(fd);
                continue;
            }

            if revents & libc::EPOLLIN as i32 == 0 {
                continue;
            }

            if fd == self.inotify_fd {
                self.handle_inotify_event()?;
                continue;
            }

            loop {
                let mut event = MaybeUninit::<InputEvent>::uninit();
                let size = unsafe {
                    read(fd, event.as_mut_ptr() as *mut _, event_size)
                };
                if size < 0 {
                    let err = std::io::Error::last_os_error();
                    if err.kind() == std::io::ErrorKind::WouldBlock {
                        break;
                    }
                    break;
                }
                if size != event_size as isize {
                    break;
                }
                let ie = unsafe { event.assume_init() };
                if ie.type_ == EV_KEY && ie.value >= 0 && ie.value <= 2 {
                    let device_id = self.fd_to_id.get(&fd).copied().unwrap_or(0);

                    if let Some(state) = KeyState::from(ie.value as u32) {
                        let timestamp = (ie.time.tv_sec as u64 * 1000)
                            + (ie.time.tv_usec as u64 / 1000);
                        events.push(Event::new(
                            device_id,
                            ie.code,
                            state,
                            timestamp,
                        ));
                    }
                }
            }
        }

        for fd in fds_to_remove {
            self.fd_to_id.remove(&fd);
            if let Some(pos) = self.grabbed_fds.iter().position(|&x| x == fd) {
                self.grabbed_fds.remove(pos);
            }
            unsafe { close(fd); }
        }

        Ok(events)
    }

    pub fn emit_key(&mut self, key: u16, state: KeyState) -> Result<(), VilandError> {
        if let Some(ref mut uinput) = self.uinput {
            uinput.emit_key(key, state)?;
            uinput.syn()?;
        }
        Ok(())
    }

    pub fn emit_key_press(&mut self, key: u16) -> Result<(), VilandError> {
        self.emit_key(key, KeyState::Press)
    }

    pub fn emit_key_release(&mut self, key: u16) -> Result<(), VilandError> {
        self.emit_key(key, KeyState::Release)
    }

    pub fn release_all_keys(&mut self, virtual_pressed: &std::collections::HashSet<u16>) {
        for &key in virtual_pressed.iter() {
            let _ = self.emit_key(key, KeyState::Release);
        }
    }

    pub fn ungrab_all(&self) {
        for fd in &self.grabbed_fds {
            let _ = self.ungrab_device(*fd);
        }
    }
}

impl Drop for DeviceManager {
    fn drop(&mut self) {
        self.ungrab_all();
        for fd in self.grabbed_fds.drain(..) {
            unsafe { close(fd); }
        }
        if self.inotify_fd >= 0 {
            unsafe { close(self.inotify_fd) };
        }
        if self.epoll_fd >= 0 {
            unsafe { close(self.epoll_fd) };
        }
    }
}