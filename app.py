import streamlit as st
import pandas as pd
from datetime import datetime
import pdfplumber
import re
import io

# ==============================
# LISTA COMPLETA DE CONSULTORES
# ==============================
CONSULTORES_VALIDOS = {
    "TIAGO FERNANDES DE LIMA": "TIAGO FERNANDES DE LIMA",
    "TARCISIO TORRES DE ANDRADE": "TARCISIO TORRES DE ANDRADE",
    "MARCELO TELES RIBEIRO": "Marcelo Teles Ribeiro",
    "ROSEANE CRUZ": "ROSEANE CRUZ",
    "JOSEZITO SILVA": "JOSEZITO SILVA",
    "NARDIE ARRUDA DA SILVA": "Nardie Arruda da Silva",
    "ELIVALDO SALES SILVA": "Elivaldo Sales Silva",
    "TARCIO HENRIQUE MARIANO DA SILVA": "TARCIO HENRIQUE MARIANO DA SILVA",
    "DAVID MARTINS": "DAVID MARTINS",
    "CAMILA AGUIAR": "Camila Aguiar",
    "SERGIO CARVALHO": "Sergio Carvalho",
    "FRANCISCO SEVERO SILVA": "Francisco Severo Silva",
    "RENATO TAVARES": "RENATO TAVARES",
    "ALINY BITENCOURT DOS REIS LIMA": "ALINY BITENCOURT DOS REIS LIMA",
    "FLAVIO ROGERIO DE ALMEIDA BARBOSA": "Flavio Rogerio de Almeida Barbosa"
}

# ==============================
# CHAVES: PRIMEIRO + SEGUNDO NOME
# ==============================
CONSULTORES_CHAVES = {
    "ALINY BITENCOURT": "ALINY BITENCOURT DOS REIS LIMA",
    "TARCIO HENRIQUE": "TARCIO HENRIQUE MARIANO DA SILVA",
    "ELIVALDO SALES": "Elivaldo Sales Silva",
    "RENATO TAVARES": "RENATO TAVARES",
    "JOSEZITO SILVA": "JOSEZITO SILVA",
    "DAVID MARTINS": "DAVID MARTINS",
    "TIAGO FERNANDES": "TIAGO FERNANDES DE LIMA",
    "TARCISIO TORRES": "TARCISIO TORRES DE ANDRADE",
    "MARCELO TELES": "Marcelo Teles Ribeiro",
    "ROSEANE CRUZ": "ROSEANE CRUZ",
    "NARDIE ARRUDA": "Nardie Arruda da Silva",
    "FRANCISCO SEVERO": "Francisco Severo Silva",
    "CAMILA AGUIAR": "CAMILA AGUIAR",
    "SERGIO CARVALHO": "SERGIO CARVALHO",
    "FLAVIO ROGERIO": "Flavio Rogerio de Almeida Barbosa",
}

# ==============================
# FUNÇÕES
# ==============================
def normalizar_nome(nome):
    nome_upper = nome.upper().strip()

    # 1 - tenta batida exata
    for chave, correto in CONSULTORES_VALIDOS.items():
        if chave in nome_upper:
            return correto

    # 2 - tenta batida por primeiro + segundo nome
    partes = nome_upper.split()
    if len(partes) >= 2:
        chave = f"{partes[0]} {partes[1]}"
        if chave in CONSULTORES_CHAVES:
            return CONSULTORES_CHAVES[chave]

    return None  # ignora se não achar


def preprocess_text(text):
    """ Junta linhas quebradas para evitar nomes cortados """
    lines = text.splitlines()
    fixed_lines = []
    buffer = ""
    for line in lines:
        if buffer:
            combined = buffer + " " + line
            if re.search(r"\d", line):
                fixed_lines.append(combined)
                buffer = ""
            else:
                buffer = combined
        else:
            if re.search(r"\d", line):
                fixed_lines.append(line)
            else:
                buffer = line
    if buffer:
        fixed_lines.append(buffer)
    return "\n".join(fixed_lines)


