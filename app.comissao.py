import streamlit as st
import pandas as pd
import camelot
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import io
import tempfile
import os

# ---------------- CONFIGURAÇÃO ----------------
st.set_page_config(page_title="Comissão de Vendas", layout="wide")

# Conectar no Google Sheets
def get_google_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=scopes
    )
    return gspread.authorize(creds)

SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1h3Okp_0aQvafltjoBbt6FbGQycrd8Vfuv1X-fKZqJQU/edit?usp=sharing"
ABA = "Comissao"

# ---------------- FUNÇÕES ----------------
def extract_pdf(file_obj, coluna_valor):
    """Extrai tabelas de um PDF e retorna DataFrame formatado"""
    # Salva o arquivo temporariamente para o Camelot processar
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(file_obj.read())
        tmp_file_path = tmp_file.name
    
    try:
        tables = camelot.read_pdf(tmp_file_path, pages="all", flavor="stream")
    finally:
        # Remove o arquivo temporário
        os.unlink(tmp_file_path)
    
    if len(tables) == 0:
        return pd.DataFrame(columns=["Consultor", coluna_valor])
    
    df_list = []
    for t in tables:
        df = t.df
        df.columns = df.iloc[0]
        df = df[1:]  # remove header duplicado
        df = df.rename(columns={df.columns[0]: "Consultor", df.columns[1]: coluna_valor})
        df[coluna_valor] = (
            df[coluna_valor].replace(r"[R$\.\,]", "", regex=True).astype(float)
        )
        df_list.append(df)
    return pd.concat(df_list, ignore_index=True)

def processar_dados(df_pecas, df_servicos, ano, mes):
    """Une peças + serviços e calcula comissão"""
    df = pd.merge(df_pecas, df_servicos, on="Consultor", how="outer").fillna(0)
    df["Total Geral (R$)"] = df["Peças (R$)"] + df["Serviços (R$)"]
    df["Comissão (R$)"] = df["Total Geral (R$)"] * 0.01
    df.insert(0, "Ano", ano)
    df.insert(1, "Mês", mes)
    return df

def salvar_google_sheets(df):
    client = get_google_client()
    sheet = client.open_by_url(SPREADSHEET_URL).worksheet(ABA)

    # pega os dados existentes
    existing = pd.DataFrame(sheet.get_all_records())

    # junta com novos
    final = pd.concat([existing, df], ignore_index=True)

    # sobrescreve na planilha
    sheet.clear()
    sheet.update([final.columns.values.tolist()] + final.values.tolist())

def exportar(df, formato):
    buf = io.BytesIO()
    if formato == "Excel":
        df.to_excel(buf, index=False)
        st.download_button("⬇️ Baixar Excel", buf.getvalue(), "comissao.xlsx")
    else:
        df.to_csv(buf, index=False, encoding="utf-8-sig")
        st.download_button("⬇️ Baixar CSV", buf.getvalue(), "comissao.csv")

# ---------------- INTERFACE ----------------
st.title("📊 Comissão de Vendas")

# Upload dos arquivos
col1, col2 = st.columns(2)
with col1:
    file_pecas = st.file_uploader("Upload PDF - Peças", type=["pdf"])
with col2:
    file_servicos = st.file_uploader("Upload PDF - Serviços", type=["pdf"])

# Inputs de Ano e Mês
col3, col4 = st.columns(2)
with col3:
    ano = st.number_input("Ano", min_value=2020, max_value=2100, value=datetime.now().year)
with col4:
    mes = st.selectbox("Mês", 
                       ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", 
                        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"],
                       index=datetime.now().month-1)

if file_pecas and file_servicos:
    # Processar os dados
    df_pecas = extract_pdf(file_pecas, "Peças (R$)")
    df_servicos = extract_pdf(file_servicos, "Serviços (R$)")
    df_final = processar_dados(df_pecas, df_servicos, ano, mes)
    
    # Mostrar dados processados
    st.subheader("📋 Dados Processados")
    st.dataframe(df_final, use_container_width=True)
    
    # Mostrar matriz de tratamento
    st.subheader("🔍 Matriz de Tratamento de Dados")
    
    col_info1, col_info2 = st.columns(2)
    with col_info1:
        st.write("**Dados de Peças Extraídos:**")
        st.dataframe(df_pecas, use_container_width=True)
        st.write(f"Total de registros: {len(df_pecas)}")
        
    with col_info2:
        st.write("**Dados de Serviços Extraídos:**")
        st.dataframe(df_servicos, use_container_width=True)
        st.write(f"Total de registros: {len(df_servicos)}")
    
    # Opções de exportação ANTES de salvar
    st.subheader("💾 Opções de Exportação")
    formato = st.radio("Formato de exportação:", ["Excel", "CSV"], horizontal=True)
    exportar(df_final, formato)
    
    # Botão para salvar no Google Sheets
    if st.button("💾 Processar e Salvar no Google Sheets"):
        salvar_google_sheets(df_final)
        st.success("Dados processados e salvos com sucesso!")

# Mostrar dados existentes
if st.checkbox("📖 Ver dados existentes"):
    client = get_google_client()
    sheet = client.open_by_url(SPREADSHEET_URL).worksheet(ABA)
    dados = pd.DataFrame(sheet.get_all_records())
    if not dados.empty:
        filtro_ano = st.selectbox("Filtrar Ano", sorted(dados["Ano"].unique()))
        filtro_mes = st.selectbox("Filtrar Mês", sorted(dados["Mês"].unique()))
        filtrado = dados[(dados["Ano"] == filtro_ano) & (dados["Mês"] == filtro_mes)]
        st.dataframe(filtrado, use_container_width=True)