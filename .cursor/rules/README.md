# Regras do agente — MVP Engenharia de Dados

Kit adaptado ao pipeline **CSV → MySQL restrito → Databricks**, com privacidade LGPD.

## Preparação contínua

1. Manter `docs/PLANO_MVP.md` como referência de escopo.
2. Atualizar `00-project-context.mdc` quando pastas forem criadas.
3. Atualizar `70-project-specific-template.mdc` quando regras de vínculo/schema forem confirmadas no código.
4. Garantir `.gitignore` e `.cursorignore` cobrindo fontes e segredos.

## Regras ativas

| Menção @ | Arquivo | Escopo |
|----------|---------|--------|
| `@00-project-context.md` | [00-project-context.mdc](00-project-context.mdc) | Sempre |
| `@10-python-pipeline.md` | [10-python-pipeline.mdc](10-python-pipeline.mdc) | Python ETL |
| `@15-databricks-sql.md` | [15-databricks-sql.mdc](15-databricks-sql.mdc) | Databricks/SQL |
| `@20-privacy-lgpd.md` | [20-privacy-lgpd.mdc](20-privacy-lgpd.mdc) | Privacidade — always |
| `@30-database-mysql.md` | [30-database-mysql.mdc](30-database-mysql.mdc) | MySQL restrito |
| `@40-testes-dados.md` | [40-testes-dados.mdc](40-testes-dados.mdc) | Testes/reconciliação |
| `@60-documentation.md` | [60-documentation.mdc](60-documentation.mdc) | Docs/entrega |
| `@70-project-specific.md` | [70-project-specific-template.mdc](70-project-specific-template.mdc) | Domínio — always |

Complementares: [00-agent-workflow.mdc](00-agent-workflow.mdc), [05-safety-guardrails.mdc](05-safety-guardrails.mdc).

## Legado (desativado)

Arquivos `10-laravel-*`, `15-vue-*`, `20-security-and-inputs`, `40-testes-tdd`, `45-blade-*` existem só como redirecionamento — **não usar**.

## Comandos e skills

- `.cursor/commands/` — prompts operacionais
- `.cursor/skills/` — checklists especializados
- `.cursor/docs/` — notas auxiliares
