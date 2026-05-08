# TODO - Viland Development

## Immediate (Python - Fix Current Issues)

### Priority 1: Key Release on Shutdown
- [ ] Ensure all pressed_keys are emitted as release before exit
- [ ] Test with multiple keys held

### Priority 2: Caps2Esc Fix
- [ ] capslock tap → escape press+release
- [ ] capslock hold + key → ctrl+key
- [ ] Only in insert mode

### Priority 3: Escape Fix
- [ ] escape tap → pass through (re-emit)
- [ ] escape double-tap → normal mode
- [ ] Only in insert mode

### Priority 4: Direct Uinput
- [ ] Replace ydotool subprocess with python-uinput
- [ ] Reduce latency

### Priority 5: Modifier Fix
- [ ] Only use: {29, 97, 42, 54, 56, 100, 125, 126, 58}
- [ ] Test key combinations

## Testing (Python)

- [ ] Double-tap caps → normal mode
- [ ] Double-tap escape → normal mode
- [ ] h/j/k/l → arrows in normal mode
- [ ] i/a → exit in normal mode
- [ ] ; → command mode
- [ ] Ctrl+Alt+Q → exit
- [ ] Keys release on shutdown
- [ ] No key doubling

## Future (Rust - Rewrite)

- [ ] Create Rust project with tokio
- [ ] Async device polling
- [ ] Direct uinput injection
- [ ] Migrate all features
- [ ] Benchmark latency