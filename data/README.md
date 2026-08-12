# Benchmark data

`frozen/wordle_answers_2022.txt` contains the 2,315 original 2022 solution words and
`frozen/wordle_extra_guesses_2022.txt` contains the 10,657 additional legal guesses.
Both are normalized to unique lowercase five-letter ASCII words.

## Provenance

**Historical Wordle provenance:** these repository inputs are frozen copies of the
original pre-NYT 2,315-answer and 10,657-additional-guess lists described in
`DESIGN.md`. Their upstream retrieval URL was not recorded when the files were
introduced; the hashes below are therefore the authoritative project provenance.

**SCOWL provenance:** `raw/scowl_60_american.txt.gz` is the frozen level-60
American-English export used as input. See <https://wordlist.aspell.net/> for the
SCOWL project; the exact repository artifact is identified by its hash below.

**wordfreq provenance:** the dynamic intersection uses `wordfreq`'s English
`small` list through the version locked in `uv.lock` (currently 3.1.1).

SHA-256 provenance:

- `wordle_answers_2022.txt`: `5209b35f823f8b80f0404f863bd80df06d6a966c6eb1016d69f38badc6eed5d0`
- `wordle_extra_guesses_2022.txt`: `99be2e38dadf3e26952af7cb4d963f65b632d5de91aa99e5ce308e4dc9617b65`
- `scowl_60_american.txt.gz`: `9cd88b0a64ae43099330ced76ab9f9bf2b59eb89d717b81e1409f639003c35cb`
- `dynamic_master_5letter.txt`: `eb550131f527dfa497d98189256ed7a9eeea7129579f78d924073b51e10ed126`

`raw/scowl_60_american.txt.gz` is the SCOWL level-60 American English input. Build
the frozen dynamic vocabulary with:

```bash
uv run python scripts/build_dynamic_dictionary.py \
  --scowl data/raw/scowl_60_american.txt.gz \
  --answers data/frozen/wordle_answers_2022.txt \
  --output data/frozen/dynamic_master_5letter.txt \
  --force
```

Then generate the fully materialized development and evaluation manifests with
`uv run python -m benchmark generate-manifests --config configs/benchmark.yaml --force`.

Both commands refuse to overwrite frozen artifacts unless `--force` is explicit.

Frozen manifest SHA-256 hashes:

- `dev_historical.jsonl`: `f6e4ec45e9cdd183d6298961cf36011c1af531964f03b91f0d4d90757f07f8cc`
- `eval_historical.jsonl`: `3edd1a92371e6dd47a765d7dfddc19e6e526dee55f33f70dad1a684d163ef683`
- `dev_dynamic.jsonl`: `6d1d22d7d69499569571ae520bc919dfa802e359ad08acea4de1fb5faaa4506e`
- `eval_dynamic.jsonl`: `bb713167d14442df1286d2e46f1ee32c272a9d057a2738409d7eb3a5dcfab99f`

The `mvp-v4` migration changed only each manifest record's `benchmark_version` from
`mvp-v3`; payload fingerprints verify that all materialized game IDs, secrets,
pools, seeds, counts, and ordering remain identical.
