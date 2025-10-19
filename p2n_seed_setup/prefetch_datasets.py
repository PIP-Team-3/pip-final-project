import os
import sys

def info(msg):
    print(f"[prefetch] {msg}", flush=True)

def main():
    cache_dir = os.environ.get("DATASET_CACHE_DIR", "./data/cache")
    os.makedirs(cache_dir, exist_ok=True)
    info(f"Using cache_dir={cache_dir}")

    # Try HuggingFace datasets
    try:
        from datasets import load_dataset
        hf_targets = [
            ("glue", "sst2"),
            ("ag_news", None),
            ("dbpedia_14", None),
            ("imdb", None),
            ("yelp_polarity", None),
            ("trec", None),
            ("yahoo_answers_topics", None),
        ]
        for path, subset in hf_targets:
            try:
                if subset:
                    info(f"HF: {path}/{subset}")
                    _ = load_dataset(path, subset, cache_dir=cache_dir, download_mode="reuse_dataset_if_exists")
                else:
                    info(f"HF: {path}")
                    _ = load_dataset(path, cache_dir=cache_dir, download_mode="reuse_dataset_if_exists")
            except Exception as e:
                info(f"HF dataset {path}{('/'+subset) if subset else ''} failed: {e}")
    except Exception as e:
        info(f"Skipping HuggingFace prefetch: {e}")

    # Try torchvision datasets
    try:
        from torchvision import datasets, transforms
        import torch
        tv_targets = [
            ("MNIST", {}),
            ("FashionMNIST", {}),
            ("CIFAR10", {}),
        ]
        transform = transforms.Compose([transforms.ToTensor()])
        for name, kwargs in tv_targets:
            try:
                info(f"torchvision: {name}")
                ds_cls = getattr(datasets, name)
                _ = ds_cls(root=cache_dir, train=True, download=True, transform=transform, **kwargs)
                _ = ds_cls(root=cache_dir, train=False, download=True, transform=transform, **kwargs)
            except Exception as e:
                info(f"torchvision dataset {name} failed: {e}")
    except Exception as e:
        info(f"Skipping torchvision prefetch: {e}")

    info("Done.")

if __name__ == "__main__":
    main()