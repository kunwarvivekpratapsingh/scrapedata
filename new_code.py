def generate_metric_query(**kwargs):
    task_instance = kwargs["ti"]

    # Pulling parameters from XCom
    src_table = task_instance.xcom_pull(task_ids='get_parameters', key='src_table')
    trg_table = task_instance.xcom_pull(task_ids='get_parameters', key='trgt_table')
    pkSource = task_instance.xcom_pull(task_ids='get_parameters', key='pkSource')
    pkTarget = task_instance.xcom_pull(task_ids='get_parameters', key='pkTarget')
    result_table = task_instance.xcom_pull(task_ids='get_parameters', key='data_report')

    # Pull schema info for matching columns
    src_result = task_instance.xcom_pull(task_ids='get_source_columns_task', key='query_result')[0]
    trg_result = task_instance.xcom_pull(task_ids='get_target_columns_task', key='query_result')[0]

    src_cols = src_result[0].split(',')
    trg_cols = trg_result[0].split(',')

    common_cols = list(set(src_cols).intersection(set(trg_cols)))

    if not common_cols:
        raise ValueError("No common columns found between source and target tables.")

    query = ""
    for col in common_cols:
        # Determine data type (could be improved if types are returned in XCom)
        # For now assume numeric types only if col name contains 'amt', 'cnt', 'id'
        if any(keyword in col.lower() for keyword in ['amt', 'cnt', 'id', 'score', 'val']):
            query += f"""
            SELECT '{col}' AS variable, 'NUMERIC' AS data_type,
                CASE WHEN a.cust_mkt_cd = 'US' THEN 'US' ELSE 'INTL' END AS Mkt,
                COUNT(*) AS tot_cnt,
                COUNT(a.{col}) AS src_count,
                COUNT(b.{col}) AS trg_count,
                SUM(CASE WHEN a.{col}=0 THEN 1 ELSE 0 END) AS src_zero_count,
                SUM(CASE WHEN b.{col}=0 THEN 1 ELSE 0 END) AS trg_zero_count,
                AVG(a.{col}) AS src_mean,
                AVG(b.{col}) AS trg_mean
            FROM `{src_table}` a
            INNER JOIN `{trg_table}` b ON a.{pkSource} = b.{pkTarget}
            GROUP BY Mkt
            UNION ALL
            """
        else:
            query += f"""
            SELECT '{col}' AS variable, 'CATEGORICAL' AS data_type,
                CASE WHEN a.cust_mkt_cd = 'US' THEN 'US' ELSE 'INTL' END AS Mkt,
                COUNT(*) AS tot_cnt,
                COUNT(a.{col}) AS src_count,
                COUNT(b.{col}) AS trg_count,
                NULL AS src_zero_count,
                NULL AS trg_zero_count,
                NULL AS src_mean,
                NULL AS trg_mean
            FROM `{src_table}` a
            INNER JOIN `{trg_table}` b ON a.{pkSource} = b.{pkTarget}
            GROUP BY Mkt
            UNION ALL
            """

    final_query = query.rstrip("UNION ALL\n")

    result_table = f"`{result_table}`"
    sql_stmt = f"""
    DROP TABLE IF EXISTS {result_table};
    CREATE TABLE {result_table} AS
    {final_query}
    """

    task_instance.xcom_push(key="sqlStmtKey", value=sql_stmt)
    task_instance.xcom_push(key="reportColumns", value=[
        "variable", "data_type", "Mkt", "tot_cnt",
        "src_count", "trg_count", "src_zero_count",
        "trg_zero_count", "src_mean", "trg_mean"
    ])
