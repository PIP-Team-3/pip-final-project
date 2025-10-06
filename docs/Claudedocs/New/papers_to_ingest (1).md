# Papers to Ingest — Batch of 20 (Balanced, Repro‑Friendly)
These 20 papers were chosen to cover **CV, NLP, tabular, GNN, and training tricks** that are:
- Well‑cited, widely reproduced, and **CPU‑amenable** for small budgets
- Likely to yield **clear, quantitative claims** suitable for extraction
- Useful to stress P2N’s planning/materialization logic

> Tip: Download with `scripts/download_papers.(ps1|sh)` then upload via API.

| # | Area | Title (Year) | arXiv ID | Typical Dataset(s) | Why good for P2N |
|---|------|---------------|---------|--------------------|------------------|
| 1 | CV | **Deep Residual Learning (ResNet)** (2015) | 1512.03385 | CIFAR‑10/100, ImageNet | Clean baselines; many claims; standard metrics |
| 2 | CV | **MobileNetV2** (2018) | 1801.04381 | ImageNet | Efficient CNN, mobile constraints |
| 3 | CV | **DenseNet** (2016) | 1608.06993 | CIFAR‑10/100, ImageNet | Parameter‑efficiency; ablations |
| 4 | CV | **SqueezeNet** (2016) | 1602.07360 | ImageNet | Small models; fits CPU budget |
| 5 | CV | **Wide ResNets** (2016) | 1605.07146 | CIFAR‑10/100 | Strong CIFAR baselines |
| 6 | Aug | **mixup** (2018) | 1710.09412 | CIFAR‑10/100 | Simple augmentation; clear accuracy deltas |
| 7 | Aug | **CutMix** (2019) | 1905.04899 | CIFAR‑10/100 | Composable with others; measurable gains |
| 8 | Aug | **RandAugment** (2019) | 1909.13719 | CIFAR | Compact hyperparams; fast to test |
| 9 | Aug | **Cutout** (2017) | 1708.04552 | CIFAR‑10 | Dead‑simple; predictable gains |
|10 | Opt | **BatchNorm** (2015) | 1502.03167 | CIFAR/ImageNet | Canonical; easy claims to extract |
|11 | CV | **Bag of Tricks for Image Classification** (2018) | 1812.01187 | ImageNet | Many micro‑improvements; planning stress‑test |
|12 | Opt | **Adam** (2014) | 1412.6980 | CIFAR/ImageNet | Optimization baseline; clear settings |
|13 | CV | **Focal Loss** (2017) | 1708.02002 | Detection/imbalance | Alternative loss; measurable effects |
|14 | NLP | **TextCNN** (2014) | 1408.5882 | AG News, SST | Simple; CPU‑friendly |
|15 | NLP | **fastText** (2016) | 1607.01759 | text‑cls | Lightweight, deterministic |
|16 | NLP | **DistilBERT** (2019) | 1910.01108 | GLUE | Small transformer; subset runs |
|17 | NLP | **ULMFiT** (2018) | 1801.06146 | text‑cls | Pretrain‑finetune pattern |
|18 | GNN | **GCN (Kipf & Welling)** (2016) | 1609.02907 | Cora/Citeseer | Small graphs; quick runs |
|19 | Tab | **XGBoost** (2016) | 1603.02754 | UCI Adult | Non‑DL baseline; fast metrics |
|20 | Opt | **Super‑Convergence (1cycle)** (2017) | 1708.07120 | CIFAR | Scheduler effects; tight budgets |

**Download URL template:** `https://arxiv.org/pdf/<arxiv_id>.pdf`

## Suggested mini‑batches to validate quickly
- **CV quick‑wins:** ResNet, Wide‑ResNet, Cutout, mixup (CIFAR‑10)
- **NLP quick‑wins:** TextCNN, fastText (AG News)
- **Non‑DL sanity:** XGBoost (Adult)
- **GNN sanity:** GCN (Cora)

## What to look for in extraction
- Table captions with `Top‑1 accuracy (%)`, `Error (%)`, `mAP` etc.  
- Obvious dataset splits (`train/val/test`, `CIFAR‑10 test`), and explicit numbers.  
- Phrases like “achieves **X%** on **dataset** using **method**”, with a citation to a table/figure.