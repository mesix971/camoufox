# P4 — Network-Layer Fingerprint Patches

Four patches that extend Camoufox's fingerprint control down to the transport
and TLS layers. These exist because modern bot-detection (DataDome,
Cloudflare Bot Management, Akamai Bot Manager, Imperva, PerimeterX) correlates
application-layer spoofing with transport-layer reality — if your
`navigator.userAgent` says Chrome but your HTTP/2 SETTINGS look like Firefox,
you get flagged.

## Patch inventory

| File | Target | Effort to fix-up |
| --- | --- | --- |
| `patches/http2-settings-spoofing.patch` | `netwerk/protocol/http/Http2Session.cpp` | **low** — one C++ file, MaskConfig already available |
| `patches/tls-extensions-spoofing.patch` | `security/nss/lib/ssl/ssl3ext.c` | **medium** — NSS is C; uses env var bridge |
| `patches/tls-grease-disable.patch` | `security/nss/lib/ssl/tls13con.c`, `ssl3ext.c`, `ssl3con.c` | **medium** — depends on previous patch |
| `patches/creepjs-script-bypass.patch` | `dom/script/ScriptLoader.cpp` + `dom/script/moz.build` | **low** — one C++ file |

## Honest disclaimers

**These patches ship without line-number verification.** They were written
against Firefox 142.x source structure from documentation, not against a
checked-out tree. Expect to:

1. Apply with `make patch patches/<name>.patch` and see which hunks fail.
2. For each failure, open the target file and locate the surrounding
   context by the comments I left in the patch.
3. Re-apply with `patch -p1 --fuzz=3 < patches/<name>.patch` if hunks are
   close but off by a few lines.
4. For hunks that don't find their context at all, edit the Firefox source
   directly to achieve the documented intent, then regenerate the patch
   (see [WORKFLOW.md](WORKFLOW.md)).

## Application order

Camoufox applies patches alphabetically. Current filenames place these
correctly relative to existing patches:

```
creepjs-script-bypass.patch     ← P4.4 (depends on network-patches.patch
                                         for MaskConfig include pattern)
http2-settings-spoofing.patch   ← P4.1 (depends on network-patches.patch
                                         for moz.build LOCAL_INCLUDES)
tls-extensions-spoofing.patch   ← P4.2 (defines camoufox_tls_* C helpers)
tls-grease-disable.patch        ← P4.3 (uses helpers from P4.2 — applies after)
```

## MaskConfig plumbing

The C++ patches (H2, creepjs) use the existing pattern:

```cpp
if (auto value = MaskConfig::GetUint32("http2:settings:initialWindowSize")) {
    myValue = value.value();
}
```

The NSS/C patches use env vars populated by the Python launcher. The
pythonlib needs a small addition: when `launch_options(config=...)` sees
TLS keys, it should also set the companion env vars:

```python
# launcher populates these from the MaskConfig dict:
os.environ["CAMOUFOX_TLS_EXT_ORDER"] = ",".join(config["tls:extensions:order"])
os.environ["CAMOUFOX_TLS_GREASE"] = "0" if config["tls:grease:enabled"] is False else "1"
os.environ["CAMOUFOX_TLS_EXT_SHUFFLE"] = "1" if config["tls:extensions:shuffle"] else "0"
```

This bridge lives in `pythonlib/camoufox/utils.py` — add it next to the
existing `CAMOU_CONFIG_*` population code around line 60.

## Testing

After applying, verify handshake behaviour with:

```bash
make run args="--headless https://tls.peet.ws/api/all"
# Inspect the JSON: tls.ja4, http2.sent_frames, etc.
```

Compare against a stock Firefox 142 on the same host to confirm the JA4
and H2 fingerprints match (when no MaskConfig overrides) or differ as
expected (when overrides are set via a preset).

## Python integration

`fpgen` already supports P4 via optional Profile fields and named presets:

```python
import fpgen
p = fpgen.generate(os="windows")
fpgen.apply_preset(p, "firefox-142-stock")   # stamps H2/TLS values
# or manually:
p.tls_extensions_order = ["0", "23", "10", "51", "43", "13"]
p.tls_grease_enabled = False
cfg = fpgen.to_camoufox_config(p)
```

Profiles without P4 fields emit no P4 keys — Firefox uses its built-in
defaults, which is the correct behaviour for 99% of use cases.

## What's intentionally NOT included

- **Cipher-suite reordering**: `tls:cipherSuites:order` is in the schema but
  no patch consumes it yet. NSS's cipher selection is separately tunable
  via `SSL_CipherPrefSet`; if you need this, patch
  `security/manager/ssl/nsNSSComponent.cpp` to call `SSL_CipherPrefSet`
  for each entry.
- **HPACK dynamic-table priming**: HTTP/2 servers can fingerprint which
  headers a client primes in its HPACK dynamic table. Firefox's primer is
  fixed; changing it is intrusive and not worth it for most use cases.
- **Creepjs fake-score injection**: the patch currently BLOCKS known fingerprint
  scripts; faking a score is a richer behaviour (inject a shadow global
  that returns a plausible but varying score) and requires DOM injection
  plumbing. Left for a follow-up.
