"""Load the pinned archive handler with one in-memory portable path-key fix."""
import hashlib
from pathlib import Path
from types import ModuleType
from uuid import uuid4

PRISTINE_SERVE_SHA256 = 'fd10d2aa113172e1dfef3310dec53a5293e24369879ffb6c6a4db2c698056c30'
ORIGINAL_SELECTOR = 'str(dest.relative_to(ROOT))'
PORTABLE_SELECTOR = 'dest.relative_to(ROOT).as_posix()'


def load_archive_replay(root):
    """Reject edited archive code; preserve its ROOT, __file__ and HTTP logic."""
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('Archive root must be a directory')
    source_path = (root / 'serve.py').resolve(strict=True)
    if source_path.parent != root:
        raise ValueError('Archive serve.py must remain inside its root')
    original = source_path.read_bytes()
    if hashlib.sha256(original).hexdigest() != PRISTINE_SERVE_SHA256:
        raise ValueError('Archive serve.py differs from the pinned pristine source; restore the reviewed original before launching')
    source = original.decode('utf-8')
    if source.count(ORIGINAL_SELECTOR) != 1:
        raise ValueError('Expected exactly one reviewed archive transport path selector')
    portable = source.replace(ORIGINAL_SELECTOR, PORTABLE_SELECTOR, 1)
    # Each caller gets independent globals. Do not register or replace sys.modules.
    module = ModuleType('_bo1z_archive_replay_' + uuid4().hex)
    module.__file__ = str(source_path)
    exec(compile(portable, str(source_path), 'exec'), module.__dict__)
    if module.ROOT != root:
        raise ValueError('Archive handler ROOT differs from the requested boundary')
    module.__archive_source_sha256__ = PRISTINE_SERVE_SHA256
    module.__archive_path_normalization__ = 'relative transport encoding key as_posix only'
    return module
