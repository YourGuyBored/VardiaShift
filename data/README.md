This folder is a placeholder so the directory exists in a fresh checkout.

At runtime VardiaShift does NOT store user data here. The database, backups, QR
codes and exports live in a per-user application-data folder:

* Windows: %LOCALAPPDATA%\VardiaShift
* macOS:   ~/Library/Application Support/VardiaShift
* Linux:   ~/.local/share/VardiaShift (or $XDG_DATA_HOME/VardiaShift)

Override with the VARDIASHIFT_DATA_DIR environment variable if needed.
