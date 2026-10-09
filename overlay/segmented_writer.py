"""Private assets-only send candidate; no ownership of the request socket.

Each send argument is at most 64KiB. This bounds buffer size, not blocking-call
duration. The original server/socket timeout and outer fixture watchdog apply.
No archive logic, shutdown path, socket option or global method is changed.
"""
import errno
import io
import os
from socketserver import _SocketWriter


SEGMENT_BYTES = 65536


class SegmentedSocketWriter(io.BufferedIOBase):
    def __init__(self, sock):
        super().__init__()
        self._sock = sock

    def writable(self):
        return True

    def fileno(self):
        return self._sock.fileno()

    def write(self, data):
        if self.closed:
            raise ValueError('write to closed writer')
        # Byte addressing handles typed contiguous buffers without copying them.
        with memoryview(data) as original, original.cast('B') as view:
            size, offset = view.nbytes, 0
            while offset < size:
                end = min(size, offset + SEGMENT_BYTES)
                with view[offset:end] as segment:
                    sent = self._sock.send(segment)
                if type(sent) is not int or sent < 0 or sent > end - offset:
                    raise OSError(errno.EIO, 'socket returned an invalid send count')
                if sent == 0:
                    raise BrokenPipeError(errno.EPIPE, 'socket send made no progress')
                offset += sent
            return size


def make_segmented_handler(actual_handler, *, require_windows=True):
    """Use the one original handler construction; replace only setup's writer."""
    if require_windows and os.name != 'nt':
        raise RuntimeError('This private transfer candidate is Windows-only')

    class Handler(actual_handler):
        def setup(self):
            super().setup()
            previous = self.wfile
            if type(previous) is not _SocketWriter or previous._sock is not self.connection:
                raise RuntimeError('Expected the unchanged standard-library socket writer')
            self.wfile = SegmentedSocketWriter(self.connection)
            # _SocketWriter.close only closes its IO wrapper; request is owned by
            # the server. The replacement has the same BufferedIOBase behavior.
            previous.close()

    return Handler
