# Seleção de 7 torres por UF, com alturas cadastradas de pelo menos 70 m

Foram selecionadas **35 torres**, sete em cada UF: DF, RJ, SP, MG e PE. **Não foi necessário reduzir o limiar de 70 m em nenhuma UF.** Os valores de altura e coordenadas são os registrados nas fontes, sem atribuição de alturas hipotéticas. Os identificadores continuam no formato `UF_código`.

## Arquivos

- [Mapa em PNG](../../../data/mapa_torres_7_por_uf.png), com visão geral e painéis por UF.
- [CSV das 35 torres](../../../data/torres_7_por_uf.csv), mantendo as sete colunas anteriores.
- [Cadastro YAML](../../towers_7_por_uf.yaml), com `tx_height_ov_ground` igual à altura cadastrada.

## Critérios

1. Usar as bases locais SURIA/Mosaico, com correspondência exata entre estação e antena. Usar altura preenchida da antena principal; na ausência dela, a única altura ou a maior cadastrada, conforme a escolha anterior do usuário. Os valores completos já tratados nos CSVs disponíveis são preservados.
2. Exigir altura e coordenadas válidas, ponto dentro da UF cadastrada e dentro dos limites aceitos pelo extrator. A situação de licenciamento não é filtro.
3. Agrupar pontos conectados por distâncias de até **100 m** como um mesmo local. Uma sequência de vizinhos pode formar um grupo com diâmetro maior que 100 m. Manter a estação com maior altura cadastrada como representante; desempatar pelo ID original.
4. Priorizar locais com altura **≥ 70 m**. Somente se uma UF tivesse menos de sete locais nesse intervalo, reduzir o limite até a sétima maior altura cadastrada. Essa exceção não precisou ser aplicada.
5. Buscar o maior afastamento da vizinha selecionada mais próxima (*maximin*): testar todas as candidatas como início, escolher sucessivamente a mais distante do conjunto e refinar a melhor solução por trocas individuais. Priorizar a menor distância entre as sete; usar a soma das distâncias como desempate. É uma heurística determinística, sem garantia de ótimo global.

As distâncias são de grande círculo, em quilômetros. Não representam raios de cobertura de rádio. A distribuição fica limitada à localização das torres que satisfazem o critério de altura; a existência de sete torres não garante distribuição por todo o território estadual.

| UF | Locais distintos elegíveis ≥ 70 m | Selecionadas | Alturas selecionadas | Menor distância entre selecionadas |
|---|---:|---:|---:|---:|
| DF | 16 | 7 | 99–178,12 m | 4,34 km |
| RJ | 16 | 7 | 74–610 m | 6,24 km |
| SP | 164 | 7 | 72,5–106 m | 213,25 km |
| MG | 37 | 7 | 70–96 m | 209,04 km |
| PE | 29 | 7 | 72–353 m | 31,07 km |

As alturas elevadas, incluindo 610 m no RJ e 353 m em PE, foram mantidas como constam na fonte. A seleção não certifica a precisão física do cadastro. Os números 1–7 nos painéis do PNG seguem a ordem de cada UF no CSV.

## Preparar os mapas de propagação

Em `Capacity-TV3`, confira a configuração:

```powershell
& ".\.venv\Scripts\python.exe" scripts/prepare_environments.py --config configs/extraction/torres_7_por_uf/todas.yaml --dry-run
```

Para executar:

```powershell
& ".\.venv\Scripts\python.exe" scripts/prepare_environments.py --config configs/extraction/torres_7_por_uf/todas.yaml
```

Para uma UF, substitua `todas.yaml` por `DF.yaml`, `RJ.yaml`, `SP.yaml`, `MG.yaml` ou `PE.yaml`. Execute os lotes em sequência. A preparação mantém grade de 360×360 e frequências de 0,195; 0,234; 0,273; 0,354 e 0,600 GHz: **175 extrações** para as 35 torres, ou 35 por UF.

Os mapas determinísticos e as imagens de `env_imgs/` serão salvos em `data/environments/<UF_código>/<frequência>/<dataset_id>/`. O YAML de seleção dos conjuntos gerados será salvo em `datasets/<UF>.yaml` ou `datasets/todas.yaml`, nesta pasta.
