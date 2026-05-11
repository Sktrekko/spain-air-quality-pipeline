with source as (
    select *
    from {{ source('raw', 'mediciones_madrid') }}
),

renamed as (
    select
        estacion,
        municipio,
        magnitud,
        magnitud_cod,
        cast(fecha_hora as timestamp) as fecha_hora,
        cast(valor       as float64)  as valor,
        cast(ingestado_en as timestamp) as ingestado_en,

        -- Partición útil para filtros
        date(cast(fecha_hora as timestamp)) as fecha,
        extract(hour from cast(fecha_hora as timestamp)) as hora

    from source
    where valor is not null
      and valor >= 0
)

select * from renamed
