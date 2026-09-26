Analise qualidade de dados e reconciliação **com evidências**.

**Escopo:** $ARGUMENTS

Use `@40-testes-dados.md`, `@30-database-mysql.md`, `@10-python-pipeline.md` e `@70-project-specific.md`.

1. Identifique fonte, camada (raw/stg/fato) e grão.
2. Liste regras de qualidade aplicáveis (vazios, documentos, vínculos, datas, bairro, duplicatas).
3. Defina métricas: total avaliado, aceitos, separados, taxa por regra.
4. Verifique reconciliação entrada = aceitos + separados.
5. Separe o que é indício vs contagem final validada.
6. Não cole PII; use apenas agregados e códigos de regra.

Saída: achados, evidências (caminhos), gaps, próximos passos de correção/documentação.
