"""Router modules keep re-exporting helpers that moved to /shared (audit A3).

Tests and overlays import ``convert_to_label_studio_format`` from
``routers.projects.import_export`` and ``_coerce_metric_value`` from
``routers.evaluations.results``. Both now live in /shared so worker-side code
can use them; the router names must stay bound to the same objects.
"""


def test_label_studio_converter_reexported_from_router():
    import export_stream
    from routers.projects.import_export import convert_to_label_studio_format

    assert convert_to_label_studio_format is export_stream.convert_to_label_studio_format


def test_coerce_metric_value_reexported_from_router():
    import metric_values
    from routers.evaluations.results import _coerce_metric_value
    from routers.evaluations.results._common import _coerce_metric_value as common_alias

    assert _coerce_metric_value is metric_values.coerce_metric_value
    assert common_alias is metric_values.coerce_metric_value


def test_report_service_uses_shared_coercion():
    import metric_values
    import report_service

    assert report_service.coerce_metric_value is metric_values.coerce_metric_value
