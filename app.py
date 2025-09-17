import streamlit as st
import pandas as pd
from datetime import datetime
import io
import os
import traceback
import re
import pdfplumber  # para ler PDFs

# ---------------- PREVENÇÃO DE ERROS ----------------
try:
    st.set_page_config(page_title="Comissão de Vendas", layout="wide")
except:
    pass

# Verificação SEGURA das secrets
try:
    if "gcp_service_account" in st.secrets:
        st.sidebar.success("✅ Secrets do Google encontradas!")
        st.sidebar.write(f"Email: {st.secrets['gcp_service_account']['client_email']}")
    else:
        st.sidebar.warning("⚠️ Secrets do Google não configuradas")
except Exception:
    st.sidebar.info("ℹ️ Modo local - Secrets não disponíveis")

# Dependências opcionais
try:
    import gspread
    from google.oauth2.service_account import Credentials
    GOOGLE_SHEETS_DISPONIVEL = True
except ImportError:
    GOOGLE_SHEETS_DISPONIVEL = False
    st.sidebar.warning("⚠️ Google Sheets não disponível")

# ---------------- CONFIG ----------------
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1h3Okp_0aQvafltjoBbt6FbGQycrd8Vfuv1X-fKZqJQU/edit?usp=sharing"
ABA = "Comissao"

def get_google_client():
    if not GOOGLE_SHEETS_DISPONIVEL:
        return None
    try:
        if "gcp_service_account" in st.secrets:
            scopes = ["https://www.googleapis.com/auth/spreadsheets"]
            creds = Credentials.from_service_account_info(
                st.secrets["gcp_service_account"], scopes=scopes
            )
            return gspread.authorize(creds)
        else:
            return None
    except:
        return None

# ---------------- EXTRAÇÃO PDF ----------------
def extract_custom_pdf(text, coluna_valor, tipo="pecas"):
    """
    Extrai nomes e valores dos PDFs (Peças e Serviços)
    Aceita valor e nome na mesma linha ou em linhas diferentes
    """
    dados = []
    linhas = [l.strip() for l in text.splitlines() if l.strip()]

    i = 0
    while i < len(linhas):
        line = linhas[i]

        if tipo == "pecas":
            # Caso 1: tudo na mesma linha → "R$ 273.149,56TIAGO FERNANDES"
            m = re.search(r"R\$ ?([\d\.\,]+)\s*([A-ZÇÉÊÁÍÓÚÃÕa-zçéêáíóúãõ\s]+)$", line)
            if m:
                valor = m.group(1).replace(".", "").replace(",", ".")
                nome = m.group(2).strip()
                try:
                    valor = float(valor)
                    dados.append({"Consultor": nome, coluna_valor: valor})
                except:
                    pass

            # Caso 2: valor em uma linha, nome na próxima
            else:
                m_val = re.search(r"R\$ ?([\d\.\,]+)", line)
                if m_val and i + 1 < len(linhas):
                    nome = linhas[i+1].strip()
                    valor = m_val.group(1).replace(".", "").replace(",", ".")
                    try:
                        valor = float(valor)
                        dados.append({"Consultor": nome, coluna_valor: valor})
                        i += 1  # pular o nome
                    except:
                        pass

        else:  # serviços
            # Caso 1: tudo na mesma linha → "9533,70TIAGO FERNANDES"
            m = re.search(r"([\d\.\,]+)\s*([A-ZÇÉÊÁÍÓÚÃÕa-zçéêáíóúãõ\s]+)$", line)
            if m:
                valor = m.group(1).replace(".", "").replace(",", ".")
                nome = m.group(2).strip()
                try:
                    valor = float(valor)
                    dados.append({"Consultor": nome, coluna_valor: valor})
                except:
                    pass

            # Caso 2: valor em uma linha, nome na próxima
            else:
                m_val = re.search(r"([\d\.\,]+)", line)
                if m_val and i + 1 < len(linhas):
                    nome = linhas[i+1].strip()
                    valor = m_val.group(1).replace(".", "").replace(",", ".")
                    try:
                        valor = float(valor)
                        dados.append({"Consultor": nome, coluna_valor: valor})
                        i += 1
                    except:
                        pass
        i += 1

    df = pd.DataFrame(dados)
    if not df.empty:
        df = df.groupby("Consultor", as_index=False).sum()
    return df

def extract_file(file_obj, coluna_valor, tipo="pecas"):
    """Detecta tipo e chama parser certo"""
    if file_obj.name.endswith(".pdf"):
        text = ""
        file_obj.seek(0)
        with pdfplumber.open(file_obj) as pdf:
            for page in pdf.pages:
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                except:
                    continue

        # Debug: mostrar no sidebar as primeiras linhas
        st.sidebar.subheader(f"📄 Texto bruto ({tipo})")
        st.sidebar.text(text[:1500])  # Mostra até 1500 chars

        return extract_custom_pdf(text, coluna_valor, tipo)

    elif file_obj.name.endswith((".xls", ".xlsx")):
        df = pd.read_excel(file_obj)
        df = df.rename(columns={df.columns[0]: "Consultor", df.columns[1]: coluna_valor})
        return df

    elif file_obj.name.endswith(".csv"):
        df = pd.read_csv(file_obj)
        df = df.rename(columns={df.columns[0]: "Consultor", df.columns[1]: coluna_valor})
        return df

    else:
        st.error(f"Formato não suportado: {file_obj.name}")
        return pd.DataFrame(columns=["Consultor", coluna_valor])

