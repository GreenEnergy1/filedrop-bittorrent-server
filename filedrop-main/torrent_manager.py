"""Torrent generation and optional qBittorrent Web API seeding integration."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests

from config import Config

logger = logging.getLogger(__name__)
_registered_torrents: set[str] = set()


def torrent_path_for(file_path: Path) -> Path:
    return file_path.with_name(file_path.name + ".torrent")


def generate_torrent(file_path: Path) -> Path:
    """Create a sidecar .torrent once; preserve it until the source file changes."""
    output = torrent_path_for(file_path)
    if output.exists() and output.stat().st_mtime_ns >= file_path.stat().st_mtime_ns:
        return output

    if output.exists():
        output.unlink()
    executable = shutil.which(Config.TORRENT_CREATOR) or Config.TORRENT_CREATOR
    command = [executable, "-o", str(output)]
    if Config.TRACKER_URL:
        command.extend(["-a", Config.TRACKER_URL])
    command.append(str(file_path))

    try:
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=3600)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Torrent creator not found. Install it with: "
            "python -m pip install py3createtorrent"
        ) from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise RuntimeError(f"Torrent creation failed: {detail}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Torrent creation timed out.") from exc

    if not output.is_file():
        raise RuntimeError("Torrent creator finished without producing a .torrent file.")
    return output


def add_to_qbittorrent(torrent_file: Path, save_path: Path) -> tuple[bool, str]:
    """Ask qBittorrent to load and seed a torrent through its Web API."""
    if not Config.QBITTORRENT_URL:
        return False, "qBittorrent Web UI is not configured; download the .torrent to seed manually."

    session = requests.Session()
    base = Config.QBITTORRENT_URL.rstrip("/") + "/"
    parsed_base = urlsplit(base)
    origin = f"{parsed_base.scheme}://{parsed_base.netloc}"
    headers = {"Origin": origin, "Referer": base}
    try:
        login = session.post(
            urljoin(base, "api/v2/auth/login"),
            data={"username": Config.QBITTORRENT_USERNAME,
                  "password": Config.QBITTORRENT_PASSWORD},
            headers=headers,
            timeout=8,
        )
        legacy_login_succeeded = login.status_code == 200 and login.text.strip() == "Ok."
        current_login_succeeded = login.status_code == 204 and bool(session.cookies)
        if not (legacy_login_succeeded or current_login_succeeded):
            logger.warning(
                "qBittorrent login failed: HTTP %s, response %r",
                login.status_code,
                login.text.strip()[:160],
            )
            return False, (
                f"Could not log in to qBittorrent Web UI (HTTP {login.status_code}); "
                "check its Web UI settings."
            )

        with torrent_file.open("rb") as handle:
            response = session.post(
                urljoin(base, "api/v2/torrents/add"),
                data={"savepath": str(save_path), "paused": "false",
                      "skip_checking": "false"},
                files={"torrents": (torrent_file.name, handle, "application/x-bittorrent")},
                headers=headers,
                timeout=30,
            )
        addition_succeeded = (
            response.status_code in (200, 204)
            and response.text.strip() in ("Ok.", "")
        )
        if response.status_code == 200 and not addition_succeeded:
            try:
                result = response.json()
            except ValueError:
                result = None
            if isinstance(result, dict):
                successes = result.get("success_count")
                failures = result.get("failure_count")
                addition_succeeded = (
                    isinstance(successes, int)
                    and successes > 0
                    and isinstance(failures, int)
                    and failures == 0
                )
        if response.status_code == 409:
            logger.info("Torrent is already present in qBittorrent: %s", torrent_file.name)
            return True, "Torrent is already in qBittorrent."
        if not addition_succeeded:
            logger.warning(
                "qBittorrent rejected torrent upload: HTTP %s, response %r",
                response.status_code,
                response.text.strip()[:160],
            )
            return False, f"qBittorrent rejected the torrent (HTTP {response.status_code})."
        return True, "Added to qBittorrent for seeding."
    except requests.RequestException as exc:
        logger.warning("qBittorrent API request failed: %s", exc)
        return False, "qBittorrent Web UI is unreachable; the .torrent is still available."


def ensure_torrent(file_path: Path) -> tuple[Path | None, str]:
    """Generate and, when configured, register a file with qBittorrent."""
    torrent_file = generate_torrent(file_path)
    key = str(torrent_file.resolve())
    if key in _registered_torrents:
        return torrent_file, "Torrent is registered with qBittorrent."
    ok, message = add_to_qbittorrent(torrent_file, file_path.parent)
    if ok:
        _registered_torrents.add(key)
    return torrent_file, message
