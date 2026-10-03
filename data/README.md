This folder is a placeholder so the directory exists in a fresh checkout.

At runtime Shiftora does NOT store user data here. The database, backups, QR
codes and exports live in a per-user application-data folder:

* Windows: %LOCALAPPDATA%\Shiftora
* macOS:   ~/Library/Application Support/Shiftora
* Linux:   ~/.local/share/Shiftora (or $XDG_DATA_HOME/Shiftora)

Override with the SHIFTORA_DATA_DIR environment variable if needed.
