"""Complete local JSON snapshots. Callers own any locking or reset cancellation."""
import json
import os
from pathlib import Path


# @llr TLLR123
def write_json(path, value):
    """Replace a complete snapshot atomically; callers must serialize writes sharing the temporary path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)
