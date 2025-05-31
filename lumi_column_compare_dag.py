# !airflow
from lumi.dag import DAG
from airflow.operators.python_operator import PythonOperator
from lumi.bigQueryGetDataOperator import BigQueryGetDataOperator
from lumi.bigQueryInsertJobOperator import BigQueryInsertJobOperator
from gryphon.operators.Reports import Reports

dag = DAG(
    dag_id='lumi_column_compare_dag',
    tags=['lumi', 'column_compare'],
    schedule_interval=None,
    params={
        "src_prj": "axp-lumi.dw",
        "dest_prj": "axp-lumi.dw",
        "src_tbl": "risk_indv_cust",
        "dest_tbl": "risk_indv_customer_bureau",
        "temp_table": "temp_comparison_result",
        "final_table": "final_comparison_report"
    }
)

with dag:
    get_source_columns_query = PythonOperator(
        task_id='get_source_columns_query',
        provide_context=True,
        python_callable=Reports.get_source_columns,
    )

    fetch_source_columns = BigQueryGetDataOperator(
        task_id='fetch_source_columns',
        query="{{ ti.xcom_pull(task_ids='get_source_columns_query', key='srcColumnQueryKey') }}",
        limit=1000,
        dag=dag
    )

    get_target_columns_query = PythonOperator(
        task_id='get_target_columns_query',
        provide_context=True,
        python_callable=Reports.get_target_columns,
    )

    fetch_target_columns = BigQueryGetDataOperator(
        task_id='fetch_target_columns',
        query="{{ ti.xcom_pull(task_ids='get_target_columns_query', key='trgtColumnQueryKey') }}",
        limit=1000,
        dag=dag
    )

    generate_comparison_query = PythonOperator(
        task_id='generate_comparison_query',
        provide_context=True,
        python_callable=Reports.generate_comparison_query,
    )

    save_comparison_to_temp = BigQueryInsertJobOperator(
        task_id='save_comparison_to_temp_table',
        sql_parameters={},
        query="{{ ti.xcom_pull(task_ids='generate_comparison_query', key='store_comparison_query') }}",
        dag=dag
    )

    generate_final_report_query = PythonOperator(
        task_id='generate_final_report_query',
        provide_context=True,
        python_callable=Reports.generate_alert_query,
    )

    save_final_report = BigQueryInsertJobOperator(
        task_id='save_final_report_to_bq',
        query="{{ ti.xcom_pull(task_ids='generate_final_report_query', key='finalReportQuery') }}",
        sql_parameters={},
        dag=dag
    )

    # DAG dependencies
    get_source_columns_query >> fetch_source_columns
    fetch_source_columns >> get_target_columns_query >> fetch_target_columns
    fetch_target_columns >> generate_comparison_query >> save_comparison_to_temp
    save_comparison_to_temp >> generate_final_report_query >> save_final_report
