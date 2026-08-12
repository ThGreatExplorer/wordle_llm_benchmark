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

- `dev_historical.jsonl`: `dc941e3d9cd87d3124957f45898de258d046421219c10098ce0c603492e5e15f`
- `eval_historical.jsonl`: `49af93d015b3e7a1c83aba1832136dc2b4da6dafe1ca94b26ba7b16989d5acf3`
- `dev_dynamic.jsonl`: `6e93a8debde88562ff32735fceda4c9a875e6a9d4186c0d173bc82528c8467bc`
- `eval_dynamic.jsonl`: `d309ae4704863b6651185c9d12f4df22e79b7086269daeeac5433af2f2e83b38`
