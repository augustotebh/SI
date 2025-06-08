from flask import Flask, render_template, request, make_response, send_file, url_for
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

s3 = boto3.client('s3')

with open('questions.json', 'r', encoding='utf-8') as f:
    questions = json.load(f)

for idx, q in enumerate(questions):
    q['id'] = f"q{idx+1}"

def set_security_headers(response):
    response.headers['Strict-Transport-Security'] = 'max-age=63072000; includeSubDomains; preload'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=()'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self'; "
        "img-src 'self'; "
        "font-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'; "
        "connect-src 'self'; "
        "media-src 'none'; "
        "manifest-src 'self'; "
        "worker-src 'none'; "
        "frame-src 'none';"
    )
    return response

@app.route('/', methods=['GET'])
def index():
    response = make_response(render_template('index.html', questions=questions))
    response.headers['Content-Type'] = 'text/html; charset=utf-8'
    return set_security_headers(response)

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
            html_content = f"""
            <html>
            <head><meta charset='utf-8'><title>Resultado</title></head>
            <body style="font-family:Arial;text-align:center;margin-top:50px;">
                <h2>Infelizmente você não atingiu 70% da nota para receber o certificado.</h2>
                <p>Nome: <strong>{nome}</strong></p>
                <p>Nota: <strong>{score} pontos</strong> ({percentual:.0f}%)</p>
                <a href="/">Tentar novamente</a>
            </body>
            </html>
            """
            response = make_response(html_content, 403)
            return set_security_headers(response)

        pdf_buffer = generate_certificate(nome, score)

        nome_sanitizado = re.sub(r'[^a-zA-Z0-9_-]', '_', nome)
        file_name = f"certificados/{nome_sanitizado}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
        s3.put_object(
            Bucket=app.config['S3_BUCKET'],
            Key=file_name,
            Body=pdf_buffer.getvalue(),
            ContentType='application/pdf'
        )

        response = send_file(
            pdf_buffer,
            mimetype='application/pdf',
            download_name=f"Certificado_{nome}.pdf"
        )
        return set_security_headers(response)

    except Exception as e:
        response = make_response(f"Erro: {str(e)}", 500)
        return set_security_headers(response)

def generate_certificate(name, score):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=landscape(A4))
    width, height = landscape(A4)
    azul = HexColor("#003366")

    try:
        fundo_img = ImageReader('static/certificado_base.png')
        c.drawImage(fundo_img, 0, 0, width=width, height=height)
    except Exception as e:
        print(f"Erro ao carregar imagem de fundo: {e}")

    c.setFillColor(azul)
    c.setFont("Helvetica-Bold", 26)
    c.drawCentredString(width / 2, height - 210, name)

    c.setFont("Helvetica", 20)
    c.drawCentredString(width / 2, height - 270,
                        f"Pontuação: {score} pontos ({score / (len(questions) * 10) * 100:.0f}% de acertos)")
    c.drawCentredString(width / 2, height - 295,
                        "Concluiu com sucesso o treinamento de Boas Práticas de Cibersegurança")
    c.drawCentredString(width / 2, height - 315, "para Home Office.")

    c.setFillColor(HexColor("#336699"))
    c.setFont("Helvetica", 12)
    c.drawString(650, height - 455, datetime.now().strftime("%d/%m/%Y"))

    try:
        assinatura_path = os.path.join('static', 'assinatura.png')
        assinatura_img = ImageReader(assinatura_path)
        c.drawImage(assinatura_img, width / 2 - 80, 95, width=160, height=60,
                    preserveAspectRatio=True, mask='auto')
    except Exception as e:
        print(f"Erro ao carregar assinatura: {str(e)}")

    try:
        qr_data = f"https://quiz.gepart.click/validar?nome={name}&score={score}"
        qr = qrcode.make(qr_data)
        qr_io = BytesIO()
        qr.save(qr_io, format='PNG')
        qr_io.seek(0)
        qr_img = ImageReader(qr_io)

        c.drawImage(qr_img, 20, 17, width=110, height=110,
                    preserveAspectRatio=True, mask='auto')
        c.setFillColor(azul)
        c.setFont("Helvetica", 8)
        c.drawString(20, 5, "Verifique: quiz.gepart.click")
    except Exception as e:
        print(f"Erro ao gerar QR Code: {str(e)}")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
