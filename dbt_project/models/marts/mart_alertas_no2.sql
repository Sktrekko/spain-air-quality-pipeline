-- Días con superación de umbrales UE de NO2
-- Umbral información: 180 µg/m³  |  Umbral alerta: 400 µg/m³
-- Valor límite anual: 40 µg/m³ (media anual)
with diario as (
    select * from {{ ref('int_no2_diario') }}
),

alertas as (
    select
        estacion,
        municipio,
        fecha,
        no2_medio_ugm3,
        no2_max_ugm3,
        no2_p98_ugm3,
        n_horas,

        case
            when no2_max_ugm3 >= 400 then 'ALERTA'
            when no2_max_ugm3 >= 180 then 'INFORMACION'
            when no2_medio_ugm3 >= 40 then 'LIMITE_ANUAL_SUPERADO'
            else 'NORMAL'
        end as nivel_alerta,

        no2_max_ugm3 >= 180 as supera_umbral_informacion,
        no2_max_ugm3 >= 400 as supera_umbral_alerta

    from diario
)

select * from alertas
order by fecha desc, no2_max_ugm3 desc
