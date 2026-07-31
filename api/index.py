from pathlib import Path
import base64, zlib
_parts = Path(__file__).parent / "runtime_parts"
_code = "".join(p.read_text() for p in sorted(_parts.glob("part-*.txt")))
exec(zlib.decompress(base64.b64decode(_code)).decode("utf-8"), globals())