# ---------------- PROCESSAMENTO ----------------
def processar_dados(df_pecas, df_servicos, ano, mes):
    if df_pecas.empty:
        df_pecas = pd.DataFrame(columns=["Consultor", "Peças (R$)"])
    if df_servicos.empty:
        df_servicos = pd.DataFrame(columns=["Consultor", "Serviços (R$)"])

    df = pd.merge(df_pecas, df_servicos, on="Consultor", how="outer").fillna(0)
    df["Total Geral (R$)"] = df["Peças (R$)"] + df["Serviços (R$)"]
    df["Comissão (R$)"] = df["Total Geral (R$)"] * 0.01
    df.insert(0, "Ano", ano)
    df.insert(1, "Mês", mes)
    df = df.sort_values("Total Geral (R$)", ascending=False)
    return df

# ---------------- SALVAR ----------------
def salvar_google_sheets(df):
    if not GOOGLE_SHEETS_DISPONIVEL:
        return salvar_localmente(df)
    try:
        client = get_google_client()
        if client is None:
            return salvar_localmente(df)

        sheet = client.open_by_url(SPREADSHEET_URL).worksheet(ABA)
        existing_data = sheet.get_all_values()
        if existing_data:
            existing = pd.DataFrame(existing_data[1:], columns=existing_data[0])
        else:
            existing = pd.DataFrame()

        final_df = pd.concat([existing, df], ignore_index=True)
        final_df = final_df.drop_duplicates(subset=["Ano", "Mês", "Consultor"], keep="last")

        sheet.clear()
        sheet.update([final_df.columns.values.tolist()] + final_df.values.tolist())
        return True
    except Exception as e:
        st.error(f"Erro ao salvar no Google Sheets: {str(e)}")
        return salvar_localmente(df)

def salvar_localmente(df):
    try:
        if not os.path.exists("dados_comissao"):
            os.makedirs("dados_comissao")
        filename = f"dados_comissao/comissao_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        df.to_csv(filename, index=False, encoding="utf-8-sig")
        st.info(f"Dados salvos localmente em: {filename}")
        return True
    except:
        return False

# ---------------- EXPORTAR ----------------
def exportar(df, formato):
    try:
        buf = io.BytesIO()
        if formato == "Excel":
            df.to_excel(buf, index=False, engine="openpyxl")
            st.download_button("⬇️ Baixar Excel", buf.getvalue(), "comissao.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               key="btn_excel")
        else:
            buf.write(df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"))
            st.download_button("⬇️ Baixar CSV", buf.getvalue(), "comissao.csv",
                               mime="text/csv", key="btn_csv")
    except Exception as e:
        st.error(f"Erro ao exportar: {str(e)}")

# ---------------- INTERFACE ----------------
st.title("📊 Comissão de Vendas")
st.markdown("---")

col1, col2 = st.columns(2)
with col1:
    st.subheader("📄 Arquivo - Peças")
    file_pecas = st.file_uploader("Upload Peças", type=["pdf", "xlsx", "xls", "csv"], key="pecas")
with col2:
    st.subheader("📄 Arquivo - Serviços")
    file_servicos = st.file_uploader("Upload Serviços", type=["pdf", "xlsx", "xls", "csv"], key="servicos")

col3, col4 = st.columns(2)
with col3:
    ano = st.number_input("**Ano**", min_value=2020, max_value=2100, value=datetime.now().year)
with col4:
    mes = st.selectbox("**Mês**",
                       ["Janeiro","Fevereiro","Março","Abril","Maio","Junho",
                        "Julho","Agosto","Setembro","Outubro","Novembro","Dezembro"],
                       index=datetime.now().month-1)

if file_pecas and file_servicos:
    if st.button("🚀 Processar Arquivos", type="primary", key="processar_btn"):
        with st.spinner("Processando..."):
            df_pecas = extract_file(file_pecas, "Peças (R$)", tipo="pecas")
            df_servicos = extract_file(file_servicos, "Serviços (R$)", tipo="servicos")
            df_final = processar_dados(df_pecas, df_servicos, ano, mes)

        if not df_final.empty:
            st.subheader("📋 Resultados")
            st.dataframe(df_final, use_container_width=True)

            col1, col2, col3 = st.columns(3)
            col1.metric("Total Peças", f"R$ {df_final['Peças (R$)'].sum():,.2f}")
            col2.metric("Total Serviços", f"R$ {df_final['Serviços (R$)'].sum():,.2f}")
            col3.metric("Comissão Total", f"R$ {df_final['Comissão (R$)'].sum():,.2f}")

            st.subheader("💾 Exportar")
            formato = st.radio("Formato:", ["Excel", "CSV"], horizontal=True, key="radio_export")
            exportar(df_final, formato)

            st.subheader("💾 Salvar")
            if st.button("💾 Salvar Dados", key="salvar_btn"):
                if salvar_google_sheets(df_final):
                    st.success("✅ Dados salvos com sucesso!")
        else:
            st.error("❌ Não foi possível processar os dados.")
