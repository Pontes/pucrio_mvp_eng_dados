---
name: bug-fix
description: Corrige defeitos no pipeline com menor mudança segura e sem vazamento de PII.
---

# Bug Fix Skill

## Processo

1. Reproduzir com dados sintéticos ou agregados — não com PII real no chat.
2. Isolar causa raiz (parsing, schema, vínculo, agregação, export).
3. Aplicar menor correção alinhada às regras do plano.
4. Adicionar/ajustar teste de regressão sintético.
5. Verificar reconciliação de contagens se a carga/vínculo for afetado.
6. Registrar impacto documental se a regra de negócio mudar.
