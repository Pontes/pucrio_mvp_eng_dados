# MVP — Análise de consultas nas unidades de saúde de Maricá

Projeto acadêmico de Engenharia de Dados da PUC-Rio, desenvolvido a partir de relatórios do sistema Vitacare. O trabalho reúne preparação local dos dados, processamento no Databricks e análises sobre a utilização das unidades de saúde.

O recorte analisado contém **312.339 registros de consultas**, de agosto a dezembro de 2025, com **88.992 pacientes atendidos em 27 unidades**.

Este README funciona como relatório do projeto. O código local está nas pastas `scripts/` e `sql/`. O notebook do Databricks deve acompanhar a entrega na pasta `notebooks/`.

## 1. Contexto de Negócios e Perguntas

O objetivo é organizar os dados para entender como os pacientes utilizam as unidades da rede. A proposta inicial incluía análises por bairro, período e unidade. Nesta versão, o foco ficou no volume de consultas, nos pacientes atendidos, no uso de mais de uma unidade e nos grupos de acompanhamento de diabetes e hipertensão.

| Pergunta | O que foi feito nesta versão |
|---|---|
| Quantos registros de consulta existem por dia, mês e unidade? | Consultas agregadas por período e unidade. |
| Quantos pacientes distintos foram atendidos por unidade e na rede? | Contagem na rede e análises por unidade. |
| Quantos atendimentos cada paciente teve no período? | Abordagem parcial, com médias agregadas por faixa etária e grupo de acompanhamento. |
| De quais bairros vêm os pacientes de cada unidade? | Ficou para uma próxima etapa, após revisão dos bairros e dos vínculos cadastrais. |
| Quantos pacientes utilizaram mais de uma unidade? | Contagem de pacientes e identificação de unidades que compartilham pacientes. |
| Por quais profissionais e categorias os pacientes foram atendidos? | Ficou para uma próxima etapa; foram verificadas ausências do identificador de profissional. |
| Onde estão os problemas de qualidade? | Foram avaliados campos essenciais, datas, identificadores e relacionamentos. |
| Como o uso varia ao longo dos meses? | Comparação do volume mensal de consultas no período disponível. |
| Como se distribuem os pacientes nos planos de diabetes e hipertensão? | Separação em três grupos e comparação das consultas e médias por paciente atendido. |

As análises complementares de exames, diagnósticos, procedimentos e condições domiciliares não foram desenvolvidas nesta entrega.

## 2. Carga dos Dados

As fontes são relatórios CSV do Vitacare, referentes à rede de saúde de Maricá. Os arquivos foram carregados em um banco MySQL local. Scripts Python prepararam tabelas de saída, com substituição de identificadores pessoais por códigos e retirada de identificadores diretos. As saídas foram exportadas em Parquet e carregadas no Databricks.

As extrações vão de setembro de 2025 a janeiro de 2026. A extração acontece no mês seguinte ao dos atendimentos: por exemplo, setembro de 2025 corresponde às consultas de agosto. Por isso, as análises temporais usam `dt_consulta`.

No Databricks, os arquivos foram colocados no volume `/Volumes/workspace/vitacare_mvp/entrada` e persistidos como tabelas Delta no schema `workspace.vitacare_mvp`. O notebook compara a quantidade de linhas dos arquivos com a das tabelas criadas.

As principais fontes das análises são `consultas_ubs`, `exp_paciente`, `cadastro_pacientes_ubs`, `acompanhamento_diab_ubs` e `acompanhamento_hiper_ubs`. Outras tabelas foram carregadas, mas não foram exploradas em profundidade.

**Uso dos dados:** os arquivos de pacientes não são publicados neste repositório. A licença MIT se refere ao código, não aos dados de saúde. A substituição de identificadores por códigos é pseudonimização e não equivale, por si só, à anonimização. A comprovação formal das condições de autorização de uso não está incluída nesta documentação.

<!-- Inserir imagem da carga e da comparação de contagens. -->

## 3. Modelagem e Catálogo de Dados

Foi criado um modelo estrela simples. A tabela `fato_consultas` guarda uma linha por registro de consulta e se relaciona com três dimensões: paciente, unidade e data.

```text
                    dim_paciente
                         |
dim_unidade ———— fato_consultas ———— dim_data
```

Os relacionamentos usam `paciente_id`, `cnes` e `dt_consulta = data`. A conferência manteve 312.339 registros após as ligações, sem consultas sem correspondência nas três dimensões.

### Catálogo do modelo analítico

