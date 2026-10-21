# AGENTS.md

Instructions for coding agents working in this repository. Humans should start with [README.md](README.md).

## What this is

`rsabias` is the research tool behind "Biased RSA private keys: Origin attribution of GCD-factorable keys" (ESORICS 2020, https://arxiv.org/abs/2009.06700). It estimates which library, smartcard or HSM generated an RSA **private** key, using a pre-trained Bayes model over 26 groups of sources. It also has the pipeline that built that model from a dataset of over 150 million keys.

## Which instructions to read

| Goal | Read |
|---|---|
| Classify or analyse someone's RSA keys | [.claude/agents/rsa-key-analyst.md](.claude/agents/rsa-key-analyst.md): background, running the classifier, reading and combining reports, how to report results |
| Get keys into the format the tool accepts | [.claude/skills/prepare-rsa-keys/SKILL.md](.claude/skills/prepare-rsa-keys/SKILL.md) and its `scripts/normalize_keys.py` |
| CLI tasks and parameters, supported key formats | [README.md](README.md) |
| Model, groups, features, distributions | [rsabias/model/readme.md](rsabias/model/readme.md) |
| Report table generation | [rsabias/classification_table_template/](rsabias/classification_table_template) |

In Claude Code, `rsa-key-analyst` is a subagent that has the `prepare-rsa-keys` skill preloaded. Other agents can read both files as plain instructions. The script only needs Python 3.7+ and pycryptodome.

## Rules for any work involving keys

- Private keys are secrets. Never print or paste key material, commit keys or key-derived reports, or send keys to external services. Refer to keys by file name or by the SHA-256 of the modulus.
- Work on copies outside the repository. Never modify the user's original key files.
- Never reorder the primes. The features read p and q separately, so swapping them changes the classification.

## Layout

- `rsabias/cli.py`: the CLI (`rsabias -a <task> ...`). It dispatches to `rsabias/core/tasks.py`.
- `rsabias/core/`:
  - `key.py`: key parsing;
  - `features.py`: feature transformations;
  - `classifier.py`: the `ProbaTable`, `Classifier` and `Evaluator` classes;
  - `dataset.py`: dataset readers and writers with `meta.json` descriptors.
- `rsabias/model/`: the shipped model (`classification_table_complex.pkl`), `groups/groups.json`, `precision_recall.json`, `transformations/`, `distributions/`.
- `datasets/baby_dataset/`: small labelled sample keys, gzipped JSON lines with hex values.
- `datasets/BatchGCD-primes-only/`: single primes from GCD-factorable TLS keys.

## Running

Use an environment where `python -c "import rsabias.core.tasks"` succeeds (install per the README; the pinned dependencies are old). If a Docker image `rsabias:esorics2020` exists (`docker images rsabias`), it works: its entrypoint is `python -m rsabias.cli`.

## Known pitfalls in the current code

- `classify` opens the key file as text, so DER input fails. It doesn't take a passphrase, so encrypted keys fail too.
- OpenSSH private keys are accepted but come out with p and q swapped (pycryptodome's importer swaps them), which gives a wrong group without any error.
- `classify` writes `key_classification.json` into `-o` and overwrites it on every run.
- `evaluate` ignores `-l` and always runs the labelled accuracy evaluation. There is no CLI path for classifying an unlabelled batch.
- `batch_gcd` reads a hardcoded placeholder path (`see/comment/above` in `Evaluator.init_batch_dictionary`).
- The cross-feature classifier described in the paper cannot be selected from the CLI (`-m` accepts `complex` or `naive`).
