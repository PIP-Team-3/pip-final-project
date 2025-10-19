# P2N — Datasets & Notebooks Plan (Updated)  
**Date:** 2025-10-08  
**Scope:** How agents pick the *right* dataset, when (and why) to pre‑select papers, and the concrete plan for Phase 2–4 of the notebook system.

---

## 1) How the agents pick the correct dataset for a paper

### High‑level flow
1. **Extract** (gpt‑4o): claims are pulled from the paper (tables/sections) with `{
   dataset_name, split, metric_name, metric_value, units, method_snippet, citation }`.
2. **Plan** (two‑stage: o3‑mini → gpt‑4o): the planner reads the claims and the paper via **File Search** and produces a Plan JSON v1.1 with a concrete `dataset.name`, `split`, `model`, `framework`, `config`, `metrics` and justifications.
3. **Map → Registry** (server): the materializer resolves `plan.dataset.name` to a known dataset **without downloading anything on the server**:
   - Normalize (lowercase, hyphens/underscores removed), e.g., `SST-2 → sst2`.
   - Alias table: `sst-2`, `SST2`, `glue/sst2` → `sst2`.
   - Look up in the **Dataset Registry** (metadata only).
   - If no match → graceful **synthetic** fallback (makes the notebook still runnable).
4. **Generate Notebook** (server): the dataset generator emits **code** that downloads/caches **on the executor** (not on the server).
5. **Execute Notebook** (sandbox): first run downloads; subsequent runs hit the local cache.

### Why this works
- **Zero server downloads** (stateless service).
- **Lazy loading** in the notebook (via Hugging Face / torchvision / sklearn built‑ins).
- **Offline mode** and **resource caps** supported via env vars in the generated code.
- **Graceful degradation**: if a dataset isn’t recognized or download fails, we fallback to synthetic so every plan still materializes and runs.

### Mapping logic (deterministic)
- Normalize → alias map → registry match → generator selection.
- If ambiguity: the planner includes quotes/citations; we match by **dataset‑typical metrics/splits** and by **paper evidence** (e.g., `SST‑2`, `accuracy (test)`, GLUE references).
- Policy gates before selection:
  - **License** must be permissive (no paywalls/EULAs we can’t accept programmatically).
  - **Size/Time** fits our 20‑minute CPU budget (subsampling parameter if borderline).
  - **Availability** via standard libraries (HF `datasets`, `torchvision`, `sklearn`).

---

## 2) Do we need Web Search here?

**Short answer:** Not for Phase 2–3.  
- The planner already has grounding via **File Search** on the PDF; our **Dataset Registry** supplies the loader code paths.  
- Web Search helps when the paper references unusual datasets or off‑platform assets (e.g., a lab page zip, a GitHub repo, or a dataset with nonstandard loaders). That’s “nice‑to‑have” and we can enable it later with a model that supports it (e.g., GPT‑4o).  
- With **o3‑mini**, we intentionally **disable web_search** to avoid API errors; the two‑stage planner still works because standard benchmarks are covered by the registry.

**Recommendation:** Keep Web Search **off** for planner in MVP; enable selectively per paper when we detect **“dataset not in registry”** or **“repo/code link needed”** signals.

---

## 3) Should we pre‑select papers? Yes — and here’s a curated list

For the MVP, bias toward **small, permissively licensed** benchmarks with well‑known loaders and quick CPU training/fine‑tuning. Below are suggestion buckets.

> **How to use these:** start with *Tier A* (fast to reproduce end‑to‑end), then expand to *Tier B* for diversity, and keep *Tier C* for future/optional work.

### Tier A — Fast & fully accessible (ideal for MVP)
1. **Convolutional Neural Networks for Sentence Classification** (Kim, 2014) — classic TextCNN on small text datasets (SST‑2, TREC, etc.).  
   Paper: https://arxiv.org/abs/1408.5882  
   Datasets (loaders ready in registry):
   - GLUE **SST‑2**: https://huggingface.co/datasets/glue (subset: `sst2`)
   - **TREC** question classification: https://huggingface.co/datasets/trec
   - **AG News**: https://huggingface.co/datasets/ag_news
   - **IMDB** sentiment: https://huggingface.co/datasets/imdb  
   *(Some original Kim datasets like MPQA/CR may have license hoops; we’ll prefer the accessible ones above.)*

