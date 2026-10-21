# Simulações das 12 torres por região

São 48 torres: 12 no Norte, Nordeste, Centro-Oeste e Sudeste. O Sul não integra a seleção existente.

Cada pasta `mimo_capacity/torres_12_por_regiao/` e `mimo_ldm_capacity/torres_12_por_regiao/` contém cinco configurações: `todas.yaml` (48 torres), `NORTE.yaml`, `NORDESTE.yaml`, `CENTRO_OESTE.yaml` e `SUDESTE.yaml` (12 torres cada).

Todas usam o [cadastro regional](../towers_12_por_regiao.yaml) e a seleção `configs/extraction/torres_12_por_regiao/datasets/<lote>.yaml`, gerada ao concluir a extração do mesmo lote. Os IDs são locais e não são versionados. Se já extraiu todas as torres, execute o lote regional com `reuse_existing: true` para gerar a seleção regional sem recalcular mapas compatíveis.

## Parâmetros

| Parâmetro | MIMO | MIMO-LDM |
|---|---|---|
| Frequências (MHz) | 195, 234, 273, 354, 600 | 195, 234, 273, 354, 600 |
| Potências (dBm) | 50 a 85, passo 5 | 40 a 80, passo 10 |
| Realizações de canal | 1000 | 50 |
| Realizações de erro | — | 50 |
| Razão de injeção (dB) | — | 0, 3, 5, 10 |
| Epsilon (`nmse_values`) | — | 0, 0.05, 0.1 |
| Cenários por ambiente | 8 | 60 |
| Tarefas por região | 480 | 3600 |
| Tarefas no lote completo | 1920 | 14400 |

Os parâmetros dos modelos padrão foram preservados, exceto torres, caminhos, nome da campanha e a expansão do MIMO-LDM de 273 MHz para as cinco frequências. No MIMO-LDM, NMSE = epsilon²; `chunk_size: 128` e `rng_mode: legacy` foram mantidos.

`write_plots: true` habilita gráficos. `random_seed: null` sorteia e registra uma semente; para reprodução, configure o inteiro `base_seed` registrado. `max_workers: null` usa o limite automático do executor; ajuste esse campo conforme a memória disponível.

## Validar e executar

Na raiz do projeto, valide os dois modelos sem iniciar Monte Carlo ou gravar resultados:

```powershell
& ".\.venv\Scripts\python.exe" scripts/run_mimo_capacity.py --config configs/simulations/mimo_capacity/torres_12_por_regiao/todas.yaml --dry-run
& ".\.venv\Scripts\python.exe" scripts/run_mimo_ldm_capacity.py --config configs/simulations/mimo_ldm_capacity/torres_12_por_regiao/todas.yaml --dry-run
```

Para executar, retire `--dry-run`. Para uma região, substitua `todas.yaml` por `NORTE.yaml`, `NORDESTE.yaml`, `CENTRO_OESTE.yaml` ou `SUDESTE.yaml`. Escolha entre o lote completo ou os quatro regionais para evitar repetir o processamento.

## Resultados

Cada lote tem uma campanha própria:

- Completo: `results/<modelo>/torres_12_por_regiao_todas/`.
- Regionais: `results/<modelo>/torres_12_por_regiao_norte/`, `torres_12_por_regiao_nordeste/`, `torres_12_por_regiao_centro_oeste/` e `torres_12_por_regiao_sudeste/`.

Os resumos são gravados por campanha. Reexecutar o mesmo lote substitui os cenários selecionados. Execute um lote por vez; não execute duas instâncias sobre a mesma campanha. Os arquivos `default.yaml` preservam a seleção anterior; os scripts sem argumentos usam `exemplo_guia.yaml`. Use sempre `--config` nesta campanha.
