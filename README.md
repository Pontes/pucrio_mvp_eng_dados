# MVP — Utilização de unidades de saúde por bairro

Pipeline acadêmico (PUC-Rio) a partir de fontes Vitacare (Maricá).

| Item | Valor |
|------|--------|
| Repositório | [Pontes/pucrio_mvp_eng_dados](https://github.com/Pontes/pucrio_mvp_eng_dados) |
| Licença do código | [MIT](LICENSE) |
| Dados | **Não** publicados neste repositório |

## Escopo atual (reinício)

Carga **bruta** de todos os CSVs locais para o MySQL no schema `vitacare_mvp` (todas as colunas/linhas, sem limpeza LGPD). Tratamento e análises ficam para etapas seguintes.

### O que permanece local (fora do Git)

- `vitacare_fontes/` — CSVs originais
- `docs/requisitos/` — enunciado e plano
- `docs/entregaveis/` — relatório de entrega
- `.env` / `docker-compose.yml` — MySQL local

### Código versionado

- `scripts/ingest/import_bruto.py` — importação bruta
- `scripts/ingest/apply_schema_vitacare_mvp.py` — cria schema
- `sql/10_schema_vitacare_mvp.sql`
- `scripts/db.py`, `requirements.txt`, testes sintéticos

### Local (fora do Git)

- `.cursor/` — agents/regras Cursor
- `AGENTS.md` — diretrizes do agente (local neste reinício)

## Carga bruta

```bash
pip install -r requirements.txt
# MySQL via docker-compose local + .env
PYTHONPATH=. python3 -m scripts.ingest.apply_schema_vitacare_mvp
PYTHONPATH=. python3 -m scripts.ingest.import_bruto --all
```

Opções: `--dry-run`, `--tipo LISTAGEM_CONSULTAS_CAP`, `--arquivo caminho.csv`.

## Privacidade

Não versionar CSVs, dumps ou PII. Não colar CPF, CNS, nomes ou endereços reais em commits, issues ou docs públicos.
