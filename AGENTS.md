# AGENTS.md

## Objetivo

MVP acadêmico (PUC-Rio): utilização de unidades de saúde por bairro (fontes Vitacare / Maricá).

Trate como sistema com dados sensíveis de saúde. Priorize privacidade (LGPD), rastreabilidade e mudanças incrementais.

## Estado atual (reinício)

Arquitetura em construção. **Confirmado no código:**

```text
CSV (vitacare_fontes/) → MySQL schema vitacare_mvp (carga bruta)
```

Não presumir stg/domínio/Databricks já implementados.

## Fontes canônicas (locais — fora do Git)

- `docs/requisitos/PLANO_MVP.md`
- `docs/requisitos/requisito_mvp.pdf`
- `docs/entregaveis/`
- `.cursor/rules/` — regras do agente
- `README.md`

## Descoberta obrigatória

1. Confirmar pastas reais antes de editar.
2. Não inventar schema.
3. Não ler/colar PII real no chat.
4. Não versionar `vitacare_fontes/`, `docs/`, `.env` ou CSVs.

## Organização

| Módulo | Caminho | Responsabilidade |
|--------|---------|------------------|
| Fontes CSV | `vitacare_fontes/` (local) | Originais — nunca versionar |
| Import bruto | `scripts/ingest/import_bruto.py` | Todas as colunas/linhas → `vitacare_mvp` |
| DDL | `sql/10_schema_vitacare_mvp.sql` | Schema + controle de carga |
| Agents | `.cursor/`, `AGENTS.md` | Diretrizes Cursor |

## Regras principais

| Referência | Quando |
|------------|--------|
| `@00-project-context` | Sempre |
| `@10-python-pipeline` | Scripts Python |
| `@20-privacy-lgpd` | Dados pessoais / saída |
| `@30-database-mysql` | MySQL |
| `@70-project-specific` | Domínio Vitacare |

## Restrições

- Sem commit/push sem pedido explícito.
- Sem `DROP`/`TRUNCATE` em massa sem autorização.
- Sem Colab; Databricks só quando houver saída aprovada.
- Pseudonimização ≠ anonimização.