| Tabela | Conteúdo e origem |
|---|---|
| `consultas_tratadas` | Consultas de `consultas_ubs`, com a data convertida de texto para DATE. |
| `fato_consultas` | Registros de `consultas_tratadas` usados no modelo analítico. |
| `dim_paciente` | Identificador e faixa etária de `exp_paciente`; 236.912 pacientes. |
| `dim_unidade` | Unidades das consultas, sem repetição de CNES; 27 unidades. |
| `dim_data` | Datas encontradas nas consultas; 123 datas. Não é um calendário completo. |
| `resumo_consultas_mensal` | Quantidade de registros de consulta por ano e mês. |
| `pacientes_grupos` | Pacientes identificados nos planos de diabetes e hipertensão, classificados em três grupos exclusivos. |

| Tabela | Campo | Tipo | Significado e domínio |
|---|---|---|---|
| `fato_consultas` | `consulta_id` | STRING | Identificador do registro; preenchido e distinto no recorte. |
| `fato_consultas` | `paciente_id` | STRING | Código do paciente; ligação com `dim_paciente`. |
| `fato_consultas` | `profissional_id` | STRING | Código do profissional; pode estar ausente. |
| `fato_consultas` | `cnes` | STRING | Código da unidade; ligação com `dim_unidade`. |
| `fato_consultas` | `dt_consulta` | DATE | Data do atendimento, de 01/08/2025 a 30/12/2025. |
| `fato_consultas` | `hora_consulta` | STRING | Horário no formato HH:mm, entre 00:00 e 23:59. |
| `fato_consultas` | `competencia_extracao` | STRING | Mês da extração, no formato AAAA-MM; de 2025-09 a 2026-01. |
| `dim_paciente` | `paciente_id` | STRING | Um código por paciente. |
| `dim_paciente` | `faixa_etaria` | STRING | Categorias de 0–9 até 80–89 e 90+. |
| `dim_unidade` | `cnes` | STRING | Um código por unidade. |
| `dim_unidade` | `unidade` | STRING | Nome da unidade associado ao CNES. |
| `dim_data` | `data` | DATE | Data presente nas consultas; chave da dimensão. |
| `dim_data` | `ano` | INT | Ano da consulta; 2025 neste recorte. |
| `dim_data` | `mes` | INT | Mês da consulta; de 8 a 12 neste recorte. |
| `resumo_consultas_mensal` | `ano` | INT | Ano da consulta. |
| `resumo_consultas_mensal` | `mes` | INT | Mês da consulta. |
| `resumo_consultas_mensal` | `registros_consultas` | BIGINT | Contagem mensal; de 52.851 a 74.725 no recorte. |
| `pacientes_grupos` | `paciente_id` | STRING | Código não vazio encontrado em pelo menos um dos planos. |
| `pacientes_grupos` | `grupo` | STRING | Somente diabetes, Somente hipertensão ou Ambos os planos. |

Este catálogo descreve o modelo analítico. O detalhamento de todas as colunas das fontes é uma limitação da documentação desta versão. As estruturas locais também estão definidas nos arquivos SQL do projeto.

<!-- Inserir imagem do catálogo do Databricks e das tabelas persistidas. -->

## 4. Pipeline de Dados

```text
CSV → MySQL local → preparação e exportação Parquet
    → entrada no Databricks → tratamento e validação
    → fato e dimensões → resumos e análises
```

O projeto usa a ideia de camadas Bronze, Silver e Gold. Na preparação local, os CSVs são preservados nas tabelas `csv_*` e depois tratados nas tabelas de saída. Dentro do notebook, as tabelas de entrada preservam os Parquets recebidos, `consultas_tratadas` representa o tratamento e o modelo analítico e seus resumos apoiam as análises. A entrada do Databricks já passou pela preparação local; não corresponde aos CSVs originais sem tratamento.

A transformação principal no Databricks converte `dt_consulta` para DATE. Identificadores são mantidos como texto, pois servem para ligar registros e não para cálculos. Horários e competências são preservados como texto após as verificações de formato.

### Como acompanhar a execução

1. Consultar os scripts de carga em `scripts/ingest/`, de preparação em `scripts/transform/` e de exportação em `scripts/export/`.
2. Em ambiente autorizado, preparar os arquivos Parquet e colocá-los no volume de entrada.
3. Disponibilizar o catálogo, schema e volume usados pelo notebook, ou adaptar os caminhos ao ambiente.
4. Executar o notebook na ordem: carga, validações, criação da tabela tratada, dimensões, fato, resumos e análises.

Os dados não acompanham o repositório. Portanto, a execução integral depende de acesso autorizado às fontes; o notebook e as evidências documentam os resultados obtidos. As cargas com `CREATE TABLE IF NOT EXISTS` não atualizam automaticamente tabelas existentes quando o arquivo muda.

