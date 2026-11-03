# c-obsidian-explainable-v1

This policy is independent from Maps of the Ideaverse. No AI is used.
It is an explainable prototype, not a semantic truth about a note.

## Links and dates

Only resolved links between distinct Markdown notes count. Repeated links
are deduplicated. Self-links and unresolved links do not raise the level.
Code spans and fenced code blocks are excluded from link extraction. Wiki
aliases, heading fragments and simple Markdown URLs are supported. Unique
filenames can resolve across folders. Ambiguous filenames stay unresolved.
Relative Markdown links are normalized, while direct API file paths reject
`..` and protected or linked paths. Complex Markdown destinations, YAML arrays
and aliases are not fully implemented.

Date priority: configured scalar property (default `created`) → `YYYY-MM-DD`
in filename → unknown. Invalid dates are unknown. Filesystem timestamps are
never substituted. The timeline uses current graph links, not link history.

## Five levels, checked in order

1. No resolved incoming or outgoing links → **L1**, even if type is `home`.
2. Connected note with `type: home` or `type: hub` → **L5**.
3. At least two outgoing links to content-map candidates → **L4**.
4. Content-map candidate → **L3**.
5. Any remaining connected note → **L2**.

A content-map candidate is `type: moc` or `type: map` with at least one outgoing
link, or any note with five or more distinct outgoing links. Candidates are
determined before levels. This avoids circular level recursion.

## Starfield

Select up to six connected hubs by descending level, degree, then path.
Multi-source breadth-first traversal assigns each reachable note to the
nearest selected hub. Equal-distance ties are deterministic. Unreachable
notes form folder clouds. The prototype may select a well-connected ordinary
note as one of the six centers; the UI does not infer a semantic topic.

## Sensemakers

Top down = at least three Markdown headings, a map candidate or `home`/`hub` type.
Express = at least one Markdown checkbox or a top folder named `Efforts`,
`Projects`, `Проекты` or `项目` (case-insensitive). Otherwise reflect.

| Direction | Reflect | Express |
|---|---|---|
| Top down | Synthesizer | Producer |
| Bottom up | Inner guide | Creative |

First-person clues (Russian, English, Chinese) are reported but do **not** affect
the role in v1. Headings and checkbox counts are simple text heuristics.

## Read and write boundaries

No recursive selection of the AI_WorckBook project root. Hidden directories,
`Pass`, `Private`, `Runtime`, symlinks and junctions are excluded. Explicit
API paths reject traversal, ADS, reserved Windows names and active image
formats. These checks are a local trust boundary, not a defense against an
adversarial process concurrently replacing filesystem entries. Do not choose
a vault that untrusted local software can modify.

No updates or deletes; create uses exclusive file creation. No model calls,
external image fetches or telemetry. Scan reads and hashes files on every call;
only parsed note structures are cached in memory. Missing, unreadable or
oversized notes appear as warnings, not a successful complete scan.
