"""Opt-in temporary HTTPS signaling admission; no assets, DNS changes or relay."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import platform
import queue
import re
import socket
import subprocess
import sys
import struct
import threading
import time
from urllib.parse import urlsplit

BINARY_SHA256 = '72edfd3eea463aef4d5cb89e2e209cecb048cc756c2b01915de2e0ad7cb39830'
BINARY_VERSION = 'cloudflared version 2026.10.0 (built 2026-10-05-17:37 UTC)'
BINARY_BYTES = 39364384
BINARY_PROFILES = {
 'darwin': {'sha256': BINARY_SHA256, 'bytes': BINARY_BYTES, 'version': BINARY_VERSION, 'machines': ('arm64','aarch64'), 'kind':'Mach-O ARM64'},
 'win32': {'sha256':'86aee4017b26625cee8484c113558f48effa4cd47f7aa05fcf425604e5d2b23c', 'bytes':55365048, 'version':'cloudflared version 2026.10.0 (built 2026-10-05T08:39 UTC)', 'machines':('amd64','x86_64'), 'kind':'PE AMD64'}
}
REGISTRATION_SECONDS = 45
READINESS_SECONDS = 120
INTERVAL_SECONDS = 5
PROBE_SECONDS = 3
STUN_URL = 'stun:stun.cloudflare.com:3478'
PROTOCOL = 'bo1z-native-rtc-resume-v2'


def temporary_origin(value):
    if not isinstance(value, str) or not value.isascii() or value != value.strip():
        raise RuntimeError('Unexpected temporary signaling address; refusing it.')
    if not re.fullmatch(r'https://[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.trycloudflare\.com', value):
        raise RuntimeError('Free hosting accepts only the temporary official HTTPS address.')
    return value


def correct_binary_machine(path, target):
    try:
        with Path(path).open('rb') as stream:
            header = stream.read(64)
            if target == 'darwin':
                return len(header) >= 8 and struct.unpack('<II', header[:8]) == (0xfeedfacf, 0x0100000c)
            if target == 'win32':
                if len(header) != 64 or header[:2] != b'MZ':
                    return False
                offset = struct.unpack_from('<I', header, 60)[0]
                if offset < 64 or offset > 1048576:
                    return False
                stream.seek(offset)
                pe = stream.read(26)
                return len(pe) == 26 and pe[:4] == b'PE\0\0' and struct.unpack_from('<H', pe, 4)[0] == 0x8664 and struct.unpack_from('<H', pe, 24)[0] == 0x20b
    except (OSError, ValueError, struct.error):
        return False
    return False


def verified_binary(value):
    if not value:
        raise RuntimeError('Free hosting requires --cloudflared PATH to the exact official2026.10.0 MacARM64/WindowsAMD64 binary. Nothing is bundled or downloaded.')
    profile = BINARY_PROFILES.get(sys.platform)
    if not profile or platform.machine().lower() not in profile['machines']:
        raise RuntimeError('Free hosting admits only macOS ARM64 or Windows AMD64 with the exact reviewed official binary.')
    path = Path(value).expanduser().resolve()
    if not path.is_file() or path.stat().st_size != profile['bytes'] or (sys.platform == 'darwin' and not os.access(path, os.X_OK)) or (sys.platform == 'win32' and path.suffix.lower() != '.exe'):
        raise RuntimeError('cloudflared path/type/size differs from the admitted binary.')
    if not correct_binary_machine(path, sys.platform):
        raise RuntimeError('cloudflared executable architecture/format does not match this platform.')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    if digest.hexdigest() != profile['sha256']:
        raise RuntimeError('cloudflared SHA256 differs from the official reviewed binary; it will not be executed.')
    try:
        result = subprocess.run([str(path), '--version'], capture_output=True, text=True, encoding='utf-8', errors='strict', timeout=3, env=tunnel_environment())
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise RuntimeError('The admitted cloudflared did not return its exact version within3 seconds.') from None
    if result.returncode or result.stdout.strip() != profile['version'] or result.stderr.strip():
        raise RuntimeError('cloudflared version/output differs from the reviewed build.')
    verify_no_default_config()
    return path


def default_config_paths():
    # Exact upstream2026.10.0 search: three user directories; Unix adds two system directories.
    home = Path.home()
    dirs = [home / '.cloudflared', home / '.cloudflare-warp', home / 'cloudflare-warp']
    if sys.platform != 'win32':
        dirs += [Path('/etc/cloudflared'), Path('/usr/local/etc/cloudflared')]
    return [directory / name for directory in dirs for name in ('config.yml', 'config.yaml')]


def verify_no_default_config():
    for path in default_config_paths():
        try:
            path.stat()
        except FileNotFoundError:
            continue
        except OSError:
            raise RuntimeError('Default cloudflared configuration could not be safely checked. Nothing will be changed or reused.') from None
        raise RuntimeError('An existing cloudflared configuration needs separate review. This launcher will not change it or reuse it.')


def tunnel_environment():
    return {k: v for k, v in os.environ.items()
            if not k.upper().startswith(('TUNNEL_', 'CLOUDFLARE_', 'CF_')) and k.upper() != 'BO1Z_TURN_SECRET'}


def tunnel_command(binary, port):
    return [str(binary), 'tunnel', '--no-autoupdate', '--url', f'http://127.0.0.1:{port}',
            '--metrics', '127.0.0.1:0', '--loglevel', 'info', '--protocol', 'quic']


def diagnostic_work_root(package_root):
    """Locate work independently of package parent; copied outputs never becomes work."""
    package = Path(package_root).resolve()
    if package.parent.name not in ('work', 'outputs'):
        raise RuntimeError('Private startup diagnostics require a recognized workspace work/outputs package layout.')
    workspace = package.parent.parent
    work, outputs = workspace / 'work', workspace / 'outputs'
    if work.is_symlink() or outputs.is_symlink() or not work.is_dir() or not outputs.is_dir():
        raise RuntimeError('Private startup diagnostics require the actual workspace work directory; outputs is never a log destination.')
    return work.resolve()


class StartupDiagnostics:
    """Single raw writer; atomic prefix snapshots do not wait on filesystem writes."""
    LIMIT = 128 * 1024
    CLOSE_BOUND_SECONDS = 1
    def __init__(self, path, work_root, package_root):
        if sys.platform == 'win32':
            raise RuntimeError('Raw startup diagnostics are unavailable on Windows until private ACL protection is admitted. Sanitized startup/cleanup diagnostics remain enabled.')
        expected_work = diagnostic_work_root(package_root)
        if Path(work_root).expanduser().resolve() != expected_work:
            raise RuntimeError('Explicit diagnostics work root does not match the actual workspace work directory.')
        path = Path(path).expanduser().resolve()
        if not path.is_relative_to(expected_work) or path.is_relative_to(Path(package_root).resolve()):
            raise RuntimeError('Startup diagnostics must be a new private file under actual work, outside the package; never outputs.')
        if not path.parent.is_dir() or path.parent.stat().st_mode & 0o077:
            raise RuntimeError('Create a private work directory for startup diagnostics first.')
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
        try:
            fd = os.open(path, flags, 0o600)
            os.fchmod(fd, 0o600)
            self.stream = os.fdopen(fd, 'wb', buffering=0)
        except OSError:
            if 'fd' in locals():
                os.close(fd)
            raise RuntimeError('Startup diagnostics could not be exclusively created. Existing files will not be overwritten.') from None
        self.captured = 0
        self.truncated = False
        self.digest = hashlib.sha256()
        self.disabled = False
        self.finalized = False
        self.close_incomplete = False
        self.writer_lock = threading.Lock()
        self.state_lock = threading.Lock()

    def append(self, raw):
        with self.writer_lock:
            with self.state_lock:
                if self.disabled or self.finalized:
                    return
                data = raw[:max(0, self.LIMIT - self.captured)]
                self.truncated = self.truncated or len(data) != len(raw)
            try:
                # Filesystem writes hold only writer_lock. Snapshot can still
                # return the previous committed prefix during a blocked write.
                written = self.stream.write(data) if data else 0
            except (OSError, ValueError):
                with self.state_lock:
                    self.disabled = True
                return
            with self.state_lock:
                self.digest.update(data[:written])
                self.captured += written
                self.disabled = written != len(data)

    def snapshot(self):
        with self.state_lock:
            return {'rawBytesCaptured': self.captured, 'rawPrefixSha256': self.digest.hexdigest(),
                    'rawCaptureTruncated': self.truncated, 'rawCaptureWriteFailed': self.disabled,
                    'rawCaptureSnapshotAtomic': True, 'rawCaptureFinalized': self.finalized,
                    'rawCaptureCloseIncomplete': self.close_incomplete}

    def defer_close(self):
        # Reader still writing: do not race fd-close with its append call.
        with self.state_lock:
            self.close_incomplete = True

    def close(self):
        if not self.writer_lock.acquire(timeout=self.CLOSE_BOUND_SECONDS):
            self.defer_close()
            return False
        try:
            try:
                self.stream.close()
            except (OSError, ValueError):
                with self.state_lock:
                    self.disabled = True
                    self.close_incomplete = True
                return False
            with self.state_lock:
                self.finalized = True
                self.close_incomplete = False
            return True
        finally:
            self.writer_lock.release()


class TunnelRegistration:
    """Separate stream termination, strict decoding errors and actual process exits."""
    LINE_LIMIT = 16 * 1024
    ERROR_TYPES = {'UnicodeDecodeError', 'OSError', 'ValueError', 'TypeError', 'LineLimitError'}
    def __init__(self, process, diagnostics=None):
        self.process = process
        self.diagnostics = diagnostics
        self.events = queue.Queue()
        self.admitted = threading.Event()
        self.startup_finished = threading.Event()
        self.origin = None
        self.registered_at = None
        self.origin_observed = False
        self.registration_observed = False
        self.stdout_eof = False
        self.reader_error_type = None
        self.phase = 'registration'
        self.reason = None
        self.poll_at_failure = None
        self.failure_poll_observed = False
        self.lock = threading.Lock()
        self.reader_cleanup_checked = False
        self.reader_cleanup_incomplete = False
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self):
        try:
            while True:
                raw = self.process.stdout.readline(self.LINE_LIMIT + 1)
                if raw == b'':
                    with self.lock:
                        self.stdout_eof = True
                    self.events.put(('stdout_eof', None))
                    return
                if not isinstance(raw, bytes):
                    raise TypeError('Binary log stream required')
                if self.diagnostics and not self.startup_finished.is_set():
                    self.diagnostics.append(raw)
                if len(raw) > self.LINE_LIMIT:
                    with self.lock:
                        self.reader_error_type = 'LineLimitError'
                    self.events.put(('reader_error', None))
                    return
                # Preserve bytes before strict decoding; never execute log text.
                line = raw.decode('utf-8', errors='strict')
                if self.admitted.is_set():
                    continue
                match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com(?=[\s|]|$)', line)
                if match:
                    with self.lock:
                        self.origin_observed = True
                    self.events.put(('origin', match.group(0)))
                if 'Registered tunnel connection' in line:
                    with self.lock:
                        self.registration_observed = True
                    self.events.put(('registered', (time.monotonic(), bool(re.search(r'\bprotocol=quic\b', line)))))
        except Exception as error:
            kind = type(error).__name__
            with self.lock:
                self.reader_error_type = kind if kind in self.ERROR_TYPES else 'OtherError'
            self.events.put(('reader_error', None))

    _UNOBSERVED = object()

    def fail(self, reason, message, observed_poll=_UNOBSERVED):
        with self.lock:
            if self.reason is None:
                self.reason = reason
                value = self.process.poll() if observed_poll is self._UNOBSERVED else observed_poll
                self.poll_at_failure = value if type(value) is int else None
                self.failure_poll_observed = True
        raise RuntimeError(message)

    def capture_failure(self, reason):
        # Pin the provider outcome before any owned process receives cleanup signals.
        with self.lock:
            if self.reason is None:
                value = self.process.poll()
                self.reason = reason
                self.poll_at_failure = value if type(value) is int else None
                self.failure_poll_observed = True

    def check_stream(self):
        value = self.process.poll()
        if value is not None:
            self.fail('process_exited', f'Temporary tunnel process exited (code {value}) before hosting could continue.', value)
        if self.reader_error_type:
            self.fail('reader_error', 'Temporary tunnel log reader failed (' + self.reader_error_type + '); free hosting stopped. Process exit is not established.', value)
        if self.stdout_eof:
            self.fail('reader_closed', 'Temporary tunnel log stream closed while its process was still running; free hosting stopped.', value)

    def snapshot(self):
        with self.lock:
            value = self.process.poll()
            result = {'phase': self.phase, 'reason': self.reason, 'originObserved': self.origin_observed,
                      'registrationObserved': self.registration_observed, 'stdoutEOF': self.stdout_eof,
                      'readerErrorType': self.reader_error_type, 'processPoll': value if type(value) is int else None,
                      'readerFinished': not self.thread.is_alive(), 'readerCleanupChecked': self.reader_cleanup_checked,
                      'readerCleanupIncomplete': self.reader_cleanup_incomplete, 'failurePollObserved': self.failure_poll_observed, 'processPollAtFailure': self.poll_at_failure}
        if self.diagnostics:
            result.update(self.diagnostics.snapshot())
            if self.reader_cleanup_incomplete:
                result['rawBytesCaptured'] = None
                result['rawPrefixSha256'] = None
                result['rawCaptureFinalized'] = False
        return result

    def wait(self, children, clock=time.monotonic):
        deadline = clock() + REGISTRATION_SECONDS
        while clock() < deadline:
            self.check_stream()
            if any(p.poll() is not None for p in children if p is not self.process):
                self.fail('owned_child_exited', 'An owned service stopped during tunnel registration.')
            try:
                kind, value = self.events.get(timeout=min(.1, max(0, deadline - clock())))
            except queue.Empty:
                continue
            if kind == 'origin':
                origin = temporary_origin(value)
                if self.origin and self.origin != origin:
                    self.fail('origin_changed', 'Temporary tunnel address changed during startup.')
                self.origin = origin
            elif kind == 'registered':
                self.registered_at, quic = value
                if not quic:
                    self.fail('unexpected_protocol', 'Temporary tunnel did not register using the required QUIC protocol.')
            elif kind in ('reader_error', 'stdout_eof'):
                self.check_stream()
            if self.origin and self.registered_at is not None:
                self.check_stream()
                self.admitted.set()
                self.phase = 'health'
                return self.origin, self.registered_at
        self.fail('registration_timeout', 'Temporary tunnel did not register within 45 seconds. Some networks may not connect; no fallback was started.')

    def finish_reader(self, timeout=1):
        self.thread.join(timeout=timeout)
        complete = not self.thread.is_alive()
        with self.lock:
            self.reader_cleanup_checked = True
            self.reader_cleanup_incomplete = not complete
        return complete

    def ready(self):
        self.check_stream()
        self.phase = 'ready'
        self.startup_finished.set()


def check_children(children):
    if any(process.poll() is not None for process in children):
        raise RuntimeError('An owned service stopped. Free hosting will close all services it started.')


def curl_executable():
    if sys.platform == 'darwin':
        path = Path('/usr/bin/curl')
    elif sys.platform == 'win32':
        # Avoid shell aliases/PATH wrappers and environment-supplied SystemRoot.
        import ctypes
        buffer = ctypes.create_unicode_buffer(32768)
        size = ctypes.windll.kernel32.GetSystemDirectoryW(buffer, len(buffer))
        if not size or size >= len(buffer):
            raise RuntimeError('The Windows system directory could not be verified.')
        path = Path(buffer.value) / 'curl.exe'
    else:
        raise RuntimeError('HTTPS readiness supports only the admitted Mac/Windows platforms.')
    if not path.is_file():
        raise RuntimeError('Existing operating-system curl is required for strict HTTPS readiness. No tool will be downloaded.')
    return path


def probe_pair(origin):
    """Native OS DNS and config-independent curl run concurrently, each with a total 3s bound."""
    origin = temporary_origin(origin)
    host = urlsplit(origin).hostname
    def dns():
        script = "import socket,sys;\ntry:socket.getaddrinfo(sys.argv[1],443,0,socket.SOCK_STREAM);print('resolved')\nexcept socket.gaierror:print('negative')"
        try:
            result = subprocess.run([sys.executable, '-c', script, host], capture_output=True, timeout=PROBE_SECONDS)
        except subprocess.TimeoutExpired:
            return 'unexpected'
        return result.stdout.strip().decode('ascii', errors='replace') if result.returncode == 0 else 'unexpected'
    def curl():
        command = [str(curl_executable()), '-q', '--proto', '=https', '--silent', '--show-error', '--connect-timeout', '3', '--max-time', '3',
                   '--max-filesize', '65536', '--write-out', '\n%{http_code}', origin + '/coop/health']
        try:
            result = subprocess.run(command, capture_output=True, timeout=PROBE_SECONDS)
        except subprocess.TimeoutExpired:
            return {'exit': None, 'status': None, 'json': None}
        raw, _, status = result.stdout.rpartition(b'\n')
        try:
            value = json.loads(raw) if len(raw) <= 65536 else None
        except ValueError:
            value = None
        return {'exit': result.returncode, 'status': int(status) if status.isdigit() else None,
                'json': value if isinstance(value, dict) else None}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(dns), pool.submit(curl)
        return a.result(), b.result()


def wait_public_ready(origin, registered_at, launch_id, children, probe=probe_pair,
                      clock=time.monotonic, sleep=time.sleep, notify=print, reader=None):
    temporary_origin(origin)
    deadline = registered_at + READINESS_SECONDS
    next_check = registered_at
    next_progress = registered_at + 30
    while clock() < deadline:
        if reader:
            reader.check_stream()
        check_children(children)
        if clock() < next_check:
            sleep(min(.1, next_check - clock()))
            continue
        if clock() >= next_progress:
            notify('Still waiting for temporary HTTPS signaling. Some networks may not connect.')
            next_progress += 30
        if deadline - clock() < PROBE_SECONDS:
            break
        dns, response = probe(origin)
        if reader:
            reader.check_stream()
        check_children(children)
        value = response['json']
        if response['exit'] == 0 and response['status'] == 200 and isinstance(value, dict):
            valid = (value.get('ok') is True and value.get('service') == 'bo1z-local-signaling'
                     and type(value.get('protocolVersion')) is int and value['protocolVersion'] == 2
                     and value.get('transportProtocol') == PROTOCOL and value.get('gameAssets') is False
                     and value.get('launchId') == launch_id)
            if not valid or dns != 'resolved' or clock() > deadline:
                raise RuntimeError('Public signaling health did not match this owned service. Refusing to open the game.')
            return origin
        if response['exit'] != 6 or dns not in ('negative', 'resolved'):
            raise RuntimeError('Temporary HTTPS health returned an unexpected response or connection error. Free hosting stopped; no fallback was started.')
        next_check += INTERVAL_SECONDS
    raise RuntimeError('Temporary HTTPS signaling was not ready within 120 seconds. Some networks may not connect. Try local/LAN play; no paid fallback was started.')
