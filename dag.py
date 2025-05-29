import os
import pandas as pd
import numpy as np
from lumi.dag import DAG
from datetime import datetime
from airflow.models import Param
from lumi.bigQueryGetDataOperator import BigQueryGetDataOperator
from airflow.operators.bash_operator import BashOperator
from lumi.bigQueryInsertJobOperator import BigQueryInsertJobOperator
from airflow.operators.python_operator import PythonOperator
from airflow.operators.python_operator import PythonOperator
from lumi_dq4bq.dvt_bq_reports import Reports
from google.cloud import storage
from google.cloud import bigquery, Client, QueryJobConfig

# Set GCP project environment (ensure credentials are configured on Airflow worker)
os.environ["GOOGLE_CLOUD_PROJECT"] = "axp-lumi"


# Function to compare two BigQuery tables
# Accepts table/project names and computes basic stats (count, mean, zero-count)
# Saves result to CSV file with alert metrics


# Define the DAG with dynamic parameters

def compare_tables_dynamic(params, **kwargs):
    src_tbl = params["src_tbl"]
    dest_tbl = params["dest_tbl"]
    src_prj = params["src_prj"]
    dest_prj = params["dest_prj"]
    file_name = params["file_name"]

    client = storage.Client()
    result = pd.DataFrame()
    slots = 100  # Max columns to query in one loop

    # Step 1: Fetch column metadata from source and destination tables
    src_query = f"SELECT column_name, data_type FROM `{src_prj}`.INFORMATION_SCHEMA.COLUMNS WHERE table_name = '{src_tbl}'"
    dest_query = f"SELECT column_name, data_type FROM `{dest_prj}`.INFORMATION_SCHEMA.COLUMNS WHERE table_name = '{dest_tbl}'"

    src_df = client.query(src_query).to_dataframe().set_index("column_name")
    dest_df = client.query(dest_query).to_dataframe().set_index("column_name")

    # Step 2: Join on common columns that have the same data type
    combined = src_df.join(dest_df, rsuffix="_dest", how="inner")
    combined = combined[combined.data_type == combined.data_type_dest]

    # Step 3: For each chunk of columns, build and run query
    for s in range(1 + len(combined) // slots):
        query = ""
    for col in combined.index[slots * s: slots * (s + 1)]:
        dtype = combined.data_type[col]
    if dtype in ["FLOAT64", "INT64"]:
    # Numeric columns: calculate mean and zero counts
        query += f"""
     SELECT '{col}' AS variable, '{dtype}' AS data_type,
     (CASE WHEN a.cust_mkt_cd = 'US' THEN 'US' ELSE 'INTL' END) AS Mkt,
     COUNT(*) AS tot_cnt, COUNT(a.{col}) AS ric_count, COUNT(b.{col}) AS lumi_count,
     SUM(CASE WHEN a.{col} = 0 THEN 1 ELSE 0 END) AS ric_zero_count,
     SUM(CASE WHEN b.{col} = 0 THEN 1 ELSE 0 END) AS lumi_zero_count,
     AVG(a.{col}) AS ric_mean, AVG(b.{col}) AS lumi_mean
     FROM `{src_prj}.{src_tbl}` a
     INNER JOIN `{dest_prj}.{dest_tbl}` b ON a.cust_xref_id = b.cust_xref_id
     GROUP BY 1, 3
     UNION ALL
     """
    else:
    # String or categorical: only count matches
        query += f"""
     SELECT '{col}' AS variable, '{dtype}' AS data_type,
     (CASE WHEN a.cust_mkt_cd = 'US' THEN 'US' ELSE 'INTL' END) AS Mkt,
     NULL AS ric_zero_count, NULL AS lumi_zero_count,
     NULL AS ric_mean, NULL AS lumi_mean,
     COUNT(*) AS tot_cnt, COUNT(a.{col}) AS ric_count, COUNT(b.{col}) AS lumi_count
     FROM `{src_prj}.{src_tbl}` a
     INNER JOIN `{dest_prj}.{dest_tbl}` b ON a.cust_xref_id = b.cust_xref_id
     GROUP BY 1, 3
     UNION ALL
     """

    # Step 4: Execute query and collect results
    if query:
        df = client.query(query[:-10]).to_dataframe()  # remove trailing UNION ALL
    result = pd.concat([result, df], ignore_index=True)

    # Step 5: Compute alert metrics
    result["Count_alert"] = (result["ric_count"] - result["lumi_count"]) / \
                            (result["lumi_count"] + result["ric_count"]).replace(0, 1)
    result["Zero_alert"] = abs(result["ric_zero_count"] - result["lumi_zero_count"]) / (
            result["lumi_zero_count"] + result["ric_zero_count"]).replace(0, 1)
    result["Mean_alert"] = abs(result["ric_mean"] - result["lumi_mean"]) / (
            result["ric_mean"] + result["lumi_mean"]).replace(0, np.nan)

    # Step 6: Output to local file
    os.makedirs("LVT_results/LVT_dump", exist_ok=True)
    result.to_csv(f"LVT_results/LVT_dump/{file_name}.csv", index=False)


# Define the DAG with dynamic parameters
with DAG(
        dag_id="cdit_profiling_report",
        start_date=datetime(2024, 1, 1),
        schedule_interval=None,
        catchup=False,
        render_template_as_native_obj=True,
        params={
            "src_tbl": Param("risk_indv_cust", type="string"),
            "dest_tbl": Param("risk_indv_customer_bureau", type="string"),
            "src_prj": Param("axp-lumi.dw", type="string"),
            "dest_prj": Param("axp-lumi.dw", type="string"),
            "file_name": Param("risk_indv_customer_final_2605", type="string")
        }
) as dag:
    # Python task to execute the comparison logic
    run_comparison = PythonOperator(
        task_id="run_comparison",
        python_callable=compare_tables_dynamic,
        op_kwargs={"params": "{{ params }}"}
    )
