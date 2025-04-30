from flask import Flask, render_template, request, make_response, send_file
from reportlab.lib.pagesizes import landscape, A4
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
    c = canvas.Canvas(buffer, pagesize=landscape(A4))
    width, height = landscape(A4)

    azul = HexColor("#003366")

    # Fundo branco
    c.setFillColorRGB(1, 1, 1)
    c.rect(0, 0, width, height, fill=1, stroke=0)

    # Moldura arredondada
    margin = 40
    c.setLineWidth(4)
    c.setStrokeColor(azul)
    c.roundRect(margin, margin, width - 2 * margin, height - 2 * margin, radius=20, fill=0, stroke=1)

    # Logo
    try:
        logo_obj = s3.get_object(Bucket=app.config['S3_BUCKET'], Key='logo/logo.png')
        logo_img = ImageReader(BytesIO(logo_obj['Body'].read()))
        c.drawImage(logo_img, width / 2 - 50, height - margin - 100,
                    width=100, height=100, preserveAspectRatio=True, mask='auto')
    except Exception as e:
        print(f"Erro ao carregar logo: {str(e)}")

    # Título com linhas mais próximas e mais grossas
    c.setStrokeColor(azul)
    c.setLineWidth(2)
    c.line(100, height - 145, width - 100, height - 145)
    c.setFont("Helvetica-Bold", 28)
    c.setFillColor(azul)
    c.drawCentredString(width / 2, height - 165, "Certificado de Conclusão")
    c.line(100, height - 175, width - 100, height - 175)

    # Nome
    c.setFont("Helvetica", 20)
    c.drawCentredString(width / 2, height - 230, name)

    # Conteúdo
    c.setFont("Helvetica", 16)
    c.drawCentredString(width / 2, height - 270,
                        f"Pontuação: {score} pontos ({score/(len(questions)*10)*100:.0f}% de acertos)")
    c.drawCentredString(width / 2, height - 295,
                        "Concluiu com sucesso o treinamento em Boas Práticas de")
    c.drawCentredString(width / 2, height - 315, "Cibersegurança para Home Office")

    # Data
    c.setFont("Helvetica-Oblique", 12)
    c.drawCentredString(width / 2, height - 350, datetime.now().strftime("%d/%m/%Y"))

    # Assinatura grande e linha mais acima
    try:
        assinatura_path = os.path.join('static', 'assinatura.png')
        with open(assinatura_path, 'rb') as img_file:
            assinatura_img = ImageReader(img_file)
            assinatura_width = 400  # dobro do tamanho anterior
            assinatura_height = 160
            x = width / 2 - assinatura_width / 2
            y = height - 430
            c.drawImage(assinatura_img, x, y, width=assinatura_width, height=assinatura_height,
                        preserveAspectRatio=True, mask='auto')
            c.setStrokeColor(azul)
            c.setLineWidth(1)
            c.line(width / 2 - 60, y - 15, width / 2 + 60, y - 15)
    except Exception as e:
        print(f"Erro ao carregar assinatura: {str(e)}")

    # QR Code centralizado novamente
    qr_data = f"https://quiz.gepart.click/validar?nome={name}&score={score}"
    qr = qrcode.make(qr_data)
    qr_io = BytesIO()
    qr.save(qr_io, format='PNG')
    qr_io.seek(0)
    qr_img = ImageReader(qr_io)
    qr_size = 80
    qr_x = width / 2 - qr_size / 2
    qr_y = 90
    c.drawImage(qr_img, qr_x, qr_y, width=qr_size, height=qr_size, preserveAspectRatio=True, mask='auto')
    c.setFont("Helvetica", 8)
    c.drawCentredString(width / 2, 60, "Verifique a autenticidade em quiz.gepart.click")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer
