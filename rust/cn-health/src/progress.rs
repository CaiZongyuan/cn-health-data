use std::cell::RefCell;
use std::io::{IsTerminal, Read, Write};
use std::time::{Duration, Instant};

/// Minimum wall-clock interval between two non-TTY progress lines.
const MIN_EMIT_INTERVAL: Duration = Duration::from_secs(5);
/// Minimum percentage step between two non-TTY progress lines.
const MIN_EMIT_STEP_PERCENT: u64 = 5;
/// Rates measured over shorter windows are omitted as noise.
const MIN_RATE_WINDOW: Duration = Duration::from_millis(200);

pub struct Progress {
    label: String,
    tty: bool,
    started: Instant,
    sink: RefCell<Box<dyn Write>>,
    state: RefCell<StreamState>,
    last_rendered_length: RefCell<usize>,
}

struct StreamState {
    phase: String,
    emitted_at: Option<Instant>,
    emitted_bytes: u64,
    emitted_percent: Option<u64>,
}

impl Progress {
    pub fn new(label: impl Into<String>) -> Self {
        Self::with_sink(
            label,
            Box::new(std::io::stderr()),
            std::io::stderr().is_terminal(),
        )
    }

    fn with_sink(label: impl Into<String>, sink: Box<dyn Write>, tty: bool) -> Self {
        Self {
            label: label.into(),
            tty,
            started: Instant::now(),
            sink: RefCell::new(sink),
            state: RefCell::new(StreamState {
                phase: String::new(),
                emitted_at: None,
                emitted_bytes: 0,
                emitted_percent: None,
            }),
            last_rendered_length: RefCell::new(0),
        }
    }

    /// Starts a phase that has no streaming byte counter, for example SQLite
    /// verification or artifact hashing.
    pub fn phase(&self, name: &str) {
        self.finish_rendered_line();
        {
            let mut state = self.state.borrow_mut();
            state.phase = name.to_owned();
            state.emitted_at = None;
            state.emitted_bytes = 0;
            state.emitted_percent = None;
        }
        self.emit_line(&format!("[{}] {} …", self.label, name));
    }

    /// Reports `bytes` of `total` done for the current streaming phase. The
    /// final call with `bytes == total` always renders one line.
    pub fn update(&self, bytes: u64, total: Option<u64>) {
        let now = Instant::now();
        let percent = percent_of(bytes, total);
        let finished = total.is_some_and(|total| bytes >= total);
        let mut state = self.state.borrow_mut();
        let should_emit = self.tty
            || finished
            || match (state.emitted_at, percent) {
                (Some(last_at), Some(percent_now)) => {
                    now.duration_since(last_at) >= MIN_EMIT_INTERVAL
                        && percent_now.saturating_sub(state.emitted_percent.unwrap_or(0))
                            >= MIN_EMIT_STEP_PERCENT
                }
                _ => false,
            };
        if !should_emit {
            if state.emitted_at.is_none() {
                state.emitted_at = Some(now);
                state.emitted_bytes = bytes;
            }
            return;
        }
        let rate = state
            .emitted_at
            .filter(|last_at| now.duration_since(*last_at) >= MIN_RATE_WINDOW)
            .and_then(|last_at| {
                let elapsed = now.duration_since(last_at).as_secs_f64();
                if elapsed <= 0.0 {
                    None
                } else {
                    Some((bytes.saturating_sub(state.emitted_bytes) as f64 / elapsed) as u64)
                }
            });
        state.emitted_at = Some(now);
        state.emitted_bytes = bytes;
        state.emitted_percent = percent;
        let phase = state.phase.clone();
        drop(state);
        let line = render_streaming(&self.label, &phase, bytes, total, rate);
        if self.tty {
            self.render_replaced(&line);
        } else {
            self.emit_line(&line);
        }
    }

    /// Prints the closing line for the whole operation.
    pub fn finish(&self, message: &str) {
        self.finish_rendered_line();
        let elapsed = format_seconds(self.started.elapsed());
        self.emit_line(&format!(
            "[{label}] {message} ({elapsed})",
            label = self.label
        ));
    }

    fn emit_line(&self, line: &str) {
        let mut sink = self.sink.borrow_mut();
        let _ = writeln!(sink, "{line}");
        let _ = sink.flush();
        *self.last_rendered_length.borrow_mut() = 0;
    }

    fn render_replaced(&self, line: &str) {
        let mut sink = self.sink.borrow_mut();
        let padding = line.len().max(*self.last_rendered_length.borrow());
        let _ = write!(sink, "\r{line:<padding$}", padding = padding);
        let _ = sink.flush();
        *self.last_rendered_length.borrow_mut() = line.len();
    }

    fn finish_rendered_line(&self) {
        if *self.last_rendered_length.borrow() > 0 {
            let mut sink = self.sink.borrow_mut();
            let _ = writeln!(sink);
            let _ = sink.flush();
            *self.last_rendered_length.borrow_mut() = 0;
        }
    }
}

fn percent_of(bytes: u64, total: Option<u64>) -> Option<u64> {
    total.map(|total| {
        bytes
            .saturating_mul(100)
            .checked_div(total)
            .unwrap_or(100)
            .min(100)
    })
}

pub fn render_streaming(
    label: &str,
    phase: &str,
    bytes: u64,
    total: Option<u64>,
    rate_per_second: Option<u64>,
) -> String {
    let rate_text = rate_per_second
        .map(|rate| format!(" {}", format_rate(rate)))
        .unwrap_or_default();
    match total {
        Some(total) => {
            let percent = percent_of(bytes, Some(total)).unwrap_or(100);
            let divisor = unit_divisor(total);
            format!(
                "[{label}] {phase} {}/{} {} ({percent}%){rate_text}",
                scaled_value(bytes, divisor),
                scaled_value(total, divisor),
                unit_name(divisor),
            )
        }
        None => format!("[{label}] {phase} {}{rate_text}", format_bytes(bytes),),
    }
}

fn unit_divisor(bytes: u64) -> f64 {
    const UNIT: f64 = 1024.0;
    let value = bytes as f64;
    if value >= UNIT.powi(3) {
        UNIT.powi(3)
    } else if value >= UNIT.powi(2) {
        UNIT.powi(2)
    } else if value >= UNIT {
        UNIT
    } else {
        1.0
    }
}

fn scaled_value(bytes: u64, divisor: f64) -> String {
    if divisor <= 1.0 {
        format!("{bytes}")
    } else {
        format!("{:.1}", bytes as f64 / divisor)
    }
}

fn unit_name(divisor: f64) -> &'static str {
    const UNIT: f64 = 1024.0;
    if divisor >= UNIT.powi(3) {
        "GB"
    } else if divisor >= UNIT.powi(2) {
        "MB"
    } else if divisor >= UNIT {
        "KB"
    } else {
        "B"
    }
}

/// Copies `reader` into `writer` while reporting streamed byte progress for
/// the current phase. `total`, when known, turns updates into percentages.
pub fn copy_with_progress<R: Read, W: Write>(
    reader: &mut R,
    writer: &mut W,
    progress: &Progress,
    total: Option<u64>,
) -> std::io::Result<u64> {
    let mut buffer = vec![0_u8; 256 * 1024];
    let mut copied: u64 = 0;
    loop {
        let size = reader.read(&mut buffer)?;
        if size == 0 {
            break;
        }
        writer.write_all(&buffer[..size])?;
        copied += size as u64;
        progress.update(copied, total);
    }
    Ok(copied)
}

pub fn format_bytes(bytes: u64) -> String {
    const UNIT: f64 = 1024.0;
    let value = bytes as f64;
    if value >= UNIT.powi(3) {
        format!("{:.1} GB", value / UNIT.powi(3))
    } else if value >= UNIT.powi(2) {
        format!("{:.1} MB", value / UNIT.powi(2))
    } else if value >= UNIT {
        format!("{:.1} KB", value / UNIT)
    } else {
        format!("{bytes} B")
    }
}

pub fn format_rate(bytes_per_second: u64) -> String {
    format!("{}/s", format_bytes(bytes_per_second))
}

