def extract_pecas_pdf(file):
    """Extrai dados do PDF de peças - método mais robusto"""
    rows = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                lines = text.split('\n')
                for line in lines:
                    line = line.strip()
                    
                    # Padrão 1: Nome + R$ Valor Venda + % Rentab.
                    match = re.search(r"(.+?)\s+R\$\s*([\d\.\,]+)\s*\%\s*[\d\-\,\.]+", line)
                    if match:
                        nome = normalizar_nome(match.group(1).strip())
                        if nome and nome in VENDEDORES_VALIDOS:
                            valor_str = match.group(2).replace(".", "").replace(",", ".")
                            try:
                                valor = float(valor_str)
                                if valor > 0:
                                    rows.append({"Consultor": nome, "Peças (R$)": valor})
                                    continue  # Pula para próxima linha se encontrou
                            except:
                                pass
                    
                    # Padrão 2: Nome + R$ Valor Venda (sem porcentagem)
                    match = re.search(r"(.+?)\s+R\$\s*([\d\.\,]+)(?:\s*\%)?", line)
                    if match:
                        nome = normalizar_nome(match.group(1).strip())
                        if nome and nome in VENDEDORES_VALIDOS:
                            valor_str = match.group(2).replace(".", "").replace(",", ".")
                            try:
                                valor = float(valor_str)
                                if valor > 0:
                                    rows.append({"Consultor": nome, "Peças (R$)": valor})
                            except:
                                continue
    
    if rows:
        df = pd.DataFrame(rows)
        df = df.groupby("Consultor", as_index=False).sum(numeric_only=True)
        return df
    
    return pd.DataFrame(columns=["Consultor", "Peças (R$)"])
