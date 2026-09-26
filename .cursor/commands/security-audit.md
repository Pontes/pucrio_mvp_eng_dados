Audite privacidade e exposição de dados **sem corrigir ainda**.

**Escopo:** $ARGUMENTS

Use `@20-privacy-lgpd.md`, `@05-safety-guardrails.md` e `@70-project-specific.md`.

Verifique:

1. CSVs/fontes versionados ou indexáveis indevidamente?
2. PII em código, docs, notebooks, testes ou prints?
3. Logs/exceções com potencial de vazar identificadores?
4. Exportação para Databricks com colunas restritas?
5. Pseudônimo tratado incorretamente como anônimo?
6. Credenciais ou `.env` expostos?

Para cada achado: evidência (caminho), impacto, severidade, correção mínima sugerida.
Não altere arquivos nesta passagem.
