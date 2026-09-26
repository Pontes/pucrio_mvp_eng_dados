---
name: python-etl
description: Implementa ou revisa scripts Python de ingestão, validação e qualidade do pipeline.
---

# Python ETL Skill

## Processo

1. Ler etapa correspondente em `docs/PLANO_MVP.md`.
2. Seguir `@10-python-pipeline.md` e `@20-privacy-lgpd.md`.
3. Preferir lotes, documentos como texto, metadados de proveniência.
4. Segregar linhas inválidas com motivo; nunca descartar em silêncio.
5. Cobrir com testes sintéticos (`@40-testes-dados.md`).
6. Atualizar evidências de contagem na documentação de qualidade.

## Restrições

- Sem PII em logs/prints.
- Sem alterar CSV original.
- Sem credenciais no código.