def extract_custom_pdf(file, coluna_valor):
    rows = []
    with pdfplumber.open(file) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        text = preprocess_text(text)

        for line in text.splitlines():
            match = re.search(r"(.+?)\s+([\d\.\,]+)", line)
            if match:
                nome = normalizar_nome(match.group(1))
                if not nome:
                    continue
                valor = match.group(2).replace(".", "").replace(",", ".")
                try:
                    valor = float(valor)
                except:
                    valor = 0.0
                rows.append({"Consultor": nome, coluna_valor: valor})

    if rows:
        df = pd.DataFrame(rows)
        df = df.groupby("Consultor", as_index=False).sum(numeric_only=True)
        return df
    return pd.DataFrame(columns=["Consultor", coluna_valor])


def processar_dados(df_pecas, df_servicos, ano, mes):
    if df_pecas.empty:
        df_pecas = pd.DataFrame(columns=["Consultor", "Peças (R$)"])
    if df_servicos.empty:
        df_servicos = pd.DataFrame(columns=["Consultor", "Serviços (R$)"])

    df_pecas = df_pecas.groupby("Consultor", as_index=False).sum(numeric_only=True)
    df_servicos = df_servicos.groupby("Consultor", as_index=False).sum(numeric_only=True)

    df = pd.merge(df_pecas, df_servicos, on="Consultor", how="outer").fillna(0)
    df = df.groupby("Consultor", as_index=False).sum(numeric_only=True)

    df["Total Geral (R$)"] = df["Peças (R$)"] + df["Serviços (R$)"]
    df["Comissão (R$)"] = df["Total Geral (R$)"] * 0.01
    df.insert(0, "Ano", ano)
    df.insert(1, "Mês", mes)
    return df


def exportar(df, formato):
    buf = io.BytesIO()
    if formato == "Excel":
        df.to_excel(buf, index=False, engine="openpyxl")
        st.download_button("⬇️ Baixar Excel", buf.getvalue(), "comissao.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        buf.write(df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"))
        st.download_button("⬇️ Baixar CSV", buf.getvalue(), "comissao.csv", mime="text/csv")

# ==============================
# INTERFACE STREAMLIT
# ==============================
st.set_page_config(page_title="Comissão de Vendas", layout="wide")
st.title("📊 Comissão de Vendas")
st.markdown("---")

# Upload
col1, col2 = st.columns(2)
with col1:
    st.subheader("📄 Arquivo - Peças")
    file_pecas = st.file_uploader("Upload Peças", type=["pdf"], label_visibility="collapsed")
with col2:
    st.subheader("📄 Arquivo - Serviços")
    file_servicos = st.file_uploader("Upload Serviços", type=["pdf"], label_visibility="collapsed")

st.markdown("---")

# Inputs
col3, col4 = st.columns(2)
with col3:
    ano = st.number_input("**Ano**", min_value=2020, max_value=2100, value=datetime.now().year)
with col4:
    mes = st.selectbox("**Mês**",
        ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
         "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"],
        index=datetime.now().month - 1)

st.markdown("---")

# Processamento
if file_pecas and file_servicos:
    if st.button("🚀 Processar Arquivos", type="primary"):
        with st.spinner("Processando..."):
            df_pecas = extract_custom_pdf(file_pecas, "Peças (R$)")
            df_servicos = extract_custom_pdf(file_servicos, "Serviços (R$)")
            df_final = processar_dados(df_pecas, df_servicos, ano, mes)

        if not df_final.empty:
            st.subheader("📋 Resultados")
            st.dataframe(df_final, use_container_width=True)

            # Totais
            total_pecas = df_final["Peças (R$)"].sum()
            total_servicos = df_final["Serviços (R$)"].sum()
            total_geral = df_final["Total Geral (R$)"].sum()
            total_comissao = df_final["Comissão (R$)"].sum()

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Peças", f"R$ {total_pecas:,.2f}")
            with col2:
                st.metric("Total Serviços", f"R$ {total_servicos:,.2f}")
            with col3:
                st.metric("Total Geral", f"R$ {total_geral:,.2f}")
            with col4:
                st.metric("Comissão Total", f"R$ {total_comissao:,.2f}")

            # Exportação
            st.subheader("💾 Exportar")
            formato = st.radio("Formato:", ["Excel", "CSV"], horizontal=True)
            exportar(df_final, formato)
        else:
            st.error("❌ Não foi possível processar os dados.")
