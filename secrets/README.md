# Private Mail Configuration

`mail_private.sqlite3` and `mail_private.key` are created locally by:

```powershell
py -3.11 scripts\migrate_private_config.py
```

They contain recipient and company email data encrypted with Fernet and are ignored by Git.
For GitHub Actions, copy the JSON payload into the `MAIL_PRIVATE_CONFIG_JSON` repository secret and
use the matching Fernet key in `MAIL_PRIVATE_CONFIG_KEY`. Do not commit either value.
