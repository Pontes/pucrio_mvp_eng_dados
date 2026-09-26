Analise schema, carga e consultas MySQL do ambiente restrito.

**Escopo:** $ARGUMENTS

Siga `@30-database-mysql.md`, `@20-privacy-lgpd.md` e `@70-project-specific.md`.

1. Confirme tabelas/colunas existentes em `sql/` (não invente).
2. Mapeie camadas raw → stg → domínio.
3. Avalie índices para vínculos (documento, ID, CNES, datas).
4. Verifique metadados de proveniência e idempotência de carga.
5. Para mudança estrutural: impacto, rollback, risco a dados restritos.
6. Não sugira `DROP`/`TRUNCATE` sem plano autorizado.

Entregue: estado atual, riscos, recomendações priorizadas, SQL apenas quando baseado em evidência.
