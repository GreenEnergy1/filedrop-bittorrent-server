# FileZ

A Windows-friendly Flask file server with automatic BitTorrent torrent-file generation and optional qBittorrent background seeding. On first run, choose the folder to share (for example, a folder on your Desktop or in Documents). Files appear with their size, date, direct and BitTorrent download links, and an on-demand SHA-256 checksum. It runs through Waitress and can be installed as a background Windows service.

## Features

- Lists every file in `files/` (subfolders included), newest first
- One-click direct downloads
- Automatic `.torrent` generation for shared files
- BitTorrent download links beside direct downloads
- Optional automatic seeding through the qBittorrent Web API
- Filter box to find a file by name
- SHA-256 checksum on request, handy for unsigned installers
- Hidden files (names starting with `.`) are never listed or served
- Path traversal is blocked
- Runs as a Windows service with automatic start and restart on crash

## Run it

**Windows**

```bat
run.bat
```

**Linux/macOS**

```bash
./run.sh
```

On first run, the launcher asks for the folder to serve. Enter its full path, or press Enter to use the default `files/` folder. The choice is saved in `settings.json`, and changes to that folder appear without restarting. Run `python setup.py` to choose a different folder later.

## Discovery client

The JavaScript desktop client is in [`client/`](client/). It scans the LAN for Filedrop servers and opens the selected server in the system browser. See [`client/README.md`](client/README.md) for development and packaging instructions. The Electron client targets Windows, macOS, and Linux; Android packaging is planned separately.

## Install as a Windows service

1. Download [NSSM](https://nssm.cc) and put `nssm.exe` on your `PATH`.
2. Open a terminal **as Administrator** in this folder.
3. Run:

```bat
install_service.bat
```

The script creates the virtual environment, asks which folder to serve, registers the `Filedrop` service (starts at boot, restarts if it crashes), writes logs to `logs\filedrop.log`, opens the firewall port, and starts it. To change the folder later, stop the service, run `python setup.py`, then restart it. To remove it, run `uninstall_service.bat`. Your files are not touched.

Manage it later with `nssm restart Filedrop`, `nssm stop Filedrop`, or the Services app.

## Configuration

Set these in a `.env` file in the project folder or as environment variables before starting. Existing process/system environment variables take precedence over `.env`. For a Windows service, the `.env` file is loaded from the project folder.

| Variable          | Default        | Purpose                          |
| ----------------- | -------------- | -------------------------------- |
| `FILEDROP_DIR`    | saved setup choice, otherwise `./files` | Folder to serve (overrides the saved choice) |
| `FILEDROP_HOST`   | `0.0.0.0`      | Interface to listen on           |
| `FILEDROP_PORT`   | `1080`         | Port                             |
| `FILEDROP_TITLE`  | `Filedrop`     | Heading shown on the page        |
| `FILEDROP_NAME`   | hostname-based Filedrop name | Friendly name advertised to discovery clients |
| `FILEDROP_TORRENT_CREATOR` | `py3createtorrent` | Torrent creation executable |
| `FILEDROP_TRACKER_URL` | empty | Optional announce URL for a tracker you actually operate |
| `FILEDROP_QBITTORRENT_URL` | `http://127.0.0.1:8080` | qBittorrent Web UI base URL |
| `FILEDROP_QBITTORRENT_USERNAME` | `admin` | qBittorrent Web UI username |
| `FILEDROP_QBITTORRENT_PASSWORD` | empty | qBittorrent Web UI password |

## BitTorrent setup (Windows)

1. Install qBittorrent from [qbittorrent.org](https://www.qbittorrent.org/).
2. In **Tools → Options → Web UI**, enable the Web UI and set its port to `8080`. Enable qBittorrent's option to start with Windows (or configure it as a separate Windows service) so it is available whenever Filedrop runs. Keep the Web UI bound to `127.0.0.1` when possible; it is an administrative interface, not the public download page. Set a strong username and password.
3. In **Tools → Options → BitTorrent**, enable Local Peer Discovery (PeX and DHT may also be enabled for trackerless torrents). Set seeding limits so torrents do not stop immediately.
4. Create a `.env` file beside `app.py` with the qBittorrent settings:

   ```dotenv
   FILEDROP_QBITTORRENT_URL=http://127.0.0.1:8080
   FILEDROP_QBITTORRENT_USERNAME=your-qbittorrent-username
   FILEDROP_QBITTORRENT_PASSWORD=your-qbittorrent-password
   ```

   `.env` is excluded from Git. Keep it private and use the same credentials configured in qBittorrent's Web UI.
5. Restart Filedrop. When the file list is opened, it creates a sidecar `<filename>.torrent` for each shared file and asks qBittorrent to add it using the existing file as the seed data. The generated `.torrent` files are hidden from the ordinary file listing.
6. Use the **BitTorrent** link to download a torrent file and open it in a BitTorrent client on another LAN device.

Install dependencies with `run.bat`; the requirements include `py3createtorrent`. If torrent creation fails, the row shows **Torrent unavailable** and the server log contains the cause.

**Tracker note:** the guide's example `http://SERVER-IP:6969/announce` only works if a tracker is actually running at that address. qBittorrent's Web UI on port 8080 is not a tracker. This implementation leaves the tracker unset by default and uses DHT/Peer Exchange/Local Peer Discovery where client settings and network policy permit. If you operate a tracker, set `FILEDROP_TRACKER_URL` to its real announce URL. For a strictly private LAN swarm, deploy and configure a LAN tracker rather than inventing an announce URL.

qBittorrent must be running for automatic background seeding. Filedrop can still generate and serve `.torrent` files without qBittorrent, but it cannot seed them itself. Do not expose the qBittorrent Web UI to the LAN or internet unless you have deliberately secured it.

The server advertises `_filedrop._tcp.local` over mDNS/DNS-SD while it is running. The advertisement includes its friendly name, persistent server ID, and port. The server ID is stored in `settings.json` and remains stable across restarts. Devices on networks that block multicast may not see the advertisement.

The Windows service installer allows the configured TCP port and mDNS UDP port 5353 through Windows Firewall for the local subnet. To change the service port, edit `PORT` at the top of `install_service.bat` before installing.

## Putting it on the internet

Filedrop has no login: anyone who can reach the page can see and download everything in the folder. Only put files there that you are happy to share. Discovery is not authentication. Keep the server on a trusted local network and do not forward its port from your router.

## Project structure

```
filedrop/
├── app.py                  # Flask app: page, download, checksum routes
├── config.py               # Settings read from environment variables
├── requirements.txt
├── templates/index.html    # The downloads page
├── static/style.css
├── files/                  # Put the files to share here
├── run.bat / run.sh        # Run in a console
├── install_service.bat     # Install as a Windows service (NSSM)
└── uninstall_service.bat
```