pub fn format_seconds(duration: Duration) -> String {
    let seconds = duration.as_secs_f64();
    if seconds < 10.0 {
        format!("{seconds:.1}s")
    } else {
        format!("{}s", seconds.round() as u64)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn formats_bytes_with_one_decimal() {
        assert_eq!(format_bytes(0), "0 B");
        assert_eq!(format_bytes(512), "512 B");
        assert_eq!(format_bytes(1024), "1.0 KB");
        assert_eq!(format_bytes(1_500_000), "1.4 MB");
        assert_eq!(format_bytes(3_221_225_472), "3.0 GB");
    }

    #[test]
    fn renders_streaming_line_with_total_percent_and_rate() {
        let line = render_streaming(
            "nhsa-drugs@2026-01-09.r4",
            "download",
            100_000_000,
            Some(200_000_000),
            Some(8_300_000),
        );
        assert_eq!(
            line,
            "[nhsa-drugs@2026-01-09.r4] download 95.4/190.7 MB (50%) 7.9 MB/s"
        );
    }

    #[test]
    fn renders_streaming_line_without_total_or_rate() {
        assert_eq!(
            render_streaming("x", "decompress", 2048, None, None),
            "[x] decompress 2.0 KB"
        );
        assert_eq!(
            render_streaming("x", "download", 0, Some(0), None),
            "[x] download 0/0 B (100%)"
        );
    }

    struct VecSink(std::rc::Rc<std::cell::RefCell<Vec<u8>>>);

    impl Write for VecSink {
        fn write(&mut self, bytes: &[u8]) -> std::io::Result<usize> {
            self.0.borrow_mut().extend_from_slice(bytes);
            Ok(bytes.len())
        }
        fn flush(&mut self) -> std::io::Result<()> {
            Ok(())
        }
    }

    fn sink() -> (std::rc::Rc<std::cell::RefCell<Vec<u8>>>, Box<dyn Write>) {
        let buffer = std::rc::Rc::new(std::cell::RefCell::new(Vec::new()));
        (buffer.clone(), Box::new(VecSink(buffer)))
    }

    fn output(buffer: &std::rc::Rc<std::cell::RefCell<Vec<u8>>>) -> String {
        String::from_utf8(buffer.borrow().clone()).unwrap()
    }

    #[test]
    fn non_tty_progress_emits_final_line_and_gates_intermediate_lines() {
        let (buffer, boxed) = sink();
        let progress = Progress::with_sink("lab@r1", boxed, false);
        progress.phase("download");
        progress.update(1, Some(100));
        progress.update(50, Some(100));
        progress.update(100, Some(100));
        let text = output(&buffer);
        assert!(text.contains("[lab@r1] download …"));
        assert!(!text.contains("(1%)"));
        assert!(!text.contains("(50%)"));
        assert!(text.contains("[lab@r1] download 100/100 B (100%)"));
    }

    #[test]
    fn non_tty_progress_seeds_first_update_as_rate_baseline_without_emitting() {
        let (buffer, boxed) = sink();
        let progress = Progress::with_sink("lab@r1", boxed, false);
        progress.phase("download");
        progress.update(3, Some(100));
        let mut state = progress.state.borrow_mut();
        assert!(state.emitted_at.is_some());
        assert_eq!(state.emitted_bytes, 3);
        state.emitted_at = Some(Instant::now() - MIN_EMIT_INTERVAL - Duration::from_secs(1));
        drop(state);
        progress.update(10, Some(100));
        let text = output(&buffer);
        assert!(text.contains("(10%)"));
    }

    #[test]
    fn non_tty_progress_emits_intermediate_line_after_interval_and_step() {
        let (buffer, boxed) = sink();
        let progress = Progress::with_sink("lab@r1", boxed, false);
        progress.phase("download");
        let mut state = progress.state.borrow_mut();
        state.emitted_at = Some(Instant::now() - MIN_EMIT_INTERVAL - Duration::from_secs(1));
        state.emitted_percent = Some(10);
        drop(state);
        progress.update(20, Some(100));
        let text = output(&buffer);
        assert!(text.contains("(20%)"));
    }

    #[test]
    fn tty_progress_replaces_one_line_and_finishes_with_newline() {
        let (buffer, boxed) = sink();
        let progress = Progress::with_sink("lab@r1", boxed, true);
        progress.phase("download");
        progress.update(10, Some(100));
        progress.update(100, Some(100));
        progress.finish("done");
        let text = output(&buffer);
        assert!(text.contains('\r'));
        assert!(text.contains("(10%)"));
        assert!(text.contains("(100%)"));
        assert!(text.contains("[lab@r1] done ("));
        assert!(text.ends_with('\n'));
    }
}
