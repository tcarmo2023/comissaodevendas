import streamlit as st
import pandas as pd
from datetime import datetime
import io
import tempfile
import os
import time

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

# Tente importar as dependências opcionais
try:
    import camelot
    CAMELOT_DISPONIVEL = True
except ImportError:
    CAMELOT_DISPONIVEL = False
    st.sidebar.warning("⚠️ Camelot não instalado")

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GOOGLE_SHEETS_DISPONIVEL = True
except ImportError:
    GOOGLE_SHEETS_DISPONIVEL = False
    st.sidebar.warning("⚠️ Google Sheets não disponível")

# ---------------- CONFIGURAÇÃO ----------------
def get_google_client():
    """Conectar no Google Sheets (se disponível)"""
    if not GOOGLE_SHEETS_DISPONIVEL:
        return None
        
    try:
        # Verificação SEGURA das secrets
        try:
            if "gcp_service_account" in st.secrets:
                scopes = ["https://www.googleapis.com/auth/spreadsheets"]
                creds = Credentials.from_service_account_info(
                    st.secrets["gcp_service_account"], scopes=scopes
                )
                return gspread.authorize(creds)
            else:
                st.sidebar.warning("Credenciais do Google não configuradas.")
                return None
        except:
            return None
    except Exception as e:
        st.error(f"Erro ao conectar com Google Sheets: {str(e)}")
        return None

SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1h3Okp_0aQvafltjoBbt6FbGQycrd8Vfuv1X-fKZqJQU/edit?usp=sharing"
ABA = "Comissao"

# ---------------- FUNÇÕES ----------------
def extract_pdf(file_obj, coluna_valor):
    """Extrai tabelas de um PDF e retorna DataFrame formatado"""
    if not CAMELOT_DISPONIVEL:
        st.error("Camelot não está disponível para extrair PDFs.")
        return pd.DataFrame(columns=["Consultor", coluna_valor])
    
    try:
        # Salva o arquivo temporariamente
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            tmp_file.write(file_obj.getvalue())
            tmp_file_path = tmp_file.name
        
        tables = camelot.read_pdf(tmp_file_path, pages="all", flavor="stream")
        
        if len(tables) == 0:
            return pd.DataFrame(columns=["Consultor", coluna_valor])
        
        df_list = []
        for t in tables:
            df = t.df
            if len(df.columns) < 2:
                continue
                
            df.columns = df.iloc[0]
            df = df[1:]
            df = df.rename(columns={df.columns[0]: "Consultor", df.columns[1]: coluna_valor})
            
            # Limpa valores monetários
            df[coluna_valor] = (
                df[coluna_valor]
                .astype(str)
                .str.replace(r"[R$\s\.]", "", regex=True)
                .str.replace(",", ".")
                .replace("", "0")
                .astype(float)
            )
            
            df = df[df[coluna_valor] > 0]
            
            if not df.empty:
                df_list.append(df)
                
        if not df_list:
            return pd.DataFrame(columns=["Consultor", coluna_valor])
            
        return pd.concat(df_list, ignore_index=True)
        
    except Exception as e:
        st.error(f"Erro ao processar PDF: {str(e)}")
        return pd.DataFrame(columns=["Consultor", coluna_valor])
        
    finally:
        if 'tmp_file_path' in locals() and os.path.exists(tmp_file_path):
            try:
                os.unlink(tmp_file_path)
            except:
                pass

def processar_dados(df_pecas, df_servicos, ano, mes):
    """Une peças + serviços e calcula comissão"""
    try:
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
        
    except Exception as e:
        st.error(f"Erro ao processar dados: {str(e)}")
        return pd.DataFrame()

def salvar_google_sheets(df):
    """Salva dados no Google Sheets (se disponível)"""
    if not GOOGLE_SHEETS_DISPONIVEL:
        st.warning("Google Sheets não disponível - salvando localmente")
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
    """Salva dados localmente como fallback"""
    try:
        if not os.path.exists("dados_comissao"):
            os.makedirs("dados_comissao")
        
        filename = f"dados_comissao/comissao_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        df.to_csv(filename, index=False, encoding='utf-8-sig')
        st.info(f"Dados salvos localmente em: {filename}")
        return True
    except Exception as e:
        st.error(f"Erro ao salvar localmente: {str(e)}")
        return False

def exportar(df, formato):
    """Exporta dados para download"""
    try:
        buf = io.BytesIO()
        if formato == "Excel":
            df.to_excel(buf, index=False, engine='openpyxl')
            st.download_button(
                "⬇️ Baixar Excel", 
                buf.getvalue(), 
                "comissao.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            buf.write(df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig'))
            st.download_button(
                "⬇️ Baixar CSV", 
                buf.getvalue(), 
                "comissao.csv",
                mime="text/csv"
            )
    except Exception as e:
        st.error(f"Erro ao exportar: {str(e)}")

# ---------------- INTERFACE ----------------
st.title("📊 Comissão de Vendas")
st.markdown("---")

# Upload dos arquivos
col1, col2 = st.columns(2)
with col1:
    st.subheader("📄 PDF - Peças")
    file_pecas = st.file_uploader("Upload PDF - Peças", type=["pdf"], label_visibility="collapsed", key="pecas")

with col2:
    st.subheader("📄 PDF - Serviços")
    file_servicos = st.file_uploader("Upload PDF - Serviços", type=["pdf"], label_visibility="collapsed", key="servicos")

st.markdown("---")

# Inputs de Ano e Mês
col3, col4 = st.columns(2)
with col3:
    ano = st.number_input("**Ano**", min_value=2020, max_value=2100, value=datetime.now().year)
with col4:
    mes = st.selectbox("**Mês**", 
                       ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", 
                        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"],
                       index=datetime.now().month-1)

st.markdown("---")

if file_pecas and file_servicos:
    if st.button("🚀 Processar Arquivos", type="primary"):
        with st.spinner("Processando..."):
            df_pecas = extract_pdf(file_pecas, "Peças (R$)")
            df_servicos = extract_pdf(file_servicos, "Serviços (R$)")
            df_final = processar_dados(df_pecas, df_servicos, ano, mes)
        
        if not df_final.empty:
            # Mostrar dados
            st.subheader("📋 Resultados")
            st.dataframe(df_final, use_container_width=True)
            
            # Métricas
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Peças", f"R$ {df_final['Peças (R$)'].sum():,.2f}")
            with col2:
                st.metric("Total Serviços", f"R$ {df_final['Serviços (R$)'].sum():,.2f}")
            with col3:
                st.metric("Comissão Total", f"R$ {df_final['Comissão (R$)'].sum():,.2f}")
            
            # Exportação
            st.subheader("💾 Exportar")
            formato = st.radio("Formato:", ["Excel", "CSV"], horizontal=True)
            exportar(df_final, formato)
            
            # Salvar
            st.subheader("💾 Salvar")
            if st.button("💾 Salvar Dados"):
                if salvar_google_sheets(df_final):
                    st.success("✅ Dados salvos com sucesso!")
        else:
            st.error("❌ Não foi possível processar os dados.")

st.markdown("---")
st.info("💡 Dica: No Streamlit Cloud, configure as secrets para acesso ao Google Sheets")
