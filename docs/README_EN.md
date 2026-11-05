# Getting started · English

c_Obsidian 0.2.1 is a standalone local companion for an Obsidian Markdown
vault. It includes a CLI, a loopback HTTP API, four explainable maps and an
image gallery. It does not install Obsidian or the Ideaverse plugin.

[Changing the login and password on MikroTik](ACCOUNTS_EN.md).
For container HTTPS, read the [RouterOS deployment notes (Russian)](ROUTEROS_HTTPS_RU.md)
and the [deployment guide (Russian)](DEPLOYMENT_RU.md).

Run from a **local** copy with Python 3.10+; no third-party packages required:

```powershell
py -3 -B obsidian.py --lang en serve --write --open
```

The demo has 47 fictional notes and three original illustrations. Select
**RU · EN · 中文** in the sticky top bar. The entire menu, map names, forms,
tooltips and messages change language. Note contents retain their original
language. The browser remembers the interface language.

- **Emergence** places notes in five levels, by date or folder.
- **Starfield** groups notes by their nearest selected hub.
- **Gravity** draws the levels in concentric rings.
- **Sensemakers** shows four roles based on headings, map type and tasks.
- **Images** shows local PNG, JPEG, GIF and WebP files embedded in notes.

Select a node to see why it has that level, its links and original text. Use
**+ New note** with a path such as `Inbox/My idea.md`; existing files are never
overwritten. Use **+ Image** to add a file to `assets/`, then include the displayed
`![[assets/photo.jpg]]` text in a note. Images appear in the gallery after refresh.

Your own vault:

```powershell
py -3 -B obsidian.py --vault "C:\MyNotes" --lang en serve --write --open
```

Omit `--write` for read-only HTTP access. Stop with `Ctrl+C` in the server's
terminal. The CLI `create` and `photo` commands explicitly add new files.
Scanning never changes notes. There is no API for replacing or deleting files.

The server only binds to `127.0.0.1`, uses a per-run bearer token and checks Host
and Origin. It makes no cloud, AI, CDN or remote image requests. Do not share the
launch URL printed when `--open` is omitted. Do not run code from SMB directly;
copy the documented minimal module files to a local folder and verify SHA-256.

This is a first version with its own [level policy](POLICY.md), not an exact
reimplementation of Ideaverse. No 3D or Bases support. Timeline playback shows
creation dates with **current** links, not historical link evolution. Dates
come from the scalar `created` field or a date in the filename, never filesystem
timestamps. Only simple frontmatter and a Markdown link subset are supported.
Each scan reads and hashes all notes, then reuses cached parsing where possible.
Limits: 20,000 notes, 2 MiB per note, 12 MiB per image; large vaults are untested.
Protected and hidden directories and linked paths are excluded.

[CLI reference](CLI.md) · [API reference](API.md) · [OpenAPI](../openapi.json)

Inspired by [Nick Milo's Maps of the Ideaverse](https://github.com/nickmilo/ideaverse-maps).
No upstream source code or screenshots are bundled. The included illustrations
are original demo assets. c_Obsidian CLI is separate from the
[official Obsidian CLI](https://help.obsidian.md/cli).

To every user, contributor and friend of the project: thank you for being here!
Thank you for your ideas, feedback, translations, testing and support.
