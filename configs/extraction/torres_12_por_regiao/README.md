# Extração de 12 estações por região

São **48 estações**, com IDs no formato `UF_código`, e **240 combinações estação/frequência**. As alturas e coordenadas são as registradas na base SURIA/Mosaico.

- [Cadastro das torres](../../towers_12_por_regiao.yaml)
- [Mapa das estações e grades](../../../data/mapa_torres_12_por_regiao.png)
- [Registro de seleção, fontes e validações](../../../data/torres_12_por_regiao_selecao.json)

## Seleção

A altura é a maior válida entre as antenas principais; na ausência de altura principal válida, usa-se a maior cadastrada na estação. Exigem-se altura positiva, latitude e longitude válidas, posição dentro da UF do cadastro e dos limites aceitos pelo extrator. O licenciamento não é filtro.

Locais conectados por distâncias de até 100 m são agrupados. Nesta revisão, as 39 estações sem lacunas foram mantidas. As nove substitutas foram escolhidas entre locais com terreno válido e os mesmos filtros costeiros, buscando aumentar a menor distância entre vizinhas e refinando somente as substitutas por trocas individuais. É uma heurística determinística, sem garantia de ótimo global.

Mantido o limiar de 55 m no Nordeste para favorecer a distribuição geográfica, com nove alturas abaixo de 70 m. Nas outras três regiões o limiar é 70 m. Todas as alturas são as cadastradas, sem alteração artificial.

| Região | Torres | Alturas (m) | Menor espaçamento (km) | Afastamento costeiro conservador mínimo (km) |
|---|---:|---:|---:|---:|
| Norte | 12 | 70–94 | 244.5 | 306.1 |
| Nordeste | 12 | 55–75.5 | 168.9 | 256.4 |
| Centro-Oeste | 12 | 71.5–97 | 218.1 | 541.0 |
| Sudeste | 12 | 70–123 | 143.4 | 261.1 |

## Distância do mar e disponibilidade dos dados

