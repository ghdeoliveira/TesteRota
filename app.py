from flask import Flask, render_template, jsonify, request
import requests
import re
import json
import logging
from datetime import datetime

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

class GoogleFormsBot:
    def __init__(self, email, driver_id, telefone, palavras_prioritarias, palavras_bloqueadas):
        # ENTRIES DO FORMULÁRIO (atualizado)
        self.ENTRY_EMAIL = 'entry.1468368768'      # E-mail
        self.ENTRY_DRIVER_ID = 'entry.1443850243'  # ID Driver
        self.ENTRY_TELEFONE = 'entry.1044818358'   # Telefone
        self.ENTRY_ROTA = 'entry.1969976134'       # Rota
        
        self.email = email
        self.driver_id = driver_id
        self.telefone = telefone
        self.palavras_prioritarias = palavras_prioritarias
        self.palavras_bloqueadas = palavras_bloqueadas
        
        # URL do formulário
        self.form_id = '1FAIpQLSfDXrWpIUS0J1JPjq672drZ4D1tL9CGxhL6SlmeZ4eZUwwDjA'
        self.view_url = f'https://docs.google.com/forms/d/e/{self.form_id}/viewform'
        self.submit_url = f'https://docs.google.com/forms/d/e/{self.form_id}/formResponse'
        
        self.session = requests.Session()
        self.logs = []
    
    def add_log(self, message, tipo='info'):
        log_entry = {
            'timestamp': datetime.now().strftime('%H:%M:%S'),
            'message': message,
            'type': tipo
        }
        self.logs.append(log_entry)
        print(f"[{tipo.upper()}] {message}")
    
    def buscar_rotas_disponiveis(self):
        """Busca as rotas disponíveis no formulário"""
        try:
            response = self.session.get(self.view_url, timeout=10)
            response.raise_for_status()
            html = response.text
            
            rotas = []
            
            # Busca via FB_PUBLIC_LOAD_DATA_
            fb_match = re.search(r'FB_PUBLIC_LOAD_DATA_\s*=\s*(\[.*?\]);', html, re.DOTALL)
            if fb_match:
                try:
                    data = json.loads(fb_match.group(1))
                    if data and len(data) > 1 and data[1]:
                        questions = data[1][1] if len(data[1]) > 1 else []
                        for question in questions:
                            if question and isinstance(question, list) and len(question) > 0:
                                # Procura a pergunta que contém "rota"
                                titulo = question[0] if question[0] else ""
                                if 'rota' in str(titulo).lower() or 'selecione' in str(titulo).lower():
                                    if len(question) > 4 and question[4]:
                                        for opt in question[4]:
                                            if opt and len(opt) > 0:
                                                rota = opt[0] if opt[0] else (opt[1] if len(opt) > 1 else None)
                                                if rota and rota != '.' and rota not in rotas and len(rota) > 2:
                                                    rotas.append(rota)
                except Exception as e:
                    pass
            
            # Fallback: busca por data-value
            if not rotas:
                radio_pattern = r'<div[^>]*data-value="([^"]*)"[^>]*role="radio"[^>]*>'
                matches = re.findall(radio_pattern, html)
                for value in matches:
                    if value and value != '.' and value not in rotas and len(value) > 2:
                        rotas.append(value)
            
            # Fallback 2: busca por spans com texto
            if not rotas:
                span_pattern = r'<span[^>]*class="[^"]*"[^>]*>([^<]*(?:Camboriú|BC|Itajaí|Brusque|CEDROS|CENTRO|NOVA)[^<]*)</span>'
                matches = re.findall(span_pattern, html, re.IGNORECASE)
                for match in matches:
                    match = match.strip()
                    if match and match not in rotas and len(match) > 2:
                        rotas.append(match)
            
            rotas = list(dict.fromkeys(rotas))
            return rotas
            
        except Exception as e:
            self.add_log(f"Erro ao buscar rotas: {e}", 'error')
            return []
    
    def selecionar_melhor_rota(self, rotas):
        """Seleciona a melhor rota baseada nas palavras"""
        if not rotas:
            return None
        
        self.add_log("🔍 Analisando rotas disponíveis...", 'info')
        
        # Mostra todas as rotas disponíveis
        self.add_log(f"📋 Rotas encontradas: {len(rotas)}", 'info')
        for rota in rotas:
            self.add_log(f"  - {rota}", 'info')
        
        # Filtra rotas bloqueadas
        rotas_liberadas = []
        for rota in rotas:
            bloqueada = False
            for palavra in self.palavras_bloqueadas:
                if palavra.lower() in rota.lower():
                    self.add_log(f"🚫 BLOQUEADA: {rota} (contém: {palavra})", 'warning')
                    bloqueada = True
                    break
            if not bloqueada:
                rotas_liberadas.append(rota)
                self.add_log(f"✅ LIBERADA: {rota}", 'success')
        
        if not rotas_liberadas:
            self.add_log("❌ Todas as rotas foram bloqueadas!", 'error')
            return None
        
        # Tenta encontrar rota com palavra prioritária (em ordem)
        for palavra in self.palavras_prioritarias:
            for rota in rotas_liberadas:
                if palavra.lower() in rota.lower():
                    self.add_log(f"🎯 ESCOLHIDA: {rota} (contém: {palavra})", 'success')
                    return rota
        
        # Fallback: primeira rota liberada
        rota = rotas_liberadas[0]
        self.add_log(f"⚠️ Nenhuma palavra prioritária encontrada. Usando primeira: {rota}", 'warning')
        return rota
    
    def pegar_fbzx(self):
        """Captura o token de segurança fbzx"""
        try:
            response = self.session.get(self.view_url, timeout=10)
            match = re.search(r'fbzx" value="([^"]+)"', response.text)
            return match.group(1) if match else None
        except Exception:
            return None
    
    def enviar_formulario(self, rota):
        """Envia o formulário com a rota escolhida"""
        payload = {
            self.ENTRY_EMAIL: self.email,
            self.ENTRY_DRIVER_ID: self.driver_id,
            self.ENTRY_TELEFONE: self.telefone,
            self.ENTRY_ROTA: rota,
            'fvv': '1',
            'pageHistory': '0'
        }
        
        fbzx = self.pegar_fbzx()
        if fbzx:
            payload['fbzx'] = fbzx
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        try:
            response = self.session.post(
                self.submit_url,
                data=payload,
                headers=headers,
                allow_redirects=False,
                timeout=30
            )
            
            if response.status_code in [200, 301, 302]:
                self.add_log(f"✅ FORMULÁRIO ENVIADO COM SUCESSO!", 'success')
                self.add_log(f"📍 Rota: {rota}", 'success')
                self.add_log(f"📧 Email: {self.email}", 'success')
                self.add_log(f"🆔 Driver ID: {self.driver_id}", 'success')
                self.add_log(f"📱 Telefone: {self.telefone}", 'success')
                return True
            else:
                self.add_log(f"❌ Falha no envio. Status: {response.status_code}", 'error')
                return False
        except Exception as e:
            self.add_log(f"❌ Erro: {e}", 'error')
            return False
    
    def executar(self):
        """Executa o bot completo"""
        self.logs = []
        self.add_log("🚀 Iniciando Bot de Formulário", 'info')
        self.add_log("━" * 40, 'info')
        self.add_log(f"📧 Email: {self.email}", 'info')
        self.add_log(f"🆔 Driver ID: {self.driver_id}", 'info')
        self.add_log(f"📱 Telefone: {self.telefone}", 'info')
        self.add_log("━" * 40, 'info')
        
        # Busca rotas disponíveis
        rotas = self.buscar_rotas_disponiveis()
        
        if not rotas:
            self.add_log("❌ Nenhuma rota disponível no momento!", 'error')
            return {'sucesso': False, 'logs': self.logs}
        
        # Seleciona a melhor rota
        rota_escolhida = self.selecionar_melhor_rota(rotas)
        
        if not rota_escolhida:
            self.add_log("❌ Nenhuma rota atende aos critérios!", 'error')
            return {'sucesso': False, 'logs': self.logs}
        
        # Envia o formulário
        self.add_log("━" * 40, 'info')
        self.add_log(f"📤 Enviando formulário...", 'info')
        
        if self.enviar_formulario(rota_escolhida):
            self.add_log("━" * 40, 'info')
            self.add_log(f"🎉 PROCESSO FINALIZADO COM SUCESSO!", 'success')
            return {'sucesso': True, 'rota': rota_escolhida, 'logs': self.logs}
        else:
            self.add_log("❌ PROCESSO FINALIZADO COM FALHA!", 'error')
            return {'sucesso': False, 'logs': self.logs}


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/enviar', methods=['POST'])
def enviar():
    data = request.json
    
    email = data.get('email', 'gho8885@gmail.com')
    driver_id = data.get('driverId', '163347')
    telefone = data.get('telefone', '47996327935')
    palavras_prioritarias = data.get('prioridades', ['NOVA ESPERANÇA', 'CEDROS', 'MONTE ALEGRE', 'NAÇÕES'])
    palavras_bloqueadas = data.get('bloqueadas', ['BRUSQUE', 'MOTO', 'FIORINO', 'CENTRO'])
    
    bot = GoogleFormsBot(
        email=email,
        driver_id=driver_id,
        telefone=telefone,
        palavras_prioritarias=palavras_prioritarias,
        palavras_bloqueadas=palavras_bloqueadas
    )
    
    resultado = bot.executar()
    return jsonify(resultado)


@app.route('/api/rotas', methods=['GET'])
def listar_rotas():
    """Endpoint para listar as rotas disponíveis sem enviar"""
    bot = GoogleFormsBot('', '', '', [], [])
    rotas = bot.buscar_rotas_disponiveis()
    return jsonify({'rotas': rotas})


if __name__ == '__main__':
    print("=" * 50)
    print("🚀 Brilhante Bot - Servidor Rodando!")
    print("📍 Acesse: http://localhost:5000")
    print("=" * 50)
    app.run(debug=True, host='0.0.0.0', port=5000)