## 5. Qualidade de Dados

As verificações priorizaram os campos necessários às análises.

| Verificação | Resultado observado |
|---|---|
| Identificador das consultas | 312.339 preenchidos e distintos. |
| Datas após conversão | Nenhuma ausente; intervalo de 01/08/2025 a 30/12/2025. |
| Horários | Nenhum ausente ou fora do formato verificado. |
| Competência de extração | Nenhuma ausente; relação com o mês seguinte confirmada. |
| Paciente e CNES nas consultas | Nenhum ausente. |
| Profissional nas consultas | 459 registros sem identificador, preservados nas análises gerais. |
| Dimensões | Chaves únicas; nenhuma consulta sem correspondência nas três dimensões. |
| Cadastro por unidade | 2.026 bairros ausentes, uma faixa etária ausente e 1.130 pacientes associados a mais de uma faixa. |
| Plano de diabetes | 717 registros sem identificador de paciente. |
| Plano de hipertensão | 1.641 registros sem identificador de paciente. |

Os registros sem identificador nos planos não entram na classificação de pacientes, pois não é possível relacioná-los com segurança. As fontes são preservadas. As divergências cadastrais foram registradas como limitações, sem excluir automaticamente os registros.

A unicidade de `consulta_id` comprova que o identificador não se repete no recorte; isoladamente, ela não comprova a ausência de dois registros diferentes do mesmo atendimento. A revisão de qualidade não cobre todos os atributos das fontes.

<!-- Inserir imagem das validações da fato e dos relacionamentos. -->

## 6. Análise de Dados

### Volume de consultas

| Mês de 2025 | Registros de consultas |
|---|---:|
| Agosto | 62.008 |
| Setembro | 63.122 |
| Outubro | 74.725 |
| Novembro | 59.633 |
| Dezembro | 52.851 |
| **Total** | **312.339** |

Outubro teve o maior volume e dezembro, o menor. Os dados mostram essa variação, mas não permitem afirmar sua causa.

### Pacientes e unidades

Foram identificados 88.992 pacientes atendidos em 27 unidades. Desses, 1.204 utilizaram mais de uma unidade: 1.187 passaram por duas e 17 por três. Compartilhar pacientes não comprova encaminhamento entre unidades.

### Diabetes e hipertensão

Os planos reúnem 41.016 pacientes distintos: 3.976 somente no plano de diabetes, 26.362 somente no de hipertensão e 10.678 em ambos. A classificação considera todas as extrações disponíveis.

| Grupo | Consultas no período | Pacientes atendidos | Média por paciente atendido |
|---|---:|---:|---:|
| Ambos os planos | 38.453 | 8.199 | 4,69 |
| Somente diabetes | 11.440 | 2.696 | 4,24 |
| Somente hipertensão | 68.040 | 16.781 | 4,05 |

Os pacientes presentes em ambos os planos tiveram a maior média de consultas. O grupo somente de hipertensão teve o maior volume total. As médias consideram apenas quem teve consulta no período e não permitem concluir gravidade da doença ou qualidade do acompanhamento. As consultas podem ter ocorrido por outros motivos, e o grupo não representa necessariamente a condição do paciente na data de cada consulta.

O gráfico foi produzido em Python, convertendo apenas o resultado agregado para Pandas e utilizando Matplotlib.

<!-- Inserir aqui: ![Média de consultas por grupo](imagens/media_consultas_grupo.png) -->

## 7. Autoavaliação

O trabalho permitiu construir um fluxo desde a preparação das fontes até as tabelas e análises no Databricks. Foi possível comparar os meses, contar pacientes distintos, observar o uso de mais de uma unidade e analisar os grupos de acompanhamento.

As principais dificuldades foram relacionar os pacientes entre arquivos, lidar com diferenças cadastrais e distinguir o mês da extração do mês do atendimento. As verificações ajudaram a identificar problemas e a evitar conclusões que os dados não sustentam.

A proposta inicial era mais ampla. As análises por bairro, profissionais, exames e condições domiciliares ficaram para uma próxima etapa. Também precisam ser ampliados o catálogo das fontes e a avaliação de qualidade de todos os atributos. O processamento ainda depende de etapas manuais, como o envio dos Parquets para o Databricks.

Como continuidade, pretendo revisar as divergências cadastrais, ampliar as análises e organizar uma atualização periódica. Nesta entrega, o foco foi demonstrar o fluxo de dados e responder parte das perguntas com resultados verificáveis.