A distância usa três referências: a faixa costeira local (`coastal_zone.shp`), as células de mar ou zona costeira (`zone` 1 ou 3) do mapa radioclimático e o contorno externo da união dos países da base Natural Earth já instalada. Dissolver os países remove as fronteiras terrestres; assim, os litorais dos países vizinhos também entram na verificação. A base global é generalizada, na escala 1:110 milhões, e recebe margem adicional: mínimo de 275 km, contra 250 km nas referências locais. [Descrição da base global](https://www.naturalearthdata.com/downloads/110m-cultural-vectors/110m-admin-0-countries/).

As distâncias registradas são estimativas conservadoras relativas a essas bases, calculadas com vértices densificados, correção para a diferença entre esfera e elipsoide e margem para o tamanho da célula radioclimática. Não são medições de campo do litoral. O registro JSON detalha o método e contém os hashes das fontes utilizadas.

A verificação também considera a grade completa: 360 × 360 pontos, abrangendo ±2° ao redor da estação e o pequeno ajuste ao raster. Todas as 48 grades ficaram dentro das extensões dos rasters e do mapa radioclimático, sem interseção com a costa global ou a faixa costeira local, com **zero pontos de mar (`zones_map == 1`)** e sem clutter não classificado. Isso foi conferido antes da execução dos modelos de propagação.

As 48 grades foram verificadas após a mesma reamostragem usada pelo extrator: **zero células de terreno ausente e zero valores não finitos**. Foram substituídas cinco estações no Norte e quatro no Centro-Oeste; as outras 39 estações válidas foram preservadas. A região Sul foi excluída da campanha.

Rios, lagos e represas permanecem incluídos. A classe genérica de água do MODIS não foi removida. A amostra caracteriza o interior das quatro regiões; não representa seus ambientes litorâneos, nem necessariamente todas as UFs. Grades de estações diferentes podem se sobrepor.

## Parâmetros preservados

- Frequências: 195, 234, 273, 354 e 600 MHz.
- Grade: 360 × 360; área: 4° × 4°.
- Potência de referência: 1 kW; padrão de antena vazio/isotrópico; polarização horizontal (`1`).
- Altura do receptor: 10 m; `field_th: 50`; `excedance_perc: 50`.
- Mesmo `suriacov.yaml`, caminhos locais e `reuse_existing: true`.

## Executar

A partir de `Capacity-TV3`, valide o lote:

```powershell
& ".\.venv\Scripts\python.exe" scripts/prepare_environments.py --config configs/extraction/torres_12_por_regiao/todas.yaml --dry-run
```

Para iniciar as extrações:

```powershell
& ".\.venv\Scripts\python.exe" scripts/prepare_environments.py --config configs/extraction/torres_12_por_regiao/todas.yaml
```

Para processar uma região, troque `todas.yaml` por `NORTE.yaml`, `NORDESTE.yaml`, `CENTRO_OESTE.yaml` ou `SUDESTE.yaml`. Cada lote regional possui 60 combinações. Execute um lote por vez, pois todos compartilham o catálogo de ambientes.

Os mapas e imagens serão publicados em `data/environments/<UF_código>/<frequência>/<dataset_id>/`. Ao concluir cada lote, o extrator grava `datasets/<nome_do_lote>.yaml` nesta pasta. Esses arquivos são produzidos pela extração e devem ser usados posteriormente na configuração da simulação. Os comandos sem `--config` usam os exemplos de uma torre; use `--config` para selecionar este lote.

## Estações do mapa

A numeração reinicia em cada região. A coluna de afastamento é o menor dos três limites conservadores do registro de seleção.

| Região | Nº | Identificador | Município / UF | Altura (m) | Afastamento (km) |
|---|---:|---|---|---:|---:|
| Norte | 1 | `AM_57dbac0ec1a75` | Coari / AM | 86.14 | 1274.2 |
| Norte | 2 | `AM_57dbaae08af98` | Manacapuru / AM | 83.17 | 994.0 |
| Norte | 3 | `AM_57dbaae00239c` | Itacoatiara / AM | 83.48 | 799.3 |
| Norte | 4 | `PA_57dbab29e9626` | São Félix do Xingu / PA | 70 | 685.2 |
| Norte | 5 | `PA_57dbab276b156` | Itaituba / PA | 70 | 681.7 |
| Norte | 6 | `PA_57dbab2a7df18` | Tucuruí / PA | 70 | 306.1 |
| Norte | 7 | `PA_57dbac2c28e23` | Uruará / PA | 72 | 470.0 |
| Norte | 8 | `PA_57dbab28880e5` | Oriximiná / PA | 70 | 509.6 |
| Norte | 9 | `RO_57dbac3a6f7ba` | Rio Crespo / RO | 94 | 1110.1 |
| Norte | 10 | `TO_57dbac4f29124` | Gurupi / TO | 78 | 1030.8 |
| Norte | 11 | `TO_57dbac4ea9609` | Araguacema / TO | 71 | 776.7 |
| Norte | 12 | `TO_57dbab7ac04e4` | Palmeiras do Tocantins / TO | 82 | 467.0 |
| Nordeste | 1 | `BA_57dbac10a8194` | Correntina / BA | 75.5 | 537.9 |
| Nordeste | 2 | `BA_57dbaae7888b4` | Ibotirama / BA | 60 | 401.0 |
| Nordeste | 3 | `BA_57dbaae43ca1f` | Luís Eduardo Magalhães / BA | 60 | 676.5 |
| Nordeste | 4 | `BA_57dbaae5de114` | Central / BA | 70 | 348.5 |
| Nordeste | 5 | `CE_57dbaaf05ea41` | Caririaçu / CE | 58.25 | 268.1 |
| Nordeste | 6 | `MA_57dbab007d719` | Balsas / MA | 58 | 479.7 |
| Nordeste | 7 | `MA_57dbab01bba80` | Estreito / MA | 60 | 461.2 |
| Nordeste | 8 | `MA_57dbab0426325` | São Domingos do Maranhão / MA | 60 | 256.4 |
| Nordeste | 9 | `MA_57dbac1b6beed` | Açailândia / MA | 72 | 295.4 |
| Nordeste | 10 | `PE_57dbac2f175aa` | Lagoa Grande / PE | 64 | 348.9 |
| Nordeste | 11 | `PI_57dbac3166872` | São João do Piauí / PI | 55 | 527.8 |
| Nordeste | 12 | `PI_57dbab8cbf8e0` | Floriano / PI | 56 | 376.2 |
| Centro-Oeste | 1 | `GO_57dbaaf999935` | Catalão / GO | 81 | 600.4 |
| Centro-Oeste | 2 | `GO_57dbaad27b93d` | Santa Helena de Goiás / GO | 75 | 761.9 |
| Centro-Oeste | 3 | `GO_57dbac1a2eb1f` | Jussara / GO | 89 | 967.9 |
| Centro-Oeste | 4 | `GO_57dbac1abc02a` | Planaltina / GO | 97 | 779.2 |
| Centro-Oeste | 5 | `GO_57dbab864988d` | Porangatu / GO | 71.5 | 1020.1 |
| Centro-Oeste | 6 | `MS_57dbab8b1b076` | Três Lagoas / MS | 73.2 | 541.0 |
| Centro-Oeste | 7 | `MS_57dbac284d57c` | Rochedo / MS | 86 | 823.0 |
| Centro-Oeste | 8 | `MT_57dbac289373d` | Alto Araguaia / MT | 81 | 957.4 |
| Centro-Oeste | 9 | `MT_57dbac2988714` | Nova Brasilândia / MT | 76.5 | 1276.2 |
| Centro-Oeste | 10 | `MT_57dbab24db539` | Sorriso / MT | 73.7 | 1446.7 |
| Centro-Oeste | 11 | `MT_57dbac29c0a2e` | Porto Alegre do Norte / MT | 97 | 1082.2 |
| Centro-Oeste | 12 | `MT_57dbab2084412` | Alta Floresta / MT | 74 | 1192.6 |
| Sudeste | 1 | `MG_57dbac258394b` | Santo Antônio do Monte / MG | 96 | 295.2 |
| Sudeste | 2 | `MG_57dbac1e1b768` | Belo Horizonte / MG | 81 | 263.5 |
| Sudeste | 3 | `MG_57dbac21ef0d2` | Ituiutaba / MG | 123 | 595.2 |
| Sudeste | 4 | `MG_57dbac1d9c457` | Araguari / MG | 88 | 568.6 |
| Sudeste | 5 | `MG_57dbac1fef75c` | Corinto / MG | 79 | 402.3 |
| Sudeste | 6 | `MG_57dbac24097b7` | Paracatu / MG | 88 | 650.5 |
| Sudeste | 7 | `SP_57dbac46b44f8` | Assis / SP | 70 | 298.1 |
| Sudeste | 8 | `SP_57dbac4b752ce` | Presidente Epitácio / SP | 106 | 478.6 |
| Sudeste | 9 | `SP_57dbac4c583c6` | Santa Lúcia / SP | 83 | 261.1 |
| Sudeste | 10 | `SP_57dbac4a42024` | Neves Paulista / SP | 80 | 417.6 |
| Sudeste | 11 | `SP_57dbac4ae2733` | Pereira Barreto / SP | 77 | 527.5 |
| Sudeste | 12 | `SP_57dbac4baa6ac` | Ribeirão Corrente / SP | 70 | 366.7 |
