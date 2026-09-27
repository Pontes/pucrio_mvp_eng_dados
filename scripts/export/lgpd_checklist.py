"""Checklist de colunas proibidas na saída para Databricks."""

from __future__ import annotations

COLS_PROIBIDAS = frozenset(
    {
        "cns",
        "cns_paciente",
        "cns_do_paciente",
        "numero_cns_profissional",
        "n_cns_da_pessoa_cadastrada",
        "cpf",
        "cpf_paciente",
        "n_cpf",
        "data_de_nascimento",
        "dta_nasc",
        "dt_nasc",
        "data_nasc_paciente",
        "nis",
        "nis_paciente",
        "nome",
        "nome_social",
        "nome_paciente",
        "nome_do_paciente",
        "nome_da_pessoa_cadastrada",
        "nome_social_da_pessoa_cadastrada",
        "nome_da_mae",
        "nome_mae",
        "nome_da_mae_pessoa_cadastrada",
        "nome_profissional",
        "nome_do_profissional_solicitante",
        "profissional_consulta",
        "nome_acs",
        "logradouro",
        "tipo_de_logradouro",
        "numero",
        "complemento",
        "cep_logradouro",
        "telefone_contato",
        "email_contato",
        "email",
        "login",
        "login_utilizador",
        "src_id",
        "num_sus",
        "num_pront",
        "n_do_prontuario",
        "dnv",
        "n_dnv",
        "responsavel",
        "informa_es_complementares",
    }
)

COLS_META_OPCIONAL = frozenset({"carga_id", "linha_origem"})

TABELAS_EXPORT_CADASTRO = (
    "exp_paciente",
    "cadastro_pacientes_ubs",
    "exp_cadastro_presenca",
)
TABELAS_EXPORT_PROFISSIONAL = ("exp_profissional",)
TABELAS_EXPORT_CONSULTAS = ("consultas_ubs",)
TABELAS_EXPORT_EXAMES = ("exames_ubs",)
TABELAS_EXPORT_CID = ("atendimentos_cid_ubs",)
TABELAS_EXPORT_ACOMP = ("acompanhamento_diab_ubs", "acompanhamento_hiper_ubs")
TABELAS_EXPORT_FICHA = ("ficha_a_ubs",)

TABELAS_EXPORT_TODAS = (
    TABELAS_EXPORT_CADASTRO
    + TABELAS_EXPORT_PROFISSIONAL
    + TABELAS_EXPORT_CONSULTAS
    + TABELAS_EXPORT_EXAMES
    + TABELAS_EXPORT_CID
    + TABELAS_EXPORT_ACOMP
    + TABELAS_EXPORT_FICHA
)

TABELAS_LOCAIS_NAO_EXPORTAR = (
    "map_paciente_chave",
    "fila_identidade_conflito",
    "map_profissional_chave",
    "fila_profissional_conflito",
    "csv_cadastro_usuario_cap",
    "csv_consultas_cap",
    "csv_listagem_login",
    "csv_exames",
    "csv_atendimento_cid_param_bio",
    "csv_acompanhamento_diab",
    "csv_acompanhamento_hiper",
    "csv_consolidada",
    "csv_ficha_a_v2",
    "csv_ficha_a_v2_ext",
)


def colunas_proibidas_encontradas(colunas: set[str] | list[str]) -> list[str]:
    lower = {c.lower() for c in colunas}
    return sorted(lower & COLS_PROIBIDAS)
