import streamlit as st
import pandas as pd
import camelot
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import io
import tempfile
import os
import time

# ---------------- PREVENÇÃO DE ERROS ----------------
# Prevenir erro de UI do Streamlit
try:
    st.set_page_config(page_title="Comissão de Vendas", layout="wide")
except:
    pass
st.markdown('<style>div[data-testid="stToolbar"] { display: none !important; }</style>', unsafe_allow_html=True)
time.sleep(0.1)

# ---------------- CONFIGURAÇÃO ----------------
# Conectar no Google Sheets
def get_google_client():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"], scopes=scopes
        )
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Erro ao conectar com Google Sheets: {str(e)}")
        return None

SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1h3Okp_0aQvafltjoBbt6FbGQycrd8Vfuv1X-fKZqJQU/edit?usp=sharing"
ABA = "Comissao"

# ---------------- FUNÇÕES ----------------
def extract_pdf(file_obj, coluna_valor):
    """Extrai tabelas de um PDF e retorna DataFrame formatado"""
    try:
        # Salva o arquivo temporariamente para o Camelot processar
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            tmp_file.write(file_obj.getvalue())
            tmp_file_path = tmp_file.name
        
        tables = camelot.read_pdf(tmp_file_path, pages="all", flavor="stream")
        
        if len(tables) == 0:
            return pd.DataFrame(columns=["Consultor", coluna_valor])
        
        df_list = []
        for t in tables:
            df = t.df
            # Pula tabelas vazias ou com poucas colunas
            if len(df.columns) < 2:
                continue
                
            df.columns = df.iloc[0]
            df = df[1:]  # remove header duplicado
            df = df.rename(columns={df.columns[0]: "Consultor", df.columns[1]: coluna_valor})
            
            # Limpa e converte valores monetários
            df[coluna_valor] = (
                df[coluna_valor]
                .astype(str)
                .str.replace(r"[R$\s\.]", "", regex=True)
                .str.replace(",", ".")
                .replace("", "0")
                .astype(float)
            )
            
            # Remove linhas com valores zerados ou inválidos
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
        # Remove o arquivo temporário
        if 'tmp_file_path' in locals() and os.path.exists(tmp_file_path):
            os.unlink(tmp_file_path)

def processar_dados(df_pecas, df_servicos, ano, mes):
    """Une peças + serviços e calcula comissão"""
    try:
        # Garante que os DataFrames tenham as colunas necessárias
        if df_pecas.empty:
            df_pecas = pd.DataFrame(columns=["Consultor", "Peças (R$)"])
        if df_servicos.empty:
            df_servicos = pd.DataFrame(columns=["Consultor", "Serviços (R$)"])
        
        # Merge dos dados
        df = pd.merge(df_pecas, df_servicos, on="Consultor", how="outer").fillna(0)
        
        # Calcula totais e comissão
        df["Total Geral (R$)"] = df["Peças (R$)"] + df["Serviços (R$)"]
        df["Comissão (R$)"] = df["Total Geral (R$)"] * 0.01
        
        # Adiciona informações de data
        df.insert(0, "Ano", ano)
        df.insert(1, "Mês", mes)
        
        # Ordena por total geral (decrescente)
        df = df.sort_values("Total Geral (R$)", ascending=False)
        
        return df
        
    except Exception as e:
        st.error(f"Erro ao processar dados: {str(e)}")
        return pd.DataFrame()

def salvar_google_sheets(df):
    try:
        client = get_google_client()
        if client is None:
            return False
            
        sheet = client.open_by_url(SPREADSHEET_URL).worksheet(ABA)
        
        # Pega os dados existentes
        existing_data = sheet.get_all_values()
        if existing_data:
            existing = pd.DataFrame(existing_data[1:], columns=existing_data[0])
        else:
            existing = pd.DataFrame()
        
        # Junta com novos dados
        final_df = pd.concat([existing, df], ignore_index=True)
        
        # Remove duplicatas baseadas em Ano, Mês e Consultor
        final_df = final_df.drop_duplicates(subset=["Ano", "Mês", "Consultor"], keep="last")
        
        # Atualiza a planilha
        sheet.clear()
        sheet.update([final_df.columns.values.tolist()] + final_df.values.tolist())
        
        return True
        
    except Exception as e:
        st.error(f"Erro ao salvar no Google Sheets: {str(e)}")
        return False

