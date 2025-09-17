import streamlit as st
import pandas as pd
from datetime import datetime
import io
import tempfile
import os
import traceback

# ---------------- PREVENÇÃO DE ERROS ----------------
try:
    st.set_page_config(page_title="Comissão de Vendas", layout="wide")
except:
    pass

# Verificação SEGURA das secrets (evita erro se não existirem)
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
    import camelot
    CAMELOT_DISPONIVEL = True
except ImportError:
    CAMELOT_DISPONIVEL = False
    st.sidebar.warning("⚠️ Camelot não instalado (PDF não será processado)")

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
    """Conectar no Google Sheets (se disponível)"""
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

# ---------------- FUNÇÕES ----------------
def extract_file(file_obj, coluna_valor):
    """Extrai Nome + Valor de PDF/Excel/CSV"""
    if file_obj.name.endswith(".pdf"):
        return extract_pdf(file_obj, coluna_valor)
    elif file_obj.name.endswith((".xls", ".xlsx")):
        return pd.read_excel(file_obj).rename(
            columns={list(pd.read_excel(file_obj).columns)[0]: "Consultor",
                     list(pd.read_excel(file_obj).columns)[1]: coluna_valor}
        )
    elif file_obj.name.endswith(".csv"):
        return pd.read_csv(file_obj).rename(
            columns={list(pd.read_csv(file_obj).columns)[0]: "Consultor",
                     list(pd.read_csv(file_obj).columns)[1]: coluna_valor}
        )
    else:
        st.error(f"Formato não suportado: {file_obj.name}")
        return pd.DataFrame(columns=["Consultor", coluna_valor])

def extract_pdf(file_obj, coluna_valor):
    """Extrai tabelas de um PDF e retorna DataFrame formatado"""
    if not CAMELOT_DISPONIVEL:
        return pd.DataFrame(columns=["Consultor", coluna_valor])
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            tmp_file.write(file_obj.getvalue())
            tmp_file_path = tmp_file.name

        tables = camelot.read_pdf(tmp_file_path, pages="all", flavor="stream")
        if len(tables) == 0:
            return pd.DataFrame(columns=["Consultor", coluna_valor])

        df_list = []
        for t in tables:
            df = t.df.copy()
            if len(df.columns) >= 2:
                df = df.rename(columns={df.columns[0]: "Consultor", df.columns[1]: coluna_valor})
                df_list.append(df)

        if df_list:
            final_df = pd.concat(df_list, ignore_index=True)
            final_df[coluna_valor] = pd.to_numeric(
                final_df[coluna_valor].astype(str).str.replace(r"[^\d,]", "", regex=True).str.replace(",", "."),
                errors="coerce"
            )
            final_df = final_df.dropna(subset=[coluna_valor])
            return final_df
        return pd.DataFrame(columns=["Consultor", coluna_valor])
    except Exception as e:
        st.error(f"Erro ao processar PDF: {str(e)}")
        st.sidebar.error(f"Traceback: {traceback.format_exc()}")
        return pd.DataFrame(columns=["Consultor", coluna_valor])
    finally:
        if 'tmp_file_path' in locals() and os.path.exists(tmp_file_path):
            os.unlink(tmp_file_path)

def processar_dados(df_pecas, df_servicos, ano, mes):
    """Une peças + serviços e calcula comissão"""
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

def salvar_google_sheets(df):
    """Salva dados no Google Sheets (se disponível)"""
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
    """Salva localmente como fallback"""
    try:
        if not os.path.exists("dados_comissao"):
            os.makedirs("dados_comissao")
        filename = f"dados_comissao/comissao_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        df.to_csv(filename, index=False, encoding="utf-8-sig")
        st.info(f"Dados salvos localmente em: {filename}")
        return True
    except:
        return False

def exportar(df, formato):
    """Exporta dados"""
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

# Upload
col1, col2 = st.columns(2)
with col1:
    st.subheader("📄 Arquivo - Peças")
    file_pecas = st.file_uploader("Upload Peças", type=["pdf", "xlsx", "xls", "csv"], key="pecas")
with col2:
    st.subheader("📄 Arquivo - Serviços")
    file_servicos = st.file_uploader("Upload Serviços", type=["pdf", "xlsx", "xls", "csv"], key="servicos")

# Inputs
col3, col4 = st.columns(2)
with col3:
    ano = st.number_input("**Ano**", min_value=2020, max_value=2100, value=datetime.now().year)
with col4:
    mes = st.selectbox("**Mês**",
                       ["Janeiro","Fevereiro","Março","Abril","Maio","Junho",
                        "Julho","Agosto","Setembro","Outubro","Novembro","Dezembro"],
                       index=datetime.now().month-1)

# Processar
if file_pecas and file_servicos:
    if st.button("🚀 Processar Arquivos", type="primary", key="processar_btn"):
        with st.spinner("Processando..."):
            df_pecas = extract_file(file_pecas, "Peças (R$)")
            df_servicos = extract_file(file_servicos, "Serviços (R$)")
            df_final = processar_dados(df_pecas, df_servicos, ano, mes)

        if not df_final.empty:
            st.subheader("📋 Resultados")
            st.dataframe(df_final, use_container_width=True)

            # Métricas
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Peças", f"R$ {df_final['Peças (R$)'].sum():,.2f}")
            col2.metric("Total Serviços", f"R$ {df_final['Serviços (R$)'].sum():,.2f}")
            col3.metric("Comissão Total", f"R$ {df_final['Comissão (R$)'].sum():,.2f}")

            # Exportação
            st.subheader("💾 Exportar")
            formato = st.radio("Formato:", ["Excel", "CSV"], horizontal=True, key="radio_export")
            exportar(df_final, formato)

            # Salvar
            st.subheader("💾 Salvar")
            if st.button("💾 Salvar Dados", key="salvar_btn"):
                if salvar_google_sheets(df_final):
                    st.success("✅ Dados salvos com sucesso!")
        else:
            st.error("❌ Não foi possível processar os dados.")
