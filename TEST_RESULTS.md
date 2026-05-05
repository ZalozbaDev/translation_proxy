# Package A test results

Validation evidence for the sotra + LibreTranslate combination proxy.

## Environment

- Date: 2026-04-28
- Proxy: `package-a-sotra-libretranslate/proxy`
- Stack: `docker compose up -d` from `package-a-sotra-libretranslate`
- sotra: `ZalozbaDev/sotra_modele`, branch `workaround_jitsi_limitation`
- LibreTranslate: `libretranslate/libretranslate:v1.9.5`

## Unit and API tests

Command:

```sh
cd package-a-sotra-libretranslate/proxy
pytest -q
```

Result:

```text
22 passed
```

Coverage:

- route selection for every contract scenario
- LibreTranslate-compatible JSON/form API behavior
- mocked sotra and LibreTranslate backend calls
- `/languages`, `/detect`, `/frontend/settings`, and `/health`
- unsupported route error handling

## Live integration tests

Command:

```sh
cd package-a-sotra-libretranslate
docker compose up -d
cd proxy
pytest -q -m live tests/test_live.py -v
```

Result:

```text
15 passed
```

Covered live scenarios:

| Scenario | Example | Expected route |
| --- | --- | --- |
| fully via sotra | `hsb -> de`, `de -> hsb`, `dsb -> hsb`, `hsb -> dsb` | `sotra` |
| partial sotra / partial LibreTranslate | `cs -> hsb`, `cs -> de` | `sotra` or `libretranslate` |
| LibreTranslate only | `de -> en`, `en -> de`, `pl -> en` | `libretranslate` |
| chained | `hsb -> en`, `dsb -> en`, `en -> hsb`, `pl -> dsb` | two-hop via pivot |
| unsupported | `en -> ja` | HTTP 400 |
| language matrix | required target pairs in `/languages` | present |

## All-pairs live smoke

Live smoke over the required language set:

```text
hsb, dsb, de, cs, pl, en
```

Result:

```text
30/30 successful directions
```

Representative outputs:

```text
hsb -> de  'Das ist ein Test.'
hsb -> en  "That's a test."
en  -> hsb 'To je test.'
pl  -> dsb 'To jo test.'
```

This verifies all requested translation directions between `hsb`, `dsb`,
`de`, `cs`, `pl`, and `en` through the combined proxy.

