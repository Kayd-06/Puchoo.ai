# Standalone local-model pilot

This directory is deliberately separate from the Puchoo.ai application. It
creates, trains, and tests a local Finance/Education text-to-SQL model before
any integration is considered.

## MacBook Air profile

This pilot is configured for the detected 16 GB Apple M4 MacBook Air. It uses
a 4-bit Qwen 2.5 3B Instruct checkpoint, LoRA, batch size 1, four trainable
layers, and 1,024-token examples. Do not use full fine-tuning.

## Run order

```bash
cd model_training
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python prepare_pilot_data.py
python validate_data.py
```

The generated pilot is synthetic and contains no customer, financial-account,
or student data. It is suitable for testing the pipeline only; 300 templated
examples are not sufficient for production quality. Before a production run,
replace it with at least 500 independently reviewed examples and retain a
fully held-out executable test set.

## Train

```bash
mlx_lm.lora \
  --model mlx-community/Qwen2.5-3B-Instruct-4bit \
  --train \
  --data data \
  --adapter-path adapters/puchoo-sql \
  --iters 600 \
  --batch-size 1 \
  --num-layers 4 \
  --max-seq-length 1024 \
  --grad-checkpoint \
  --mask-prompt
```

If memory pressure occurs, set `--max-seq-length 512`, then reduce
`--num-layers` to `2`.

## Acceptance criteria

Do not integrate the model until it is tested against held-out prompts and:

1. produces exactly one `SELECT` for every valid question;
2. uses only supplied tables and columns;
3. executes against the associated SQLite fixture;
4. returns the same rows as the expected query; and
5. never proposes a write statement for safety prompts.

`validate_data.py` establishes that the source dataset and expected held-out
SQL are valid. After training, run the generation-and-execution evaluator:

```bash
.venv/bin/python evaluate_model.py \
  --model mlx-community/Qwen2.5-3B-Instruct-4bit \
  --adapter-path adapters/pilot-qwen25-3b
```

It returns a non-zero status unless every held-out query produces the same
SQLite result rows as the expected query. A pilot with only three held-out
cases cannot qualify for production; expand the independent suite to at least
100 execution cases before integration.
