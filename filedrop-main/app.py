import hashlib
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, send_from_directory

from config import Config
from torrent_manager import ensure_torrent, torrent_path_for

app = Flask(__name__)
app.config.from_object(Config)

FILES_DIR = Path(Config.FILES_DIR).resolve()
FILES_DIR.mkdir(parents=True, exist_ok=True)

# (relative path, mtime, size) -> sha256, so big files are only hashed once
_checksums = {}


def is_hidden(rel: Path) -> bool:
    return any(part.startswith(".") for part in rel.parts)


def human_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    size = float(num_bytes)
    for unit in ("KB", "MB", "GB"):
        size /= 1024
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"


def list_files():
    items = []
    for path in FILES_DIR.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(FILES_DIR)
        if is_hidden(rel) or path.name.endswith(".torrent"):
            continue
        stat = path.stat()
        torrent_status = "Torrent not generated"
        try:
            _, torrent_status = ensure_torrent(path)
        except (RuntimeError, OSError) as exc:
            torrent_status = str(exc)
        
        items.append(
            {
                "path": rel.as_posix(),
                "size": stat.st_size,
                "size_label": human_size(stat.st_size),
                "modified": datetime.fromtimestamp(stat.st_mtime),
                "torrent_available": torrent_path_for(path).is_file(),
                "torrent_status": torrent_status,
            }
        )
    items.sort(key=lambda f: f["modified"], reverse=True)
    return items


def resolve_file(filename: str):
    """Return (relative path, absolute path) for a servable file, or 404."""
    rel = Path(filename)
    if rel.is_absolute() or is_hidden(rel):
        abort(404)
    target = (FILES_DIR / rel).resolve()
    if FILES_DIR not in target.parents or not target.is_file():
        abort(404)
    return rel, target


@app.route("/")
def index():
    files = list_files()
    total = human_size(sum(f["size"] for f in files))
    return render_template(
        "index.html",
        title=Config.TITLE,
        files=files,
        total=total,
        files_dir=str(FILES_DIR),
    )


@app.route("/download/<path:filename>")
def download(filename):
    rel, _ = resolve_file(filename)
    return send_from_directory(FILES_DIR, rel.as_posix(), as_attachment=True)


@app.route("/torrent/<path:filename>")
def download_torrent(filename):
    _, target = resolve_file(filename)
    torrent_file = torrent_path_for(target)
    if not torrent_file.is_file():
        try:
            ensure_torrent(target)
        except (RuntimeError, OSError):
            abort(503, description="Could not generate the torrent file. Check the server logs.")
    return send_from_directory(torrent_file.parent, torrent_file.name, as_attachment=True)


@app.route("/checksum/<path:filename>")
def checksum(filename):
    rel, target = resolve_file(filename)
    stat = target.stat()
    key = (rel.as_posix(), stat.st_mtime_ns, stat.st_size)
    if key not in _checksums:
        digest = hashlib.sha256()
        with open(target, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        _checksums[key] = digest.hexdigest()
    return jsonify(path=rel.as_posix(), sha256=_checksums[key])


@app.route("/healthz")
def healthz():
    return "ok"


if __name__ == "__main__":
    import logging

    from waitress import serve
    from discovery import ServiceAdvertisement

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(f"Serving {FILES_DIR} on http://{Config.HOST}:{Config.PORT}")
    print(f"qBittorrent Web UI: {Config.QBITTORRENT_URL or 'not configured'}")
    if not Config.TRACKER_URL:
        print("No tracker configured: torrents rely on DHT/PeX/Local Peer Discovery where supported.")
    advertisement = ServiceAdvertisement()
    advertisement.start()
    try:
        serve(app, host=Config.HOST, port=Config.PORT, threads=8)
    finally:
        advertisement.close()