2. **Fashion‑MNIST: a Novel Image Dataset for Benchmarking ML Algorithms** (Xiao et al., 2017).  
   Paper: https://arxiv.org/abs/1708.07747  
   Loader: `torchvision.datasets.FashionMNIST`

3. **IMDB Large Movie Review Dataset** (Maas et al., 2011).  
   Paper: https://ai.stanford.edu/~amaas/papers/wvSent_acl2011.pdf  
   Loader: `datasets.load_dataset("imdb")`

### Tier B — Common baselines (still reasonable on CPU with subsampling)
4. **Character‑level CNNs for Text Classification** (Zhang, Zhao, LeCun, 2015).  
   Paper: https://arxiv.org/abs/1509.01626  
   Datasets: **AG News**, **DBPedia**, **Yahoo Answers** (we’ll start with AG News).

5. **Simple CNNs on MNIST / CIFAR‑10 baselines** (multiple references).  
   Dataset pages:  
   - **MNIST** (LeCun et al.): http://yann.lecun.com/exdb/mnist/ (loader in `torchvision`)
   - **CIFAR‑10** (Krizhevsky): https://www.cs.toronto.edu/~kriz/cifar.html (loader in `torchvision`)  
   *We’ll cap samples/epochs for the 20‑minute CPU budget.*

### Tier C — Heavier / partial reproductions (fine‑tuning or small‑scale)
6. **Deep Residual Learning for Image Recognition** (He et al., 2015).  
   Paper: https://arxiv.org/abs/1512.03385  
   *Full ImageNet training is out‑of‑scope for CPU; we’ll target **CIFAR‑10** with ResNet‑18/34.*

7. **BERT: Pre‑training of Deep Bidirectional Transformers** (Devlin et al., 2018).  
   Paper: https://arxiv.org/abs/1810.04805  
   *We’ll do fast **fine‑tuning** on **SST‑2** (HF `transformers`) rather than pre‑training.*

> **Why pre‑select?** It de‑risks MVP demos and end‑to‑end testing. These titles are widely cited, have straightforward loaders, and fit our runtime envelope with modest subsampling/epochs.

---

## 4) Dataset Registry — initial seed (Phase 2)

The registry is **metadata only** (no downloads). It drives generator selection and produces the correct loader **code** in the notebook.

```python
# api/app/materialize/generators/dataset_registry.py (sketch)
from enum import Enum
from typing import Dict, Optional, Tuple

class DatasetSource(Enum):
    SKLEARN = "sklearn"
    TORCHVISION = "torchvision"
    HUGGINGFACE = "huggingface"
    SYNTHETIC = "synthetic"

class DatasetMetadata:
    def __init__(self, source: DatasetSource, load_function: str,
                 typical_size_mb: int, supports_streaming: bool = False,
                 hf_path: Optional[Tuple[str, ...]] = None, aliases=()):
        self.source = source
        self.load_function = load_function
        self.typical_size_mb = typical_size_mb
        self.supports_streaming = supports_streaming
        self.hf_path = hf_path
        self.aliases = set(a.lower() for a in aliases)

DATASET_REGISTRY: Dict[str, DatasetMetadata] = {
    # Text (HF)
    "sst2": DatasetMetadata(DatasetSource.HUGGINGFACE, "load_dataset", 70,
                            supports_streaming=True, hf_path=("glue", "sst2"),
                            aliases=("sst-2", "glue/sst2", "sst_2")),
    "imdb": DatasetMetadata(DatasetSource.HUGGINGFACE, "load_dataset", 130,
                            supports_streaming=True, hf_path=("imdb",)),
    "ag_news": DatasetMetadata(DatasetSource.HUGGINGFACE, "load_dataset", 20,
                               supports_streaming=True, hf_path=("ag_news",)),
    "trec": DatasetMetadata(DatasetSource.HUGGINGFACE, "load_dataset", 5,
                            supports_streaming=True, hf_path=("trec",)),

    # Vision (torchvision)
    "mnist": DatasetMetadata(DatasetSource.TORCHVISION, "MNIST", 15),
    "fashionmnist": DatasetMetadata(DatasetSource.TORCHVISION, "FashionMNIST", 30,
                                    aliases=("fashion-mnist", "fmnist")),
    "cifar10": DatasetMetadata(DatasetSource.TORCHVISION, "CIFAR10", 180,
                               aliases=("cifar-10",)),
}
```

