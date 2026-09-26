Planeje uma etapa do pipeline **sem editar arquivos**.

**Objetivo:** $ARGUMENTS

Regras: `@00-project-context.md`, `@70-project-specific.md`, `@20-privacy-lgpd.md`, e a regra de stack aplicável (`@10-python-pipeline.md`, `@15-databricks-sql.md`, `@30-database-mysql.md`).

1. Relacione o pedido à etapa 1–14 e às perguntas 1–8 do `docs/PLANO_MVP.md`.
2. Confirme o que já existe no repositório (pastas, SQL, scripts).
3. Mapeie entradas, saídas, grão, dados sensíveis e reconciliação esperada.
4. Liste riscos de privacidade e qualidade.
5. Proponha plano incremental e critérios de aceite.
6. Não implemente ainda.

Formato:

- Contexto atual confirmado
- Etapa/perguntas afetadas
- Critérios de aceite
- Fluxo proposto
- Arquivos/tabelas impactados
- Dados sensíveis envolvidos
- Riscos e mitigação
- Plano em etapas
- Testes/reconciliação necessários
- Documentação afetada
- Perguntas bloqueantes (só se necessário)
