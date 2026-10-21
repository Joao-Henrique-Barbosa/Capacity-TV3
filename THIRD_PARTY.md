# Atribuições e componentes externos

- **SuriaCov:** o módulo `src/tv3_simulations/propagation/suriacov_local.py` preserva a atribuição a Higo Thaian Pereira da Silva. A adaptação local permite carregar caminhos configuráveis e usar Py1812 incluído no pacote. Os dados estão descritos em [data/geography/README.md](data/geography/README.md).
- **Py1812:** implementação de eeveetza da recomendação ITU-R P.1812-6, distribuída com a tabela `P1812.npz`. Consulte o [aviso de origem](src/tv3_simulations/third_party/py1812/NOTICE.md). A presença de documentos de outras revisões da recomendação não altera a versão implementada.
- **Bibliotecas Python:** dependências e versões estão em `pyproject.toml`; cada biblioteca conserva sua própria licença.

Os cabeçalhos de autoria e avisos dos componentes foram mantidos. Este repositório não atribui uma nova licença aos componentes de terceiros. A cópia de origem do SuriaCov/Py1812 não continha um arquivo de licença separado; este aviso registra essa limitação de procedência.
