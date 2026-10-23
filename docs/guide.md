# RSABias: a practical guide for testing RSA key generation

This guide shows how to use RSABias to examine RSA keys produced by your own key generation: which known library or device they resemble, whether two sets of keys differ, and whether your keys show anomalies compared with the datasets the tool was built from. It is written for the first round of testing; where a step has known limitations, they are listed, together with what to report back to us so that we know what to improve.

The [README](../README.md) is the reference for every command and option. This guide is a set of walkthroughs.

## 1. What RSABias does

RSABias accompanies the paper [Biased RSA private keys: Origin attribution of GCD-factorable keys](https://arxiv.org/abs/2009.06700) (ESORICS 2020). Implementations generate RSA primes in different ways, and those choices leave statistical traces in the keys. The tool measures five of them on every private key:

| Feature | What it measures |
|---|---|
| msb5 of p, msb5 of q | the 5 most significant bits of each prime, read separately |
| Blum | whether both primes are 3 mod 4 |
| modular fingerprint | the smallest small-prime bound up to which p-1 and q-1 have no small odd divisors: 1 (none), 5, 251 or 17863 |
| ROCA | whether the modulus has the structure of the Infineon ROCA vulnerability (CVE-2017-15361) |

From more than 150 million keys of 70 sources (libraries, smartcards, HSMs) collected until 2020, the sources were clustered into **26 groups** of sources whose keys are indistinguishable by these features. A shipped model (a Bayes classifier) then estimates which group a key most likely comes from.

What follows from this:

- **The answer is a group, not a library version.** Group 24, for example, holds OpenSSL 0.9.7 to 1.1.0e, including FIPS builds.
- **The tool needs private keys.** p and q are required; public keys and certificates cannot be analysed.
- **One key says little.** For a single key the model is right in 47.7% of cases on average (a random guess: 4%). With 10 keys from one source, it is right in about 89%.
- **The model only knows sources until 2020.** Keys from other or newer implementations are still assigned the closest group. For example, OpenSSL 3 keys are not recognised as OpenSSL: their modular fingerprint is mostly 1, while the OpenSSL versions in the model always give 17863. Comparing distributions (walkthrough 3) shows such differences directly.
- **Only these five features are compared.** A change in key generation that leaves them unchanged is not visible to the tool.

## 2. Handling keys

Everything in this guide runs on your machines; private keys never need to leave them. What you may share with us when reporting results or problems:

| Shareable | Not shareable |
|---|---|
| `dist.json` and `meta.json` from `dist` (counts of feature values) | key files, `keys.json` dataset files |
| `evaluate` outputs (`n_*_results.json`, `confusion_matrix.*`) | anything containing p, q, d or n |
| scrutiny-viz reports | |
| `key_classification.json` reports (scores per group, no key material) | |

Work on copies of the keys, never on the originals.

## 3. Setup

Clone the repository and run every command in this guide from its root:

```bash
git clone https://github.com/crocs-muni/RSABias.git
cd RSABias
mkdir -p work        # keys and outputs go here; git ignores this directory
```

**Docker (recommended).** Build the image once, then define a shell function so that the commands below work unchanged. The function mounts the repository root, so all paths must lie inside it (hence `work/`):

```bash
docker build -t rsabias .
rsabias() { docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/work" rsabias "$@"; }
rsabias-python() { docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/work" --entrypoint python rsabias "$@"; }
```

**Local install** (Python 3.11 or newer):

```bash
python3 -m venv venv && source venv/bin/activate && pip install .
alias rsabias-python=python
```

Check the setup with `rsabias -h`.

**Output directories must exist** before `classify`, `evaluate` and `group` run; only `dist` creates its own. Each walkthrough creates them with `mkdir -p`.

The model files used below are in `rsabias/model/`:

```bash
TRANS=rsabias/model/transformations/5p_5q_blum_mod_roca.json
GROUPS_JSON=rsabias/model/groups/groups.json
MODEL=rsabias/model
```

## 4. Walkthrough 1: classify one key

Generate a test key, classify it and read the result:

```bash
mkdir -p work/w1
openssl genrsa -out work/w1/key.pem 2048
rsabias -a classify -i work/w1/key.pem -o work/w1
```

The output names the most likely group, its precision ("if a key is marked as coming from group X, the model is right in Y% of cases"), its recall, and the sources in the group. `work/w1/key_classification.json` holds the same for all 26 groups, ordered by score. A score of 0 means the group has never produced this combination of features: such groups are ruled out, which for a single key is often the most solid result.

Key formats: the file must hold one unencrypted RSA private key in PEM (PKCS#1 or PKCS#8). Convert other formats first:

```bash
openssl rsa -inform DER -in key.der -out key.pem              # DER
openssl rsa -in encrypted.pem -out key.pem                    # remove a passphrase
cp id_rsa key.pem && ssh-keygen -p -m PEM -N "" -f key.pem    # OpenSSH
```

Do not classify OpenSSH keys directly: they are read with p and q swapped, which changes the result without an error.

## 5. Walkthrough 2: which known source do my keys resemble?

With several keys **from one source**, combine their results: the scores of each group are multiplied over all keys, as the model's own evaluation does. Classify each key into its own directory (every run overwrites `key_classification.json`), then summarise:

```bash
# keys in work/mykeys/*.pem
for f in work/mykeys/*.pem; do
    n=$(basename "$f" .pem); mkdir -p "work/w2/$n"
    rsabias -a classify -i "$f" -o "work/w2/$n" > /dev/null
done
rsabias-python tools/summarize_classification.py work/w2/*/key_classification.json
```

The summary lists the top group of every key, how often each group came first, and the combined ranking with the sources of the top three groups. Groups that any key rules out are excluded.

Reading it:

- Agreement between the per-key top groups and the combined ranking supports the verdict. A combined winner that few keys picked individually means the keys fit no group well.
- If **every** group is ruled out, the keys either come from several sources or from a source the model does not know.
- Only combine keys from one source. Keys from different sources rule out each other's groups.

Each `classify` run takes a few seconds, so this suits up to a few hundred keys. For large sets, use walkthrough 3.

**Without the tool:** the combined score of a group is the sum of the logarithms of its scores over all reports:

```bash
rsabias-python -c '
import json, math, sys
reports = [json.load(open(p)) for p in sys.argv[1:]]
log = {g: sum(math.log(r[g]["score"]) if r[g]["score"] > 0 else -math.inf for r in reports) for g in reports[0]}
for g in sorted(log, key=log.get, reverse=True)[:3]: print(g, log[g], reports[0][g]["sources"])
' work/w2/*/key_classification.json
```

## 6. Walkthrough 3: compare key sets

This is the main tool for comparing two sets of your keys (for example two versions of your library), or your keys with the sources the model was built from. It works with any number of keys: `dist` processes about 1 million keys in 5 minutes.

### Step 1: pack the keys into a dataset

The dataset tasks read a directory with a `meta.json` that describes the source, and a key file. `tools/pem2dataset.py` creates both from PEM files:

```bash
rsabias-python tools/pem2dataset.py work/datasets/v1/mylib-v1 MyLib 1.0 work/keys-v1/*.pem
rsabias-python tools/pem2dataset.py work/datasets/v2/mylib-v2 MyLib 2.0 work/keys-v2/*.pem
```

Arguments: output directory, source name, version, key files. It skips files it cannot read and keys of a different length than the first, with a warning. For very many keys, the shell may refuse a long `*.pem` list; pass a directory listing in parts or use the alternative below.

**Without the tool:** concatenate the PEM files and write `meta.json` by hand:

```bash
mkdir -p work/datasets/v1/mylib-v1
cat work/keys-v1/*.pem > work/datasets/v1/mylib-v1/keys.pem
cat > work/datasets/v1/mylib-v1/meta.json <<'EOF'
{
  "type": "reference",
  "files": [{"name": "keys.pem", "records": 1000000}],
  "details": {"category": "Library", "name": "MyLib", "version": "1.0", "bitlen": 2048,
              "format": "pem", "compressed": false, "fips_mode": false}
}
EOF
```

`records` must be the number of keys. Other key file formats (JSON lines, CSV) are described in [datasets/baby_dataset/readme.md](../datasets/baby_dataset/readme.md).

### Step 2: compute the distributions

```bash
rsabias -a dist -i work/datasets/v1 -o work/dist-v1 -t $TRANS
rsabias -a dist -i work/datasets/v2 -o work/dist-v2 -t $TRANS
```

Each source gets a `dist.json` with the count of every combination of feature values, under `<output>/<category>/<name>/<version>/<bitlen>/`.

### Step 3: compare

```bash
rsabias-python tools/compare_dist.py work/dist-v1 work/dist-v2
```

For each feature, it prints the share of every value in both sets, the difference in percentage points, and a chi-square test; then the total variation distance over all features together, the combinations that differ most, and combinations seen in only one set. An excerpt, comparing OpenSSL 1.1.0e keys with OpenSSL 3 keys:

```
modular fingerprint (chi-square p = 0)
     value      A %      B %    B-A pp
         1     0.00    90.00    +90.00
         5     0.00     6.67     +6.67
     17863   100.00     3.33    -96.67
```

Reading it: with many keys, even negligible differences are statistically significant, so judge them by the size in percentage points. For scale, OpenSSL 1.1.0e keys of 1024 and 2048 bits, which come from the same implementation, differ by a total variation distance of 1.2 pp.

### Comparing with the sources of the model

The distributions of all 184 sources (source, version and key length) the model was built from are in `rsabias/model/distributions/`. Either side of `compare_dist.py` can be a single `dist.json` or a directory, whose distributions are summed:

```bash
# against one known source
rsabias-python tools/compare_dist.py rsabias/model/distributions/Library/OpenSSL/1.1.0e/2048/dist.json work/dist-v1
# against all versions of a library
rsabias-python tools/compare_dist.py rsabias/model/distributions/Library/OpenSSL work/dist-v1
```

To see which known sources are closest overall, cluster your distribution together with all of them. Your source either joins an existing group or forms its own:

```bash
mkdir -p work/cluster/in work/cluster/out
cp -r rsabias/model/distributions/* work/cluster/in/
cp -r work/dist-v1/* work/cluster/in/
rsabias -a group -i work/cluster/in -o work/cluster/out -t $TRANS > work/cluster/out/groups.txt
```

`groups.txt` lists the resulting groups as JSON; find your source in it to see which known sources share its group. The dendrogram PDF in `work/cluster/out` shows how far each source is from the others.

### Limitations

- `compare_dist.py` is text only. A visual comparison of two distributions in scrutiny-viz is planned.
- `group` prints its groups instead of saving them, and its dendrogram file has a long, generated name.
- `dist+plot` draws nothing for the model's transformation (its feature space is too large to plot).

## 7. Walkthrough 4: evaluate your keys against a known group

`evaluate` measures how well the model recognises keys as coming from a group you name. Use it when you expect your keys to behave like a known source, for example because your implementation builds on a library in the model, or because walkthrough 2 pointed to one: if the model recognises your keys as that group about as well as the original source's own keys, your keys are consistent with it; if not, they deviate.

scrutiny-viz then compares two evaluations, for example the original source against your keys, and renders the differences as an HTML report.

### What evaluate does

| | |
|---|---|
| Input `-i` | a directory searched for `meta.json` files, each a dataset of **private** keys. Each `meta.json` must name the true group in `details.group` |
| `-t`, `-g`, `-c` | the transformation, groups file and model directory: `$TRANS`, `$GROUPS_JSON`, `$MODEL` |
| Output `-o` | an existing directory |
| Processing | For batch sizes 1, 10, 20, 30 and 100: cut each dataset into consecutive batches, combine the scores within a batch, and count whether the true group is the first, among the first two, or among the first three |
| `n_<size>_results.json` | `{"n_keys": size, "accuracies": {"1"/"2"/"3": {group: {"correct", "wrong"}}}}` |
| `confusion_matrix.txt`, `.png`, `.pkl` | for single keys: where the keys of each true group were classified |

Results are summed per group, not per dataset, so evaluate the two sets you want to compare **in separate runs**. `evaluate` classifies every key five times (once per batch size), about 3.5 ms each: about 5 hours for 1 million keys. A sample of 100,000 keys is enough.

### Step 1: label and evaluate your keys

Pick the group you expect, e.g. 24 for OpenSSL (`rsabias/model/groups/groups.json` lists the sources of every group):

```bash
rsabias-python tools/pem2dataset.py work/eval-in/mine/mylib MyLib 1.0 work/keys-sample/*.pem --group 24
mkdir -p work/eval-out/mine
rsabias -a evaluate -i work/eval-in/mine -o work/eval-out/mine -t $TRANS -g $GROUPS_JSON -c $MODEL
```

Without the tool, add `"group": "24"` to `details` in a hand-written `meta.json` (walkthrough 3).

### Step 2: evaluate the reference

The reference is a source of that group from our dataset of 160 million keys ([download](https://owncloud.cesnet.cz/index.php/s/Ihhw3BKKzKTaxB9); take only the source you need). Add `"group": "24"` to the `details` of its `meta.json`, take a sample of comparable size, and evaluate it the same way into `work/eval-out/reference`.

### Step 3: compare in scrutiny-viz

[scrutiny-viz](https://github.com/crocs-muni/scrutiny-viz) is a separate tool (Python 3.13); install it per its README. From its directory:

```bash
R=/path/to/RSABias/work/eval-out
python scrutinize.py map -t rsabias --folder $R/reference -o results/reference.json
python scrutinize.py map -t rsabias --folder $R/mine -o results/mine.json
python scrutinize.py verify -s scrutiny/schemas/RSABiasEval.yml -r results/reference.json -p results/mine.json -o results/verify.json
python scrutinize.py report -p results/verify.json -o mylib.html
```

The report shows, per batch size, the accuracy of each group for both evaluations and the difference, the most frequent misclassifications, and the confusion matrix as a heatmap.

### Known limitations

This combination is new, and we expect some of it not to work for your data. Please report what you run into; the right column says what helps us most.

| Limitation | Effect | Please report |
|---|---|---|
| The accuracy in the report mixes three measures: true group first, among the first two, among the first three | The percentages are higher than the top-1 accuracy | Whether you need top-1 only, or all three side by side |
| Heatmap rows and columns are matrix positions, not group numbers; position i is the i-th group in text order (1, 10, 11, ..., 19, 2, 20, ...) | Hard to read the heatmap; `confusion_matrix.txt` in the evaluate output has the real group numbers | Whether the heatmap is useful to you at all |
| The confusion matrix is read from a Python pickle | Only open evaluate outputs you produced yourself | Any loading errors with the versions you use |
| Groups without keys produce empty (NaN) rows, which the report drops | Only groups present in the input appear | |
| `report` writes into scrutiny-viz's `results/` directory, whatever path `-o` names | Look for the HTML and a zip there | |
| `evaluate` speed | Hours for millions of keys | The sample sizes you needed and the run times you saw |
| `evaluate` needs a group from the model | Keys of an unknown implementation cannot be evaluated as themselves | Whether you need this (see below) |

It is also possible to add your own implementation as a new group (train the model on one set of your keys and evaluate the others against it). This is not covered by this guide; contact us if you need it.

## 8. Interpreting results

- **Report a group, not a library.** "Most consistent with group 24 (OpenSSL 0.9.7 to 1.1.0e); the model is right 90% of the time when it predicts group 24; 13 groups are ruled out" is the right register.
- **Precision varies a lot between groups** (`rsabias/model/precision_recall.json`). Some groups are almost never predicted correctly; quote the precision of the top group.
- **Ruled-out groups are the most reliable single-key result.**
- **Unknown sources are assigned anyway.** If the summary of walkthrough 2 rules out every group, or `compare_dist.py` shows large differences from every known source, your keys come from a source the model does not know. That is a finding in itself.
- **Differences between two of your sets** in walkthrough 3 show a change in how the primes are generated. Small differences in percentage points can be sampling noise even if the p-value is tiny.

## 9. Troubleshooting

| Problem | Cause and fix |
|---|---|
| `FileNotFoundError` at the end of `classify`, `evaluate` or `group` (`classify` prints its result first, then fails writing the report) | The output directory does not exist: `mkdir -p` it first |
| `Permission denied` when writing outputs in Docker | The output directory was created by Docker as root. Remove it, create it yourself, and run with `--user "$(id -u):$(id -g)"` (the `rsabias` function above does) |
| Docker cannot find a file | Paths must lie inside the directory you run from (it is mounted as `/work`); use relative paths |
| `Failed to read key-data from file, 'utf-8' codec can't decode` | DER key, convert it to PEM |
| `The private key is encrypted: a passphrase is required` | Remove the passphrase from a copy |
| `TypeError ... 'NoneType'` in `count_records` during `evaluate` | `records` is missing in `meta.json` |
| `KeyError` in `evaluate` | `details.group` is missing in `meta.json`, or names a group that is not in `$GROUPS_JSON` |

When something fails, send us: the command, the full error output, the `meta.json` files involved, `git rev-parse --short HEAD` of your checkout, and whether you used Docker or a local install. Never send keys.
