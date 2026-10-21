# Bases geográficas da campanha

As três partes `geography.zip.part01` a `part03` formam um ZIP único. Execute `python scripts/setup_project.py` na raiz do clone para reconstruir, verificar e descompactar os arquivos. As partes têm menos de 50 MiB cada; não dependem de Git LFS ou de acesso às pastas do autor.

O [manifesto](manifest.json) registra SHA-256 e tamanho dos arquivos. As bases são cópias sem alteração dos arquivos usados pela campanha local; a divisão do ZIP não modifica seus conteúdos. As pastas extraídas e os mapas de propagação gerados não são versionados.

| Campo em `paths.local.yaml` | Base incluída |
|---|---|
| `radio_zone_grid_shp` | Grade radioclimática `zone_grid_resol_02g`, com `i_id`, `j_id` e `zone` |
| `brazil_terr_limits_shp` | Polígono territorial `brazil_poly`, usado pelo SuriaCov |
| `clutter_ref_tif` | MODIS MCD12Q1 v6.1, LC_Type1, ano 2022, em GeoTIFF |
| `brazil_geotiff` | SRTMGL3_NC v3, GeoTIFF com a reamostragem local identificada como `DWSample3x3` |

## Procedência

Os arquivos foram obtidos da distribuição local de dados do SuriaCov (`suria_coverage/data/IBGE`, `IBGP` e `SRTM`). A grade e o polígono são os artefatos utilizados pelo projeto; não são apresentados como novos produtos oficiais do IBGE. O histórico completo de transformação desses shapefiles não acompanha a cópia original. O manifesto identifica exatamente a versão distribuída.

O raster de cobertura do solo deriva do [MODIS/Terra+Aqua MCD12Q1 v6.1](https://data.nasa.gov/dataset/modis-terraaqua-land-cover-type-yearly-l3-global-500m-sin-grid-v061-fac3a). O relevo deriva do SRTM; consulte a [descrição dos produtos SRTM do LP DAAC](https://www.earthdata.nasa.gov/centers/lp-daac). Os rasters incluídos são recortes/processamentos locais, e não a coleção global original. Preserve os créditos das fontes ao utilizar seus dados.

## Compatibilidade e limites

A grade radioclimática corresponde às constantes em `configs/extraction/suriacov.yaml`: origem longitudinal −73,89°, referência de latitude 5,167° e passo 0,2°. Não substitua esse shapefile por um mapa de zonas arbitrário sem adaptar a indexação.

O código consulta as bases em coordenadas geográficas de latitude/longitude. Os rasters e o limite territorial devem ser compatíveis com essas coordenadas e cobrir toda a grade solicitada (±2° em torno da torre). Os shapefiles precisam dos arquivos auxiliares `.shx`, `.dbf` e `.prj`, incluídos no pacote.

As bases sustentam a seleção atual de 48 torres; isso não garante cobertura sem NoData para qualquer outra estação. O extrator também possui limites geográficos próprios e não cobre todo o Sul. Para novas torres, verifique extensão, CRS, valores ausentes, classes de clutter e zonas radioclimáticas antes de interpretar resultados.

Para bases próprias, mantenha-as fora de `extracted/` e ajuste `configs/paths.local.yaml`. O setup preserva esse YAML e recusa substituir uma base extraída que tenha sido modificada.
