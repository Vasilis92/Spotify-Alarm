# 🎶 Spotify Alarm

A beautiful desktop alarm that plays your chosen **Spotify** playlist, album, or track at scheduled times.

> 👉 **[Download the latest Windows installer](../../releases/latest)**  
> (No source code required—just run the installer.)

---

## 📸 Screenshot

![Spotify Alarm screenshot](docs/screenshot-dark-theme.png)

---

## Requirements

* **Windows 10/11 (64-bit)**
* **Spotify Desktop** installed and logged in
* A free **Spotify Developer** app to obtain Client ID and Secret  
  (takes ~2 minutes, instructions below)

---

## One-time Spotify setup

1. Go to [https://developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
2. Click **Create App** and give it a name (e.g. *Spotify Alarm*).
3. In **Settings → Redirect URIs** add **`http://127.0.0.1:8080/callback`** (exactly this).
4. Save. Copy your **Client ID** and **Client Secret**.

---

## Installation

1. Download the installer from **[Releases](../../releases)**.
2. Run `SpotifyAlarmSetup_x.y.z.exe`.
3. When prompted, paste:
   * **Client ID**
   * **Client Secret**
   * *(Optional)* Default Spotify URI (playlist/album/track).
4. Launch **Spotify Alarm** from the Start menu or desktop shortcut.

> You can enable **auto-start on login** directly in the installer.

---

## Using the App

* Add alarms with **Time**, **Label**, **URI**, and **Volume**.
* If an alarm has no URI, the default URI (from the installer) will be used.
* The app can **auto-launch Spotify** when an alarm triggers.
* Choose a theme (Dark, Light, or Nord) from the top-right theme selector.

---

## Verify your download (optional)

Every release lists a SHA-256 checksum.

PowerShell example:

```powershell
Get-FileHash .\SpotifyAlarmSetup_x.y.z.exe -Algorithm SHA256