**Selection rule:** normalize name → exact match → alias match → fallback **synthetic**.

---

## 5) Generators (Phase 2 & 3) — lazy, cache‑aware code

Each generator **emits code strings**; the server never downloads datasets.

**Hugging Face (text, lazy):**
```python
from datasets import load_dataset
import os

CACHE_DIR = os.getenv("DATASET_CACHE_DIR", "./data/cache")
OFFLINE_MODE = os.getenv("OFFLINE_MODE", "false").lower() == "true"

# Reuse cache if present; only download when needed and online
dataset = load_dataset("glue", "sst2", cache_dir=CACHE_DIR,
                       download_mode="reuse_dataset_if_exists")

split = "train"  # or plan.dataset.split
train = dataset[split]

# Example: bag-of-words for Phase 2 (Phase 3 swaps in real models)
from sklearn.feature_extraction.text import CountVectorizer
texts = [row["sentence"] for row in train]
labels = [row["label"] for row in train]
```

**torchvision (vision, cache‑first):**
```python
from torchvision import datasets, transforms
import os, numpy as np

CACHE_DIR = os.getenv("DATASET_CACHE_DIR", "./data")
OFFLINE_MODE = os.getenv("OFFLINE_MODE", "false").lower() == "true"

transform = transforms.Compose([transforms.ToTensor()])
train_ds = datasets.FashionMNIST(root=CACHE_DIR, train=True,
                                 download=not OFFLINE_MODE, transform=transform)
X_train = train_ds.data.numpy().reshape(len(train_ds), -1)
y_train = np.array(train_ds.targets)
```

**sklearn (tiny, bundled):**
```python
from sklearn.datasets import load_digits
X, y = load_digits(return_X_y=True)
```

**Controls available at runtime (env):**
- `OFFLINE_MODE=true` → never download, use cache only
- `DATASET_CACHE_DIR=./data/cache` → persisted volume
- `MAX_TRAIN_SAMPLES=5000` → subsample to fit time budget

---

## 6) Updated Phases, checkpoints & tests

### Phase 2 — Smart **Dataset** Selection (7 days)
**Goal:** Notebook loads the correct dataset automatically, with lazy caching.

**Deliverables**
- Dataset Registry module + unit tests
- HuggingFace/Torchvision/Sklearn DatasetGenerators
- Factory selection (registry → generator; fallback synthetic)
- Materializer wiring + env‑aware code emission

**Checkpoints**
- [ ] `lookup_dataset()` handles aliases (sst2, sst-2, glue/sst2)
- [ ] Generators emit **no downloads** on server, only code
- [ ] OFFLINE_MODE + cache_dir respected in generated code
- [ ] Subsampling honored via `MAX_TRAIN_SAMPLES`

**Tests**
- Unit: registry lookups; generator code contains `cache_dir` or `download=` knobs
- Integration: generate notebook for `sst2`, `imdb`, `fashion-mnist`, `mnist`, `cifar10`
- Smoke: run notebooks with `OFFLINE_MODE=true` when cache is present

**Acceptance**
- `materialize` produces notebooks that execute end‑to‑end on at least 5 datasets with and without cache.

---

### Phase 3 — Smart **Model** Selection (7 days)
**Goal:** Model code aligns with plan (TextCNN / simple CNN / ResNet‑18 / classic sklearn).

**Deliverables**
- `SklearnModelGenerator`: LogisticRegression, LinearSVC, RandomForest
- `TorchCNNGenerator` (text): small TextCNN‑style module
- `TorchResNetGenerator`: ResNet‑18/34 via `torchvision.models`
- Factory selection mapped from `plan.model.name` + `plan.framework`

**Checkpoints**
- [ ] Hyperparams mapped (epochs, lr, batch_size) from plan → code
- [ ] Determinism (global SEED) + CPU‑only ensured
- [ ] Training loops emit `metric_update` and save `metrics.json`

