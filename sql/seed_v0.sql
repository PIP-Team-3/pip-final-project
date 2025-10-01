INSERT INTO profiles (id, display_name, email, created_at) VALUES
    ('11111111-1111-1111-1111-111111111111', 'Alex Rivera', 'alex@example.com', '2025-09-30T21:40:00Z'),
    ('22222222-2222-2222-2222-222222222222', 'Morgan Lee', 'morgan@example.com', '2025-09-30T21:41:00Z');

INSERT INTO papers (
    id,
    title,
    source_url,
    doi,
    arxiv_id,
    pdf_storage_path,
    vector_store_id,
    pdf_sha256,
    status,
    created_by,
    is_public,
    created_at,
    updated_at
) VALUES
    (
        'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
        'Revisiting CIFAR-10 Benchmarks for Lightweight Reproducibility',
        'https://example.com/cifar10-paper',
        '10.1234/cifar10-demo',
        '2201.12345',
        'papers/cifar10/2025-09-30/cifar10.pdf',
        'vs_cifar10_demo',
        '9f86d081884c7d659a2feaa0c55ad015',
        'ingested',
        '11111111-1111-1111-1111-111111111111',
        true,
        '2025-09-30T21:42:00Z',
        '2025-09-30T21:42:30Z'
    ),
    (
        'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
        'Sentiment Analysis Reproduction on SST-2 with Minimal Compute',
        'https://example.com/sst2-paper',
        '10.5678/sst2-demo',
        '2105.67890',
        'papers/sst2/2025-09-30/sst2.pdf',
        'vs_sst2_demo',
        'e2c569be17396eca2a2e3c11578123ed',
        'ingested',
        '22222222-2222-2222-2222-222222222222',
        true,
        '2025-09-30T21:43:00Z',
        '2025-09-30T21:43:20Z'
    );

INSERT INTO paper_sections (
    id,
    paper_id,
    section_type,
    content,
    page_start,
    page_end,
    created_at
) VALUES
    (
        1,
        'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
        'abstract',
        'We revisit CIFAR-10 baselines with deterministic training settings.',
        1,
        1,
        '2025-09-30T21:44:00Z'
    ),
    (
        2,
        'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
        'results',
        'Our CPU-only run reaches 86.5% accuracy without data augmentation.',
        5,
        6,
        '2025-09-30T21:44:10Z'
    ),
    (
        3,
        'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
        'abstract',
        'We evaluate SST-2 sentiment classification with a tiny transformer.',
        1,
        1,
        '2025-09-30T21:44:20Z'
    ),
    (
        4,
        'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
        'results',
        'Evaluation yields 91.2% accuracy using frozen embeddings.',
        4,
        5,
        '2025-09-30T21:44:30Z'
    );

INSERT INTO claims (
    id,
    paper_id,
    dataset_name,
    split,
    metric_name,
    metric_value,
    units,
    method_snippet,
    source_citation,
    confidence,
    created_by,
    created_at
) VALUES
    (
        'c1c1c1c1-c1c1-c1c1-c1c1-c1c1c1c1c1c1',
        'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
        'CIFAR-10',
        'test',
        'accuracy',
        0.865,
        'ratio',
        'ResNet-18 trained for 25 epochs with cosine LR schedule.',
        'Section 4, Table 1',
        0.9,
        '11111111-1111-1111-1111-111111111111',
        '2025-09-30T21:45:00Z'
    ),
    (
        'c2c2c2c2-c2c2-c2c2-c2c2-c2c2c2c2c2c2',
        'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
        'SST-2',
        'validation',
        'accuracy',
        0.912,
        'ratio',
        'Tiny DistilBERT evaluated with frozen backbone.',
        'Section 3, Table 2',
        0.88,
        '22222222-2222-2222-2222-222222222222',
        '2025-09-30T21:45:10Z'
    );

INSERT INTO datasets (
    id,
    name,
    source,
    source_id,
    license,
    default_split,
    size_bytes,
    checksum,
    is_public,
    created_at
) VALUES
    (
        'd1d1d1d1-d1d1-d1d1-d1d1-d1d1d1d1d1d1',
        'CIFAR-10',
        'torchvision',
        'cifar10',
        'MIT',
        'train',
        17049856,
        'checksum-cifar10',
        true,
        '2025-09-30T21:46:00Z'
    ),
    (
        'd2d2d2d2-d2d2-d2d2-d2d2-d2d2d2d2d2d2',
        'SST-2',
        'glue',
        'sst2',
        'Apache-2.0',
        'train',
        5029376,
        'checksum-sst2',
        true,
        '2025-09-30T21:46:10Z'
    );

INSERT INTO plans (
    id,
    paper_id,
    version,
    plan_json,
    env_hash,
    compute_budget_minutes,
    status,
    created_by,
    created_at,
    updated_at
) VALUES
    (
        '33333333-3333-3333-3333-333333333333',
        'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
        '1.1',
        '{"steps": ["download_cifar10", "train_resnet18", "evaluate"]}'::jsonb,
        'env-hash-cifar10-demo',
        18,
        'validated',
        '11111111-1111-1111-1111-111111111111',
        '2025-09-30T21:47:00Z',
        '2025-09-30T21:47:20Z'
    ),
    (
        '44444444-4444-4444-4444-444444444444',
        'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
        '1.1',
        '{"steps": ["download_sst2", "evaluate_distilbert"]}'::jsonb,
        'env-hash-sst2-demo',
        12,
        'validated',
        '22222222-2222-2222-2222-222222222222',
        '2025-09-30T21:47:30Z',
        '2025-09-30T21:47:45Z'
    );

INSERT INTO storyboards (
    id,
    paper_id,
    storyboard_json,
    created_at,
    updated_at
) VALUES
    (
        '55555555-5555-5555-5555-555555555555',
        'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
        '{"pages": [{"title": "CIFAR-10 Intro", "score": "86.5%"}]}'::jsonb,
        '2025-09-30T21:48:00Z',
        '2025-09-30T21:48:20Z'
    ),
    (
        '66666666-6666-6666-6666-666666666666',
        'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
        '{"pages": [{"title": "SST-2 Story", "score": "91.2%"}]}'::jsonb,
        '2025-09-30T21:48:30Z',
        '2025-09-30T21:48:45Z'
    );
