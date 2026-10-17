{% macro extraction_start_utc() -%}
    '{{ var("extraction_start_date") }} 00:00:00+00'::timestamptz
{%- endmacro %}

{% macro extraction_end_exclusive_utc() -%}
    ('{{ var("extraction_end_date") }} 00:00:00+00'::timestamptz + interval '24 hours')
{%- endmacro %}
