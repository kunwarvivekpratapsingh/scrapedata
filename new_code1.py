# ✅ MODIFIED: Pull all rows returned by get_source_columns_task and get_target_columns_task
    src_result = task_instance.xcom_pull(task_ids='get_source_columns_task', key='query_result')
    trg_result = task_instance.xcom_pull(task_ids='get_target_columns_task', key='query_result')

    # ✅ MODIFIED: Convert list of tuples [(col, dtype), ...] into dictionaries
    src_cols_dict = dict(src_result)
    trg_cols_dict = dict(trg_result)

    # ✅ MODIFIED: Get common columns with same data types
    common_cols = {
        col: src_cols_dict[col]
        for col in src_cols_dict
        if col in trg_cols_dict and src_cols_dict[col] == trg_cols_dict[col]
    }

    if not common_cols:
        raise ValueError("No common columns found between source and target tables.")
