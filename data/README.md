# Benchmark data

`frozen/wordle_answers_2022.txt` contains the 2,315 original 2022 solution words and
`frozen/wordle_extra_guesses_2022.txt` contains the 10,657 additional legal guesses.
Both are normalized to unique lowercase five-letter ASCII words.

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
  --output data/frozen/dynamic_master_5letter.txt
```

Then generate the fully materialized development and evaluation manifests with
`uv run python -m benchmark generate-manifests --config configs/benchmark.yaml`.

Frozen manifest SHA-256 hashes:

- `dev_historical.jsonl`: `fc4193c922dbcd1edbe10a86ea6437be49777661884db79948ef7fd6faf0d5d7`
- `eval_historical.jsonl`: `037b5038ba3d4f0cd560eabea51baf6fb7b51b32a5c701d71ea4c024c0922e49`
- `dev_dynamic.jsonl`: `607bed09fa274828cf32b3da2af7a01698c6d92dfb078c8201b3391a8add11bf`
- `eval_dynamic.jsonl`: `f2acea506f7583336e6ac052da78ff56bdee5bdf77ea6e0d953ba4bf8a882280`
