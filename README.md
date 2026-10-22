# Capacity-TV3

Extração de mapas de propagação e simulações Monte Carlo de capacidade **MIMO 2×2** e **MIMO-LDM** para TV 3.0. O fluxo prepara terreno, distância, visibilidade (LoS), probabilidade de LoS e perda de percurso com SuriaCov/P.1812; os dois modelos de capacidade reutilizam esses mapas.

O repositório inclui exemplos de extração e dos dois modelos para uma torre em 273 MHz. Campanhas particulares e mapas gerados ficam apenas na instalação local.

## Requisitos

- Git e **Python 3.12 ou superior**. Ambiente de referência: Python 3.13 no Windows; comandos para Linux/macOS estão abaixo.
- Espaço para aproximadamente 150 MB de bases compactadas, 151 MiB de bases descompactadas, o ambiente Python e os mapas/resultados produzidos. Reserve vários GB para a campanha completa.
- Internet para clonar e instalar dependências. As bases necessárias à extração estão incluídas no repositório.

O pacote inclui o adaptador SuriaCov e as tabelas de Py1812. Não é necessário clonar `pipeline-mosaico` ou usar um ambiente Python do autor. Leia a [origem e as limitações das bases](data/geography/README.md) e as [atribuições do código](THIRD_PARTY.md).

## 1. Clonar e instalar

### Windows — PowerShell

```powershell
git clone https://github.com/Joao-Henrique-Barbosa/Capacity-TV3.git
cd Capacity-TV3
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[preparation]"
.\.venv\Scripts\python.exe scripts/setup_project.py
$pythonTV3 = (Resolve-Path '.\.venv\Scripts\python.exe').Path
```

Se tiver Python 3.12, use `py -3.12` na criação do ambiente. Não é necessário ativar o venv; `$pythonTV3` aponta para seu interpretador. Em outro terminal, defina essa variável novamente a partir da raiz do clone.

### Linux/macOS — terminal

```bash
git clone https://github.com/Joao-Henrique-Barbosa/Capacity-TV3.git
cd Capacity-TV3
python3.13 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -e '.[preparation]'
./.venv/bin/python scripts/setup_project.py
```

Use `python3.12` se essa for sua versão instalada. Nos comandos seguintes, substitua `& $pythonTV3` por `./.venv/bin/python`.

O setup reconstrói o pacote de bases, verifica SHA-256, extrai em `data/geography/extracted/` e copia `configs/paths.example.yaml` para `configs/paths.local.yaml`. Pode ser executado novamente: verifica as bases e preserva a configuração existente. Para bases próprias ou outra pasta de resultados, edite `paths.local.yaml`. **Caminhos relativos nos YAMLs partem da pasta do próprio YAML.**

## 2. Primeira extração: uma torre

Comece com Coari/AM em 273 MHz. O exemplo mantém a grade de 360×360; a extração pode demorar, mesmo sendo uma única torre.

```powershell
& $pythonTV3 scripts/prepare_environments.py --config configs/extraction/exemplo_guia.yaml --dry-run
& $pythonTV3 scripts/prepare_environments.py --config configs/extraction/exemplo_guia.yaml
```

O primeiro comando confere a estrutura da configuração; **não valida todas as bases nem calcula propagação**. O segundo gera os mapas em `data/environments/` e publica `configs/extraction/datasets/exemplo_guia.yaml`. Aguarde sua conclusão antes de simular.

## 3. Simular MIMO e MIMO-LDM

Os exemplos usam poucas realizações para conhecer o fluxo; não constituem uma análise de convergência. MIMO-LDM pode ser executado independentemente de MIMO.

```powershell
& $pythonTV3 scripts/run_mimo_capacity.py --config configs/simulations/mimo_capacity/exemplo_guia.yaml --dry-run
& $pythonTV3 scripts/run_mimo_capacity.py --config configs/simulations/mimo_capacity/exemplo_guia.yaml

& $pythonTV3 scripts/run_mimo_ldm_capacity.py --config configs/simulations/mimo_ldm_capacity/exemplo_guia.yaml --dry-run
& $pythonTV3 scripts/run_mimo_ldm_capacity.py --config configs/simulations/mimo_ldm_capacity/exemplo_guia.yaml
```

O `--dry-run` da simulação valida os parâmetros e a integridade dos mapas; depende da extração concluída. Sem `--config`, os três scripts usam os respectivos `exemplo_guia.yaml`.

## 4. Configurar seus experimentos

Use `configs/towers.example.yaml` como modelo do cadastro e os três `exemplo_guia.yaml` como modelos de extração e simulação. Copie-os para YAMLs locais, ajuste os caminhos relativos, torres e parâmetros e execute os scripts com `--config`.

A seleção indicada em `datasets` deve ser a mesma gravada pela extração em `selection_output`. Mantenha os parâmetros das torres iguais nas duas etapas. Configurações particulares e seleções geradas são ignoradas pelo Git.

## Resultados, repetição e retomada

- Mapas: `data/environments/<torre>/<frequência>/<dataset_id>/`, com catálogo, metadados e imagens de diagnóstico.
- Capacidade: `results/<modelo>/<campaign>/<torre>/<frequência>/<cenário>/`; mapas numéricos em Mbps, gráficos e `metadata.json`.
- Resumos: `mimo_sweep_summary.csv` ou `ldm_sweep_summary.csv` na pasta da campanha.

`random_seed: null` sorteia e registra uma semente. Para reprodução, use o `base_seed` registrado e mantenha dados, parâmetros e versões. No MIMO-LDM, `nmse_values` representa **epsilon**; NMSE = epsilon².

A extração reutiliza mapas completos com `reuse_existing: true`. Uma simulação reexecutada **substitui os cenários selecionados**, sem retomada automática de Monte Carlo. Mude `campaign` para preservar um experimento anterior. Não execute duas instâncias sobre a mesma campanha.

### Tratamento próximo ao transmissor

Perfis com até quatro pontos usam perda em espaço livre calculada pela distância de cada pixel. No pixel usado como transmissor, usa-se a menor distância positiva do raster. Os demais perfis mantêm P.1812; não há preenchimento uniforme de um quadrado central.

Para recalcular mapas produzidos com uma versão anterior do extrator, configure `reuse_existing: false` no YAML de extração e execute novamente a preparação. Depois use a seleção de IDs atualizada na simulação. Resultados de capacidade existentes não são atualizados automaticamente.

## Estrutura e documentação

| Caminho | Conteúdo |
|---|---|
| `scripts/` | Setup, extração, simulações e importação de mapas antigos |
| `src/tv3_simulations/` | Modelos, propagação, validação e gráficos |
| `configs/` | Exemplos portáveis, cadastros e campanhas |
| `data/geography/` | Bases compactadas, manifesto de integridade e procedência |
| `data/environments/`, `results/`, `.cache/` | Gerados localmente; fora do Git |

- [Guia completo dos campos YAML e erros comuns](GUIA_CONFIGURACAO_E_EXECUCAO.md).
- [Configurações de demonstração dos dois modelos](configs/simulations/README.md).

Para apenas simular mapas já preparados, `pip install -e .` basta; copie também o catálogo, os mapas e a seleção de IDs compatível. O [guia](GUIA_CONFIGURACAO_E_EXECUCAO.md#11-saídas-e-importação) descreve a importação de dados antigos.
