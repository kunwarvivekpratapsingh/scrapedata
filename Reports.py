from airflow.models import BaseOperator
from typing import Any
from airflow.models.dag import DagContext

class Reports(BaseOperator):

    @staticmethod
    def get_source_columns(**kwargs):
        params = kwargs['params']
        src_prj = params["src_prj"]
        src_tbl = params["src_tbl"]

        query = f"""
        SELECT column_name, data_type
        FROM `{src_prj}`.INFORMATION_SCHEMA.COLUMNS
        WHERE table_name = "{src_tbl}"
        """
        kwargs["ti"].xcom_push(key='srcColumnQueryKey', value=query)

    @staticmethod
    def get_target_columns(**kwargs):
        params = kwargs['params']
        dest_prj = params["dest_prj"]
        dest_tbl = params["dest_tbl"]

        query = f"""
        SELECT column_name, data_type
        FROM `{dest_prj}`.INFORMATION_SCHEMA.COLUMNS
        WHERE table_name = "{dest_tbl}"
        """
        kwargs["ti"].xcom_push(key='trgtColumnQueryKey', value=query)

    @staticmethod
    def generate_comparison_query(**kwargs):
        ti = kwargs["ti"]
        params = kwargs["params"]

        src_prj = params["src_prj"]
        dest_prj = params["dest_prj"]
        src_tbl = params["src_tbl"]
        dest_tbl = params["dest_tbl"]
        temp_table = f"{dest_prj}.{params['temp_table']}"

        src_cols = ti.xcom_pull(task_ids='fetch_source_columns')
        dest_cols = ti.xcom_pull(task_ids='fetch_target_columns')

        dest_col_map = {col["column_name"]: col["data_type"] for col in dest_cols}
        query_parts = []

        for col in src_cols:
            col_name = col["column_name"]
            src_type = col["data_type"]
            dest_type = dest_col_map.get(col_name)

            if dest_type is None or src_type != dest_type:
                continue

            if src_type not in ["FLOAT64", "INT64"]:
                query_parts.append(f"""
                    SELECT "{col_name}" AS variable, "{src_type}" AS data_type,
                    (CASE WHEN a.cust_mkt_cd = "US" THEN "US" ELSE "INTL" END) AS Mkt,
                    CAST(NULL AS FLOAT64) AS ric_zero_count, CAST(NULL AS FLOAT64) AS lumi_zero_count,
                    CAST(NULL AS FLOAT64) AS ric_mean, CAST(NULL AS FLOAT64) AS lumi_mean,
                    COUNT(*) AS tot_cnt, COUNT(a.{col_name}) AS ric_count, COUNT(b.{col_name}) AS lumi_count
                    FROM `{src_prj}.{src_tbl}` a
                    INNER JOIN `{dest_prj}.{dest_tbl}` b ON a.cust_xref_id = b.cust_xref_id
                    GROUP BY variable, data_type, Mkt
                """)
            else:
                query_parts.append(f"""
                    SELECT "{col_name}" AS variable, "{src_type}" AS data_type,
                    (CASE WHEN a.cust_mkt_cd = "US" THEN "US" ELSE "INTL" END) AS Mkt,
                    COUNT(*) AS tot_cnt, COUNT(a.{col_name}) AS ric_count, COUNT(b.{col_name}) AS lumi_count,
                    SUM(CASE WHEN a.{col_name} = 0 THEN 1 ELSE 0 END) AS ric_zero_count,
                    SUM(CASE WHEN b.{col_name} = 0 THEN 1 ELSE 0 END) AS lumi_zero_count,
                    AVG(a.{col_name}) AS ric_mean, AVG(b.{col_name}) AS lumi_mean
                    FROM `{src_prj}.{src_tbl}` a
                    INNER JOIN `{dest_prj}.{dest_tbl}` b ON a.cust_xref_id = b.cust_xref_id
                    GROUP BY variable, data_type, Mkt
                """)

        combined_query = "\nUNION ALL\n".join(query_parts)
        final_query = f"""
        CREATE OR REPLACE TABLE `{temp_table}` AS
        {combined_query}
        """
        ti.xcom_push(key='store_comparison_query', value=final_query)

    @staticmethod
    def generate_alert_query(**kwargs):
        ti = kwargs["ti"]
        params = kwargs["params"]

        temp_table = f"{params['dest_prj']}.{params['temp_table']}"
        final_table = f"{params['dest_prj']}.{params['final_table']}"

        final_query = f"""
        CREATE OR REPLACE TABLE `{final_table}` AS
        SELECT *,
          SAFE_DIVIDE(ric_count - lumi_count, NULLIF(ric_count + lumi_count, 0)) AS Count_alert,
          SAFE_DIVIDE(ABS(ric_zero_count - lumi_zero_count), NULLIF(ric_zero_count + lumi_zero_count, 0)) AS Zero_alert,
          SAFE_DIVIDE(ABS(ric_mean - lumi_mean), NULLIF(ric_mean + lumi_mean, 0)) AS Mean_alert
        FROM `{temp_table}`
        """
        ti.xcom_push(key='finalReportQuery', value=final_query)
