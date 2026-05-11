-- Falla si hay algún valor de NO2 negativo en staging
select *
from {{ ref('stg_mediciones') }}
where magnitud = 'NO2'
  and valor < 0
