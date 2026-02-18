"""Prepare the credit card transactions CSV for the eval-dag pipeline.

Reads the raw CSV, computes aggregations from all rows, takes a
stratified sample for the transactions list, and writes two JSON files:
  - dataset/data.json     (pipeline input)
  - dataset/metadata.json (LLM context)

Usage:
    py scripts/prepare_dataset.py
    py scripts/prepare_dataset.py --input dataset/credit_card_transactions.csv --sample-size 5000

Requires: pandas  (pip install pandas)
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("prepare_dataset")


def parse_args():
    p = argparse.ArgumentParser(description="Convert CSV to eval-dag JSON inputs")
    p.add_argument(
        "--input",
        default="dataset/credit_card_transactions.csv",
        help="Path to the raw CSV file",
    )
    p.add_argument(
        "--output-dir",
        default="dataset",
        help="Directory to write data.json and metadata.json",
    )
    p.add_argument(
        "--sample-size",
        type=int,
        default=5000,
        help="Total rows in the stratified transaction sample (default 5000)",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility",
    )
    return p.parse_args()


def safe_float(val) -> float | None:
    """Convert to Python float, returning None if NaN/NA."""
    try:
        f = float(val)
        return None if math.isnan(f) else round(f, 6)
    except (TypeError, ValueError):
        return None


def safe_int(val) -> int | None:
    """Convert to Python int, returning None if NaN/NA."""
    try:
        f = float(val)
        return None if math.isnan(f) else int(f)
    except (TypeError, ValueError):
        return None


def row_to_dict(row) -> dict:
    """Serialize one DataFrame row to a sandbox-safe plain dict.

    All values are int | float | str | None — no numpy/pandas types.
    """
    mz = row["merch_zipcode"]
    mz_str = str(mz) if str(mz) not in ("nan", "None", "") else None

    return {
        "trans_date_trans_time": str(row["trans_date_trans_time"]),
        "cc_num": str(row["cc_num"]),
        "merchant": str(row["merchant"]),
        "category": str(row["category"]),
        "amt": safe_float(row["amt"]),
        "first": str(row["first"]),
        "last": str(row["last"]),
        "gender": str(row["gender"]),
        "city": str(row["city"]),
        "state": str(row["state"]),
        "zip": str(row["zip"]),
        "lat": safe_float(row["lat"]),
        "long": safe_float(row["long"]),
        "city_pop": safe_int(row["city_pop"]),
        "job": str(row["job"]),
        "dob": str(row["dob"]),
        "trans_num": str(row["trans_num"]),
        "unix_time": safe_int(row["unix_time"]),
        "merch_lat": safe_float(row["merch_lat"]),
        "merch_long": safe_float(row["merch_long"]),
        "is_fraud": int(row["is_fraud"]),
        "merch_zipcode": mz_str,
    }


def main() -> None:
    args = parse_args()

    try:
        import pandas as pd
    except ImportError:
        logger.error("pandas is required: pip install pandas")
        sys.exit(1)

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    sample_size = args.sample_size
    seed = args.seed

    # ------------------------------------------------------------------
    # 1. Load CSV
    # ------------------------------------------------------------------
    logger.info(f"Loading {input_path} ...")
    df = pd.read_csv(input_path)
    unnamed_cols = [c for c in df.columns if c.startswith("Unnamed")]
    if unnamed_cols:
        df = df.drop(columns=unnamed_cols)
    logger.info(f"Loaded {len(df):,} rows, {len(df.columns)} columns")

    # ------------------------------------------------------------------
    # 2. Type coercions
    # ------------------------------------------------------------------
    for col in ["amt", "lat", "long", "merch_lat", "merch_long"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ["city_pop", "unix_time"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["is_fraud"] = df["is_fraud"].astype(int)
    df["cc_num"] = df["cc_num"].astype(str)

    # ------------------------------------------------------------------
    # 3. Parse datetime + derive year_month
    # ------------------------------------------------------------------
    try:
        df["parsed_dt"] = pd.to_datetime(
            df["trans_date_trans_time"], format="%d-%m-%Y %H:%M"
        )
    except Exception:
        df["parsed_dt"] = pd.to_datetime(
            df["trans_date_trans_time"], infer_datetime_format=True
        )
    df["year_month"] = df["parsed_dt"].dt.strftime("%Y-%m")

    # ------------------------------------------------------------------
    # 4. Stratified sample
    # ------------------------------------------------------------------
    fraud_df = df[df["is_fraud"] == 1]
    legit_df = df[df["is_fraud"] == 0]

    n_fraud_sample = min(1000, len(fraud_df))
    n_legit_sample = min(sample_size - n_fraud_sample, len(legit_df))

    sampled_fraud = fraud_df.sample(n=n_fraud_sample, random_state=seed)
    sampled_legit = legit_df.sample(n=n_legit_sample, random_state=seed)
    sample_df = (
        pd.concat([sampled_fraud, sampled_legit])
        .sample(frac=1, random_state=seed)
        .reset_index(drop=True)
    )

    logger.info(
        f"Stratified sample: {len(sampled_fraud)} fraud + {len(sampled_legit)} legit"
        f" = {len(sample_df)} total rows"
    )

    # ------------------------------------------------------------------
    # 5. Serialize sample to plain dicts
    # ------------------------------------------------------------------
    logger.info("Serializing transaction sample ...")
    transactions = [row_to_dict(row) for _, row in sample_df.iterrows()]

    # ------------------------------------------------------------------
    # 6. Pre-aggregated fields from ALL rows
    # ------------------------------------------------------------------
    logger.info("Computing aggregations from all rows ...")

    total_transactions = len(df)
    total_fraudulent = int(df["is_fraud"].sum())
    fraud_rate = round(total_fraudulent / total_transactions, 8)

    amt_series = df["amt"].dropna()
    amount_distribution = {
        "min": round(float(amt_series.min()), 2),
        "max": round(float(amt_series.max()), 2),
        "mean": round(float(amt_series.mean()), 4),
        "median": round(float(amt_series.median()), 2),
        "std": round(float(amt_series.std()), 4),
        "p25": round(float(amt_series.quantile(0.25)), 2),
        "p75": round(float(amt_series.quantile(0.75)), 2),
        "p95": round(float(amt_series.quantile(0.95)), 2),
        "p99": round(float(amt_series.quantile(0.99)), 2),
    }

    cat_g = df.groupby("category", sort=False).agg(
        count=("amt", "count"),
        total_amt=("amt", "sum"),
        fraud_count=("is_fraud", "sum"),
        avg_amt=("amt", "mean"),
    ).reset_index()
    category_stats: dict = {}
    for _, r in cat_g.iterrows():
        cnt, fc = int(r["count"]), int(r["fraud_count"])
        category_stats[r["category"]] = {
            "count": cnt,
            "total_amt": round(float(r["total_amt"]), 2),
            "fraud_count": fc,
            "fraud_rate": round(fc / cnt, 8) if cnt else 0.0,
            "avg_amt": round(float(r["avg_amt"]), 4),
        }

    state_g = df.groupby("state", sort=False).agg(
        count=("amt", "count"),
        total_amt=("amt", "sum"),
        fraud_count=("is_fraud", "sum"),
    ).reset_index()
    state_stats: dict = {}
    for _, r in state_g.iterrows():
        state_stats[r["state"]] = {
            "count": int(r["count"]),
            "total_amt": round(float(r["total_amt"]), 2),
            "fraud_count": int(r["fraud_count"]),
        }

    merch_g = (
        df.groupby("merchant", sort=False)
        .agg(
            count=("amt", "count"),
            total_amt=("amt", "sum"),
            fraud_count=("is_fraud", "sum"),
        )
        .reset_index()
        .sort_values("count", ascending=False)
        .head(20)
    )
    top_merchants = []
    for _, r in merch_g.iterrows():
        cnt, fc = int(r["count"]), int(r["fraud_count"])
        top_merchants.append({
            "merchant": r["merchant"],
            "count": cnt,
            "total_amt": round(float(r["total_amt"]), 2),
            "fraud_count": fc,
            "fraud_rate": round(fc / cnt, 8) if cnt else 0.0,
        })

    gender_g = df.groupby("gender", sort=False).agg(
        count=("amt", "count"),
        fraud_count=("is_fraud", "sum"),
        total_amt=("amt", "sum"),
    ).reset_index()
    gender_breakdown: dict = {}
    for _, r in gender_g.iterrows():
        gender_breakdown[r["gender"]] = {
            "count": int(r["count"]),
            "fraud_count": int(r["fraud_count"]),
            "total_amt": round(float(r["total_amt"]), 2),
        }

    ts_g = (
        df.groupby("year_month", sort=False)
        .agg(
            count=("amt", "count"),
            total_amt=("amt", "sum"),
            fraud_count=("is_fraud", "sum"),
        )
        .reset_index()
        .sort_values("year_month")
    )
    time_series: dict = {}
    for _, r in ts_g.iterrows():
        time_series[r["year_month"]] = {
            "count": int(r["count"]),
            "total_amt": round(float(r["total_amt"]), 2),
            "fraud_count": int(r["fraud_count"]),
        }

    date_range = {
        "start": df["parsed_dt"].min().strftime("%Y-%m-%d"),
        "end": df["parsed_dt"].max().strftime("%Y-%m-%d"),
    }

    fraud_in_sample = sum(1 for t in transactions if t["is_fraud"] == 1)
    sample_info = {
        "sample_size": len(transactions),
        "fraud_in_sample": fraud_in_sample,
        "fraud_rate_in_sample": round(fraud_in_sample / len(transactions), 4),
        "note": (
            "Stratified sample: fraud rows overrepresented (~20%) vs real rate (~0.57%). "
            "Use pre-aggregated fields (fraud_rate, category_stats, etc.) for global statistics. "
            "Use transactions list only for cross-dimensional or per-transaction analysis."
        ),
    }

    # ------------------------------------------------------------------
    # 7. Assemble and write data.json
    # ------------------------------------------------------------------
    data = {
        "transactions": transactions,
        "total_transactions": total_transactions,
        "total_fraudulent": total_fraudulent,
        "fraud_rate": fraud_rate,
        "date_range": date_range,
        "amount_distribution": amount_distribution,
        "category_stats": category_stats,
        "state_stats": state_stats,
        "top_merchants": top_merchants,
        "gender_breakdown": gender_breakdown,
        "time_series": time_series,
        "sample_info": sample_info,
    }

    data_path = output_dir / "data.json"
    logger.info(f"Writing {data_path} ...")
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    size_mb = data_path.stat().st_size / 1_048_576
    logger.info(
        f"data.json written: {len(transactions)} transactions, "
        f"{len(data)} top-level keys, {size_mb:.1f} MB"
    )

    # ------------------------------------------------------------------
    # 8. Write metadata.json
    # ------------------------------------------------------------------
    description = (
        f"Credit card transaction fraud detection dataset covering "
        f"{date_range['start']} to {date_range['end']}. "
        f"Contains {total_transactions:,} transactions from cardholders across the US, "
        f"with a fraud rate of {fraud_rate:.4%}. "
        f"14 merchant categories and 51 US states represented."
    )

    metadata = {
        "description": description,
        "domain": "Financial fraud detection",
        "source": "Synthetic credit card transaction dataset",
        "date_range": f"{date_range['start']} to {date_range['end']}",
        "total_rows": total_transactions,
        "fraud_rate": fraud_rate,
        "columns": {
            "trans_date_trans_time": {
                "description": "Transaction datetime",
                "type": "datetime_string",
                "format": "DD-MM-YYYY HH:MM",
                "strptime": "%d-%m-%Y %H:%M",
                "examples": ["01-01-2019 00:21", "15-06-2019 14:30", "31-12-2019 23:59"],
                "note": "Day-first format — NOT month-first. Use strptime('%d-%m-%Y %H:%M') to parse.",
            },
            "cc_num": {
                "description": "Credit card number",
                "type": "identifier",
                "sensitivity": "pii",
                "format": "scientific notation string, e.g. '2.70319E+15'",
                "note": "Use as string key/identifier only — do NOT cast to int, sum, or compute on.",
            },
            "merchant": {
                "description": "Merchant name",
                "type": "string",
                "note": "All names start with 'fraud_' as a naming convention ONLY — this prefix is NOT a fraud indicator. Use the is_fraud column exclusively for fraud detection.",
            },
            "category": {
                "description": "Transaction merchant category",
                "type": "categorical",
                "cardinality": 14,
                "values": [
                    "misc_net", "grocery_pos", "entertainment", "gas_transport", "misc_pos",
                    "grocery_net", "shopping_net", "shopping_pos", "food_dining", "personal_care",
                    "health_fitness", "travel", "kids_pets", "home",
                ],
            },
            "amt": {
                "description": "Transaction amount in USD",
                "type": "float",
                "range": "0.0 to ~28000.0",
                "examples": [4.97, 107.23, 748.33, 1.06, 2159.44],
                "note": "Non-negative float. Use directly for arithmetic.",
            },
            "first": {
                "description": "Cardholder first name",
                "type": "string",
                "sensitivity": "pii",
                "note": "Personal identity information — avoid extracting or listing individual names.",
            },
            "last": {
                "description": "Cardholder last name",
                "type": "string",
                "sensitivity": "pii",
                "note": "Personal identity information — avoid extracting or listing individual names.",
            },
            "gender": {
                "description": "Cardholder gender",
                "type": "categorical",
                "values": ["M", "F"],
                "cardinality": 2,
            },
            "city": {
                "description": "Cardholder city of residence",
                "type": "string",
                "cardinality_approx": "high (many unique cities)",
            },
            "state": {
                "description": "Cardholder state (2-letter US code)",
                "type": "categorical",
                "cardinality": 51,
                "note": "Includes DC. Always uppercase 2-letter codes, e.g. 'CA', 'NY', 'TX'.",
            },
            "zip": {
                "description": "Cardholder zip code",
                "type": "string",
                "note": "Stored as string to preserve leading zeros.",
            },
            "lat": {
                "description": "Cardholder address latitude",
                "type": "float",
                "range": "approximately 20.0 to 65.0",
            },
            "long": {
                "description": "Cardholder address longitude",
                "type": "float",
                "range": "approximately -160.0 to -65.0",
            },
            "city_pop": {
                "description": "Population of cardholder's city",
                "type": "integer",
                "range": "1 to several million",
            },
            "job": {
                "description": "Cardholder occupation/job title",
                "type": "string",
                "sensitivity": "pii",
                "cardinality_approx": "high (many unique job titles)",
            },
            "dob": {
                "description": "Cardholder date of birth",
                "type": "date_string",
                "sensitivity": "pii",
                "format": "DD-MM-YYYY",
                "strptime": "%d-%m-%Y",
                "examples": ["15-03-1985", "01-11-1962"],
                "note": "Day-first format — NOT month-first. Use strptime('%d-%m-%Y') to parse.",
            },
            "trans_num": {
                "description": "Unique transaction identifier",
                "type": "identifier",
                "format": "hex string",
                "note": "Use as unique key only — do not compute on.",
            },
            "unix_time": {
                "description": "Transaction Unix timestamp",
                "type": "integer",
                "unit": "seconds since epoch",
                "note": "Can use datetime.fromtimestamp() or datetime.utcfromtimestamp() to convert.",
            },
            "merch_lat": {
                "description": "Merchant location latitude",
                "type": "float",
            },
            "merch_long": {
                "description": "Merchant location longitude",
                "type": "float",
            },
            "is_fraud": {
                "description": "Fraud label for the transaction",
                "type": "binary_integer",
                "values": [0, 1],
                "note": "1 = fraudulent, 0 = legitimate. This is the ONLY field to use for fraud detection — do NOT use merchant name as a fraud signal.",
            },
            "merch_zipcode": {
                "description": "Merchant zip code",
                "type": "string",
                "nullable": True,
                "null_rate": "~15%",
                "note": "Approximately 15% of rows have None/null. Always check: if row['merch_zipcode'] is not None before accessing.",
            },
        },
        "dataset_keys": {
            "transactions": (
                f"Stratified sample of {len(transactions)} transaction dicts with all 23 columns. "
                "Fraud rows overrepresented at ~20% for analytical utility. "
                "Use for cross-dimensional or per-transaction analysis."
            ),
            "total_transactions": f"Integer count of all {total_transactions:,} rows in the full dataset",
            "total_fraudulent": f"Integer count of all {total_fraudulent:,} fraudulent rows in the full dataset",
            "fraud_rate": f"Overall fraud rate as float ({fraud_rate:.6f}) computed from all rows",
            "date_range": "Dict with keys 'start' and 'end' as YYYY-MM-DD strings",
            "amount_distribution": "Dict: min, max, mean, median, std, p25, p75, p95, p99 of transaction amounts (all rows)",
            "category_stats": (
                "Dict: category_name -> {count, total_amt, fraud_count, fraud_rate, avg_amt}. "
                "14 categories, computed from all rows."
            ),
            "state_stats": (
                "Dict: state_code -> {count, total_amt, fraud_count}. "
                "51 US states, computed from all rows."
            ),
            "top_merchants": "List of top 20 merchants by count: [{merchant, count, total_amt, fraud_count, fraud_rate}]",
            "gender_breakdown": "Dict: 'M' or 'F' -> {count, fraud_count, total_amt}, computed from all rows",
            "time_series": "Dict: 'YYYY-MM' -> {count, total_amt, fraud_count}, monthly aggregates from all rows",
            "sample_info": "Dict: sample_size, fraud_in_sample, fraud_rate_in_sample, note",
        },
        "important_notes": [
            "CRITICAL: All merchant names begin with 'fraud_' — naming convention only, NOT a fraud signal. Use is_fraud column only.",
            "The transactions sample overrepresents fraud (~20%) vs real rate (~0.57%). Use pre-aggregated fields for global stats.",
            "cc_num is in scientific notation as a string (e.g. '2.70319E+15') — treat as identifier only.",
            "merch_zipcode has ~15% null values (Python None) — always handle None when iterating transactions.",
            "trans_date_trans_time and dob are in DD-MM-YYYY format (day first, NOT month first).",
            "Sandbox has no pandas/numpy. Use: list comprehensions, sum(), max(), min(), sorted(), collections.Counter, statistics, math.",
        ],
    }

    meta_path = output_dir / "metadata.json"
    logger.info(f"Writing {meta_path} ...")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    logger.info(f"metadata.json written: {meta_path.stat().st_size:,} bytes")

    logger.info("Done.")
    logger.info(f"  data.json     -> {data_path}")
    logger.info(f"  metadata.json -> {meta_path}")
    logger.info("")
    logger.info("Next step:")
    logger.info(
        f"  py scripts/run_eval.py "
        f"--dataset {data_path} "
        f"--metadata {meta_path} "
        f"--output eval_results.json --verbose"
    )


if __name__ == "__main__":
    main()