**Tests**
- Unit: each generator produces import/code/requirements
- Integration: run on small slices of SST‑2 (text CNN) & Fashion‑MNIST (CNN)
- Perf: 20‑minute CPU budget with subsampling

**Acceptance**
- At least 3 model families working end‑to‑end on 3 datasets (text & vision).

---

### Phase 4 — Docker‑Ready Executor Prep (5 days)
**Goal:** Notebooks run reliably in a container with caching & resource guards.

**Deliverables**
- Env checks in setup cell (CPU‑only, memory, offline mode)
- Relative paths (`./data`, `./artifacts`) only
- Dockerfile for executor image; volume for `./data/cache`
- CI job that executes a “golden” notebook matrix

**Checkpoints**
- [ ] OFFLINE_MODE path verified (no network)
- [ ] Cache survives runs (volume mount works)
- [ ] Memory guardrails (psutil) prevent OOM

**Acceptance**
- Golden matrix passes in CI: {sst2+TextCNN}, {fashion‑mnist+CNN}, {digits+sklearn}.

---

## 7) Paper selection policy (how we accept/reject)

**Accept** when all true:
- Dataset in registry or trivial to add.
- License permissive; accessible via HF/torchvision/sklearn.
- Fits runtime envelope with subsampling.
- Paper claims are quantitative and tabled.

**Defer** when any true:
- Private/paid datasets; fragile scrapers.
- Training requires GPUs for meaningful results.
- Claims depend on heavy pretraining (we’ll switch to fine‑tuning).

---

## 8) Actionable next steps

- [ ] Seed `dataset_registry.py` (entries above) and wire to `GeneratorFactory`.
- [ ] Implement HF/Torchvision/Sklearn dataset generators (code snippets above).
- [ ] Add unit + integration tests for registry & generators.
- [ ] Add env‑var docs to `README`: `OFFLINE_MODE`, `DATASET_CACHE_DIR`, `MAX_TRAIN_SAMPLES`.
- [ ] Start with **Tier A** papers (Kim14, Fashion‑MNIST, IMDB) for end‑to‑end demos.
- [ ] Keep planner **web_search disabled** on o3‑mini; re‑enable later per case on GPT‑4o.

---

## 9) Quick reference — links

> *These are here for convenience when curating test papers/data. We do not preload these on the server; notebooks download/cache on first run.*

- Kim (2014) — Convolutional Neural Networks for Sentence Classification:  
  https://arxiv.org/abs/1408.5882
- Fashion‑MNIST (paper): https://arxiv.org/abs/1708.07747  
  Torchvision loader: https://pytorch.org/vision/stable/generated/torchvision.datasets.FashionMNIST.html
- IMDB dataset (paper): https://ai.stanford.edu/~amaas/papers/wvSent_acl2011.pdf  
  HF card: https://huggingface.co/datasets/imdb
- GLUE / SST‑2: https://huggingface.co/datasets/glue
- TREC: https://huggingface.co/datasets/trec
- AG News: https://huggingface.co/datasets/ag_news
- MNIST: http://yann.lecun.com/exdb/mnist/  
  Torchvision loader: https://pytorch.org/vision/stable/generated/torchvision.datasets.MNIST.html
- CIFAR‑10: https://www.cs.toronto.edu/~kriz/cifar.html  
  Torchvision loader: https://pytorch.org/vision/stable/generated/torchvision.datasets.CIFAR10.html
- ResNet (paper): https://arxiv.org/abs/1512.03385

---

## 10) FAQ

**Q: What if the dataset isn’t in the registry?**  
A: We still materialize a runnable notebook (synthetic fallback) and flag the paper for triage. Adding a metadata entry is a tiny PR — no server restarts required.

**Q: Do we ever download on the server?**  
A: No. The server only **generates code**. Downloads happen inside the sandbox during notebook execution and are cached on disk.

**Q: Will the same notebook run offline?**  
A: Yes. Set `OFFLINE_MODE=true` and ensure the dataset is cached. HF/torchvision will load from the local cache.

**Q: How do we control runtime?**  
A: The generated code reads `MAX_TRAIN_SAMPLES` and caps epochs/batch size from the plan. We also seed RNGs and enforce CPU‑only for determinism.