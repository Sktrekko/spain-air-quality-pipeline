-- Agrega NO2 por estación y día: promedio, máximo y percentil 98
with no2 as (
    select *
    from {{ ref('stg_mediciones') }}
    where magnitud = 'NO2'
),

agregado as (
    select
        estacion,
        municipio,
        fecha,

        round(avg(valor), 2)                                  as no2_medio_ugm3,
        round(max(valor), 2)                                  as no2_max_ugm3,
        round(approx_quantiles(valor, 100)[offset(98)], 2)   as no2_p98_ugm3,
        count(*)                                              as n_horas

    from no2
    group by 1, 2, 3
)

select * from agregado