def exportar(df, formato):
    try:
        buf = io.BytesIO()
        if formato == "Excel":
            with pd.ExcelWriter(buf, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Comissões')
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
    file_pecas = st.file_uploader("Upload PDF - Peças", type=["pdf"], label_visibility="collapsed")
    if file_pecas:
        st.success(f"✅ Arquivo carregado: {file_pecas.name}")

with col2:
    st.subheader("📄 PDF - Serviços")
    file_servicos = st.file_uploader("Upload PDF - Serviços", type=["pdf"], label_visibility="collapsed")
    if file_servicos:
        st.success(f"✅ Arquivo carregado: {file_servicos.name}")

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
    # Processar os dados
    with st.spinner("Processando arquivos PDF..."):
        df_pecas = extract_pdf(file_pecas, "Peças (R$)")
        df_servicos = extract_pdf(file_servicos, "Serviços (R$)")
        df_final = processar_dados(df_pecas, df_servicos, ano, mes)
    
    if not df_final.empty:
        # Mostrar dados processados
        st.subheader("📋 Dados Processados")
        st.dataframe(df_final, use_container_width=True)
        
        # Mostrar totais
        col_total1, col_total2, col_total3 = st.columns(3)
        with col_total1:
            st.metric("Total Peças", f"R$ {df_final['Peças (R$)'].sum():,.2f}")
        with col_total2:
            st.metric("Total Serviços", f"R$ {df_final['Serviços (R$)'].sum():,.2f}")
        with col_total3:
            st.metric("Comissão Total", f"R$ {df_final['Comissão (R$)'].sum():,.2f}")
        
        # Mostrar matriz de tratamento
        st.subheader("🔍 Matriz de Tratamento de Dados")
        
        col_info1, col_info2 = st.columns(2)
        with col_info1:
            st.write("**Dados de Peças Extraídos:**")
            if not df_pecas.empty:
                st.dataframe(df_pecas, use_container_width=True)
                st.write(f"Total de registros: {len(df_pecas)}")
            else:
                st.warning("Nenhum dado extraído do PDF de Peças")
        
        with col_info2:
            st.write("**Dados de Serviços Extraídos:**")
            if not df_servicos.empty:
                st.dataframe(df_servicos, use_container_width=True)
                st.write(f"Total de registros: {len(df_servicos)}")
            else:
                st.warning("Nenhum dado extraído do PDF de Serviços")
        
        # Opções de exportação
        st.subheader("💾 Opções de Exportação")
        formato = st.radio("Formato de exportação:", ["Excel", "CSV"], horizontal=True)
        exportar(df_final, formato)
        
        # Botão para salvar no Google Sheets
        st.markdown("---")
        if st.button("💾 Salvar no Google Sheets", type="primary"):
            with st.spinner("Salvando dados..."):
                if salvar_google_sheets(df_final):
                    st.success("✅ Dados salvos com sucesso no Google Sheets!")
    else:
        st.error("❌ Não foi possível processar os dados. Verifique os arquivos PDF.")

st.markdown("---")

# Mostrar dados existentes
if st.checkbox("📖 Ver dados existentes no Google Sheets"):
    with st.spinner("Carregando dados..."):
        client = get_google_client()
        if client:
            try:
                sheet = client.open_by_url(SPREADSHEET_URL).worksheet(ABA)
                dados = pd.DataFrame(sheet.get_all_records())
                
                if not dados.empty:
                    st.subheader("Dados Armazenados")
                    
                    # Filtros
                    col_filtro1, col_filtro2 = st.columns(2)
                    with col_filtro1:
                        anos = sorted(dados["Ano"].unique())
                        filtro_ano = st.selectbox("Filtrar por Ano", ["Todos"] + list(anos))
                    
                    with col_filtro2:
                        meses = sorted(dados["Mês"].unique())
                        filtro_mes = st.selectbox("Filtrar por Mês", ["Todos"] + list(meses))
                    
                    # Aplicar filtros
                    if filtro_ano != "Todos":
                        dados = dados[dados["Ano"] == filtro_ano]
                    if filtro_mes != "Todos":
                        dados = dados[dados["Mês"] == filtro_mes]
                    
                    st.dataframe(dados, use_container_width=True)
                    
                    # Estatísticas
                    if not dados.empty:
                        st.metric("Total de Registros", len(dados))
                        st.metric("Valor Total", f"R$ {dados['Total Geral (R$)'].sum():,.2f}")
                else:
                    st.info("ℹ️ Nenhum dado encontrado no Google Sheets.")
                    
            except Exception as e:
                st.error(f"Erro ao carregar dados: {str(e)}")
        else:
            st.error("Não foi possível conectar ao Google Sheets.")

# Footer
st.markdown("---")
st.caption("Sistema de Comissão de Vendas - Desenvolvido com Streamlit")
