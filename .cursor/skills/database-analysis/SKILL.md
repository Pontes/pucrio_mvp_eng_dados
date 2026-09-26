---
name: database-analysis
description: Analisa schema MySQL restrito, vínculos, índices e reconciliação do pipeline Vitacare.
---

# Database Analysis Skill

Use para DDL/DML, cargas, índices e camadas raw/stg/domínio.

## Processo

1. Confirmar schema em `sql/` e documentação — não inventar colunas.
2. Seguir `@30-database-mysql.md` e `@20-privacy-lgpd.md`.
3. Mapear proveniência (`arquivo_origem`, hash, competência).
4. Avaliar joins de identidade (ID/CPF/CNS) e risco de multiplicação de linhas.
5. Para mudanças: impacto, rollback e autorização se destrutivo.

## Restrições

- Sem `DROP`/`TRUNCATE` sem plano autorizado.
- Documentos como texto, nunca numéricos.
- Sem PII em exemplos ou saídas da análise.
