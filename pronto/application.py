from flask import Flask, render_template, request, make_response, send_file
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import HexColor
import boto3
from io import BytesIO
from datetime import datetime
import os
import json
import re
import qrcode
from PIL import Image

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['JSON_AS_ASCII'] = False
app.config['S3_BUCKET'] = 'elasticbeanstalk-us-east-1-619071334165'

# Cliente S3
s3 = boto3.client('s3')

# Carregar perguntas
with open('questions.json', 'r', encoding='utf-8') as f:
    questions = json.load(f)

# Adicionar IDs únicos para cada pergunta
for idx, q in enumerate(questions):
    q['id'] = f"q{idx+1}"

@app.route('/', methods=['GET'])
def index():
    response = make_response(render_template('index.html', questions=questions))
    response.headers['Content-Type'] = 'text/html; charset=utf-8'
    return response

@app.route('/submit', methods=['POST'])
def submit():
    try:
        score = 0
        user_answers = request.form.to_dict()
        nome = user_answers.pop('nome', 'Participante')

        for q in questions:
            if user_answers.get(q['id']) == q['resposta']:
                score += 10

        percentual = score / (len(questions) * 10) * 100

        if percentual < 70:
            return f"""
            <html>
            <head><meta charset='utf-8'><title>Resultado</title></head>
            <body style="font-family:Arial;text-align:center;margin-top:50px;">
                <h2>Infelizmente você não atingiu 70% da nota para receber o certificado.</h2>
                <p>Nome: <strong>{nome}</strong></p>
                <p>Nota: <strong>{score} pontos</strong> ({percentual:.0f}%)</p>
                <a href="/">Tentar novamente</a>
            </body>
            </html>
            """, 403

        pdf_buffer = generate_certificate(nome, score)

        nome_sanitizado = re.sub(r'[^a-zA-Z0-9_-]', '_', nome)
        file_name = f"certificados/{nome_sanitizado}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
        s3.put_object(
            Bucket=app.config['S3_BUCKET'],
            Key=file_name,
            Body=pdf_buffer.getvalue(),
            ContentType='application/pdf'
        )

        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            download_name=f"Certificado_{nome}.pdf"
        )

    except Exception as e:
        return f"Erro: {str(e)}", 500

def generate_certificate(name, score):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    azul = HexColor("#003366")
    azul_claro = HexColor("#E6F0FA")

    # Fundo azul claro
    c.setFillColor(azul_claro)
    c.rect(50, 100, width - 100, height - 200, fill=1, stroke=0)

    # Moldura
    margin = 40
    c.setLineWidth(4)
    c.setStrokeColor(azul)
    c.rect(margin, margin, width - 2 * margin, height - 2 * margin)

    # Cantoneiras
    c.setLineWidth(2)
    size = 20
    for x, y in [(margin, margin), (margin, height - margin),
                 (width - margin, margin), (width - margin, height - margin)]:
        c.line(x, y, x + (size if x == margin else -size), y)
        c.line(x, y, x, y + (size if y == margin else -size))

    # Logo
    try:
        logo_obj = s3.get_object(Bucket=app.config['S3_BUCKET'], Key='logo/logo.png')
        logo_img = ImageReader(BytesIO(logo_obj['Body'].read()))
        logo_width = 100
        logo_height = 100
        c.drawImage(logo_img, width / 2 - logo_width / 2, height - margin - logo_height,
                    width=logo_width, height=logo_height, preserveAspectRatio=True, mask='auto')
    except Exception as e:
        print(f"Erro ao carregar logo: {str(e)}")

    # Título
    c.setStrokeColor(azul)
    c.setLineWidth(1)
    c.line(100, height - 150, width - 100, height - 150)
    c.setFont("Helvetica-Bold", 24)
    c.setFillColor(azul)
    c.drawCentredString(width / 2, height - 170, "Certificado de Conclusão")
    c.line(100, height - 180, width - 100, height - 180)

    # Nome
    c.setFont("Helvetica", 18)
    c.drawCentredString(width / 2, height - 220, name)

    # Pontuação e conteúdo
    c.setFont("Helvetica", 14)
    c.drawCentredString(width / 2, height - 260,
                        f"Pontuação: {score} pontos ({score/(len(questions)*10)*100:.0f}% de acertos)")
    c.drawCentredString(width / 2, height - 285,
                        "Concluiu com sucesso o treinamento em Boas Práticas de")
    c.drawCentredString(width / 2, height - 305, "Cibersegurança para Home Office")

    # Data
    c.setFont("Helvetica-Oblique", 12)
    c.drawCentredString(width / 2, height - 340, datetime.now().strftime("%d/%m/%Y"))

    # Assinatura
    c.line(width / 2 - 60, height - 360, width / 2 + 60, height - 360)
    try:
        assinatura_obj = s3.get_object(Bucket=app.config['S3_BUCKET'], Key='logo/assinatura.png')
        assinatura_img = ImageReader(BytesIO(assinatura_obj['Body'].read()))
        c.drawImage(assinatura_img, width / 2 - 60, height - 370, width=120,
                    preserveAspectRatio=True, mask='auto')
    except Exception as e:
        print(f"Erro ao carregar assinatura: {str(e)}")

    c.drawCentredString(width / 2, height - 395, "Assinatura do Responsável")

    # QR Code - reposicionado um pouco acima
    qr_data = f"https://quiz.gepart.click/validar?nome={name}&score={score}"
    qr = qrcode.make(qr_data)
    qr_io = BytesIO()
    qr.save(qr_io, format='PNG')
    qr_io.seek(0)
    qr_img = ImageReader(qr_io)
    qr_size = 80
    c.drawImage(qr_img, width / 2 - qr_size / 2, 70, width=qr_size, height=qr_size, preserveAspectRatio=True, mask='auto')
    c.setFont("Helvetica", 8)
    c.drawCentredString(width / 2, 60, "Verifique a autenticidade em quiz.gepart.click")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
