# Changing the login and password on MikroTik

[Русский](ACCOUNTS_RU.md) · [English](ACCOUNTS_EN.md) · [简体中文](ACCOUNTS_ZH.md)

## The c_Obsidian account inside the container

The `--action` commands require **0.2.1**. Publishing source does not upgrade an
existing 0.2.0 container: first arrange a separate upgrade to a verified image,
preserving `/state` and `/vault`. This account belongs to the website, not the
RouterOS administrator.

In the WinBox terminal, find the container name and open its shell:

```routeros
/container print
/container shell <container-name> user=app
```

Replace `<container-name>` with your exact c_Obsidian container name. Run the
following commands **inside the container**, at the `/app $` prompt:

```sh
cd /app
# Change an existing user's password:
python /app/auth_store.py --state /state --username ExistingUser --action password --lang en
# Change the username and set a new password together:
python /app/auth_store.py --state /state --username ExistingUser --action rename --new-username NewUser --lang en
```

Replace the example names. Usernames have 3–64 characters from `A–Z`, `a–z`,
`0–9`, `.`, `_`, `-`; passwords have 8–256 characters. Enter the new password
twice. Input is hidden. If the entries differ, nothing changes. Choose prompt
language with `--lang ru|en|zh`; use `en` if the RouterOS terminal cannot display
other scripts. The utility stops if protected input is unavailable.

For **initial provisioning**, use `--action create` (the default). It never
overwrites an existing accounts.json. Password changes and renames preserve
other users, atomically replace the hash file and invalidate old sessions.
Sign in again with the new credentials; a container restart is unnecessary.
Never put passwords in command arguments, chat or reports. The plaintext
password is not saved: store it yourself in your password manager.

If `.accounts-update.lock` exists, an earlier operation may be unfinished.
Inspect the processes and operation state before removing a lock.

## The RouterOS / WinBox user

This is a separate account. Open **System → Users** in WinBox and select the
intended user. Change **Name** to rename the login. Use **Password / Change
Password** in that user's settings and enter the new password twice; the button
label depends on WinBox version. Save, then reconnect with the new credentials.
Do not change Group/Policies merely to change a password.

Changing a RouterOS account does not change the c_Obsidian login, or vice versa.

## Thank you

To every user, contributor and friend of the project: thank you for being here!
Thank you for your ideas, feedback, translations, testing and support.
