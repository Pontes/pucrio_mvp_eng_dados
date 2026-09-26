---
name: security-audit
description: Auditoria de privacidade LGPD e exposição de dados de saúde no MVP.
---

# Security / Privacy Audit Skill

## Processo

1. Aplicar `@20-privacy-lgpd.md` e `@05-safety-guardrails.md`.
2. Procurar CSVs versionados, samples reais, secrets e logs sensíveis.
3. Revisar exports Databricks e colunas de saída.
4. Distinguir pseudonimização de anonimização.
5. Classificar achados por severidade com evidência de caminho.
6. Propor correção mínima — sem implementar nesta skill de auditoria.

## Não fazer

- Colar registros pessoais no relatório.
- Ler `.env` ou imprimir credenciais.
