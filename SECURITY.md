# Security

SUB/WAVE Lyrics only needs a station's public listener API and stream. It never needs the station
admin username or password. Do not add admin credentials to its environment.

Report vulnerabilities privately through GitHub's **Security → Report a vulnerability** feature.
Please include the affected version, deployment mode, reproduction steps, and expected impact.

The app contains no telemetry, advertising, or third-party analytics. Track metadata is sent to
LRCLIB solely to locate lyrics. Lyrics and lookup status are cached in the local SQLite volume.
