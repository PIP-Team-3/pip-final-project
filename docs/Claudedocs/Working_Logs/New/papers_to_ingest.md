# Papers to Ingest & Batch Script
**Updated:** 2025-10-05

> Rationale: These 20 papers are **compute‑light**, use **standard datasets**, and give clear, citable metrics. Great for validating extraction → plan → materialize → (real) run.

## Table (20 papers)

| # | Paper (Year) | arXiv ID | Domain | Suggested Dataset / Scope | Primary Metric | Why good for P2N |
|---|---|---|---|---|---|---|
| 1 | Deep Residual Learning (ResNet, 2015) | 1512.03385 | CV | CIFAR‑10, 5–10 epochs | Accuracy | Canonical baseline; many follow‑ups. |
| 2 | MobileNetV2 (2018) | 1801.04381 | CV | CIFAR‑10 / Tiny‑ImageNet | Accuracy | Lightweight; budget‑friendly. |
| 3 | DenseNet (2016) | 1608.06993 | CV | CIFAR‑10 | Accuracy | Strong baseline; memory vs speed tradeoffs. |
| 4 | SqueezeNet (2016) | 1602.07360 | CV | CIFAR‑10 | Accuracy | Ultra‑small; model‑size constraints. |
| 5 | Wide ResNets (2016) | 1605.07146 | CV | CIFAR‑10 | Accuracy | Good for augmentation/regularization studies. |
| 6 | mixup (2018) | 1710.09412 | CV | CIFAR‑10 | Accuracy | Simple augmentation; measurable gains. |
| 7 | CutMix (2019) | 1905.04899 | CV | CIFAR‑10 | Accuracy | Complementary augmentation to mixup. |
| 8 | RandAugment (2019) | 1909.13719 | CV | CIFAR‑10 | Accuracy | Search‑free augmentation. |
| 9 | Cutout (2017) | 1708.04552 | CV | CIFAR‑10 | Accuracy | Minimal code; strong regularization. |
|10 | Batch Normalization (2015) | 1502.03167 | CV | CIFAR‑10 | Accuracy/Loss | Stabilizes training; visible quickly. |
|11 | Bag of Tricks (2018) | 1812.01187 | CV | CIFAR‑10 | Accuracy | Additive small improvements. |
|12 | Adam Optimizer (2014) | 1412.6980 | Opt | CIFAR‑10 | Acc./Loss | Swap optimizer; quick effects. |
|13 | Focal Loss (2017) | 1708.02002 | CV | CIFAR‑10 (imbalanced subset) | Acc./F1 | Handles imbalance; generalizable. |
|14 | CNN for Sentence Classification (TextCNN, 2014) | 1408.5882 | NLP | AG News / SST‑2 small | Accuracy | Fast NLP baseline. |
|15 | fastText (2016) | 1607.01759 | NLP | AG News / Yelp Polarity | Accuracy | Very fast; strong non‑DL baseline. |
|16 | DistilBERT (2019) | 1910.01108 | NLP | SST‑2 (few epochs, CPU) | Accuracy | Transformer quality at lower cost. |
|17 | ULMFiT (2018) | 1801.06146 | NLP | IMDb (subset) | Accuracy | Classic fine‑tuning story. |
|18 | GCN (2016) | 1609.02907 | Graph | Cora / Citeseer | Accuracy | Small graphs; minutes on CPU. |
|19 | XGBoost (2016) | 1603.02754 | Tabular | UCI Adult / Higgs (subset) | AUC/Accuracy | Non‑DL baseline; stresses reporting. |
|20 | Super‑Convergence (2017) | 1708.07120 | Opt | CIFAR‑10 (short schedule) | Acc./Time | Scheduler + budget compliance. |

## Batch ingest (PowerShell)
```powershell
$papers = @(
  @{id="1512.03385"; title="ResNet (He et al., 2015)"},
  @{id="1801.04381"; title="MobileNetV2 (Sandler et al., 2018)"},
  @{id="1608.06993"; title="DenseNet (Huang et al., 2016)"},
  @{id="1602.07360"; title="SqueezeNet (Iandola et al., 2016)"},
  @{id="1605.07146"; title="Wide ResNets (Zagoruyko & Komodakis, 2016)"},
  @{id="1710.09412"; title="mixup (Zhang et al., 2018)"},
  @{id="1905.04899"; title="CutMix (Yun et al., 2019)"},
  @{id="1909.13719"; title="RandAugment (Cubuk et al., 2019)"},
  @{id="1708.04552"; title="Cutout (DeVries & Taylor, 2017)"},
  @{id="1502.03167"; title="Batch Normalization (Ioffe & Szegedy, 2015)"},
  @{id="1812.01187"; title="Bag of Tricks (He et al., 2018)"},
  @{id="1412.6980" ; title="Adam (Kingma & Ba, 2014)"},
  @{id="1708.02002"; title="Focal Loss (Lin et al., 2017)"},
  @{id="1408.5882" ; title="TextCNN (Kim, 2014)"},
  @{id="1607.01759"; title="fastText (Joulin et al., 2016)"},
  @{id="1910.01108"; title="DistilBERT (Sanh et al., 2019)"},
  @{id="1801.06146"; title="ULMFiT (Howard & Ruder, 2018)"},
  @{id="1609.02907"; title="GCN (Kipf & Welling, 2016)"},
  @{id="1603.02754"; title="XGBoost (Chen & Guestrin, 2016)"},
  @{id="1708.07120"; title="Super-Convergence (Smith & Topin, 2017)"}
)
foreach ($p in $papers) {
  $url = "https://arxiv.org/pdf/$($p.id).pdf"
  $t   = [uri]::EscapeDataString($p.title)
  try {
    $resp = Invoke-RestMethod -Method POST -Uri "http://localhost:8000/api/v1/papers/ingest?url=$url&title=$t"
    Write-Host "Ingested: $($p.title) -> $($resp.paper_id)"
  } catch {
    Write-Host "FAILED: $($p.title) -> $($_.Exception.Message)"
  }
}
```

## After ingest: suggested sanity plans
- **CV (CIFAR‑10):** ResNet18, 5 epochs, `batch_size=64`, `optimizer=sgd`, `scheduler=onecycle`, `augmentation=["randaugment"]`.
- **NLP (AG News):** TextCNN, 3 epochs, `optimizer=adam`, small embeddings.
- **Graph (Cora):** 2‑layer GCN, ~200 epochs CPU, target accuracy ~80%+ (optional—extra deps).
- **Tabular (Adult):** XGBoost with early stopping, target AUC > 0.88.
