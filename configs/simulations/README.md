# Exemplos de simulação

Os exemplos `mimo_capacity/exemplo_guia.yaml` e `mimo_ldm_capacity/exemplo_guia.yaml` compartilham o cadastro [towers.example.yaml](../towers.example.yaml) e a seleção `configs/extraction/datasets/exemplo_guia.yaml`, gerada localmente pela extração.

| Parâmetro | MIMO | MIMO-LDM |
|---|---|---|
| Frequência | 273 MHz | 273 MHz |
| Potência | 60 dBm | 60 dBm |
| Realizações de canal | 10 | 10 |
| Realizações de erro | — | 5 |
| Razão de injeção | — | 3 dB |
| Epsilon | — | 0,05 |

São exemplos de funcionamento, não parâmetros de convergência científica. No MIMO-LDM, NMSE = epsilon².

Após concluir a extração, execute `python scripts/run_mimo_capacity.py` e `python scripts/run_mimo_ldm_capacity.py` na raiz do repositório. Acrescente `--dry-run` para validar parâmetros e mapas sem executar Monte Carlo. Os scripts usam os exemplos por padrão.

Para experimentos próprios, copie os exemplos, ajuste os caminhos e parâmetros e use `--config`. As configurações particulares ficam fora do Git. Resultados são gravados em `results/<modelo>/<campaign>/`. Reexecutar uma campanha substitui os cenários selecionados; altere `campaign` para preservar resultados anteriores.
