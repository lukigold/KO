# KO generator

Turns a layout into a complete keyboard package ([docs/contracts/generator.md](../docs/contracts/generator.md)).
The Python generator itself comes next in P1 (GEN-001); what exists today is its input side.

| Path | Content |
|---|---|
| `configurator/check_builder.js`, `check_schema.py` | Checks for the page and for layout files |
| `configurator/index.html` | Layout builder: one self-contained web page. Pick size, staggered or grid, standard and legends, connection, switch types (several at once), per-key light and underglow, add extra key rows or columns with functions, then save or copy the KO layout file |
| `schema/ko-layout-3.schema.json` | JSON Schema of the KO layout file v3, the generator's input (`ko-layout-1`, `-2`: older versions) |
| `switches/compat.py`, `compat.json` | Which switch types share a key position (soldered or hot-swap, with or without the per-key LED), from the footprint geometry. Running it also refreshes the data inside the layout builder page |
| `examples/ko-75-iso-ch.json` | The owner's build as in SYS-01: 75 %, ISO-CH, staggered, wireless, hot-swap Choc v1, per-key RGB (file v3) |

## Using the layout builder

Open `configurator/index.html` in a browser (no server needed), or use the published copy on claude.ai, where builds
can also be saved on the page for Claude to pick up. In a plain browser, "Download .json" saves the file directly.

## Checks (GEN-011)

`check_builder.js` opens the page in headless Chromium (Playwright) and, for both layout styles and every size and standard with extra rows
and columns, checks for overlapping keys and duplicate ids, compares the KLE export with the KO file and reads the KO
file back. `check_schema.py` validates layout files against the schema.

```bash
node generator/configurator/check_builder.js /tmp/ko-layouts.json
```

```bash
python3 generator/configurator/check_schema.py /tmp/ko-layouts.json generator/examples/ko-75-iso-ch.json
```
