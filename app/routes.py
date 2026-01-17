import base64
import os
import io, json
from flask import Blueprint, session, render_template, redirect, url_for, request, jsonify
from .models import db
from sqlalchemy import text
import pdfplumber
import joblib
# from openai import OpenAI
import requests, re
import nltk
from nltk.stem import WordNetLemmatizer
import pandas as pd
import numpy as np
nltk.download('wordnet', quiet=True)
nltk.download('omw-1.4', quiet=True)


main = Blueprint('main', __name__)

# === Load model saat Flask dijalankan ===
model_exp = joblib.load("app/model_exp.pkl")
le_exp = joblib.load("app/le_exp.pkl")
model_title = joblib.load("app/model_title.pkl")
le_title = joblib.load("app/le_title.pkl")

@main.route("/")
def home():
    web_title = "Halaman Utama"
    return redirect(url_for('main.main_form'))

@main.route("/login_form", methods = ['GET', 'POST'])
def login():
     return render_template("pages/login.html")

@main.route("/main_form", methods = ['GET', 'POST'])
def main_form():
     session.clear()
     return render_template("pages/main_form.html")

@main.route("/document_list", methods = ['GET', 'POST'])
def document_list_page():
     return render_template("pages/doc_list.html")
 
@main.route("/recommendation_list")
def recommendation_list():
    print("DEBUG session:", dict(session))
    recommendations = session.get("recommendations", [])
    return render_template("pages/recommendation.html", recommendations=recommendations)

@main.route("/api/save_recommendation", methods=["POST"])
def save_recommendation():
    data = request.get_json()
    print("DEBUG data:", dict(data))
    session["recommendations"] = data.get("recommendations", [])
    return jsonify({"status": "ok"})

@main.route("/api", methods = ['POST'])
def api():
     data = request.json
     email = data.get('email')
     password = data.get('password')

     try:
        # Context manager otomatis commit/rollback
        with db.engine.begin() as conn:
            stmt = text(
                "INSERT INTO app.users (email, password) "
                "VALUES (:email, :password) "
                "RETURNING user_id"
            )
            result = conn.execute(stmt, {"email": email, "password": password})
            new_id = result.fetchone()[0]

        return jsonify({"status": "success", "user_id": new_id})
     except Exception as e:
        # Rollback jika terjadi error
        return jsonify({'status': 'error', 'message': str(e)})
     
@main.route("/api/upload_pdf", methods = ['POST'])
def upload_pdf():
    file = request.files.get('file_pdf')
    if not file or not file.filename.endswith('.pdf'):
        return jsonify({"status": "error", "message": "File PDF tidak valid"}), 400
    # Ambil nama file & ekstensi
    filename = os.path.splitext(file.filename)[0]  # nama tanpa ekstensi
    extension = os.path.splitext(file.filename)[1].lstrip(".")  # hanya "pdf"
    # Convert file ke base64
    pdf_bytes = file.read()
    pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")
    try:
        with db.engine.begin() as conn:
            stmt = text("""
                INSERT INTO app.documents (file_name, file_base64, extension, uploaded_date, uploaded_by)
                VALUES (:file_name, :file_base64, :extension, NOW(), NULL)
                RETURNING doc_id
            """)
            result = conn.execute(stmt, {
                "file_name": filename,
                "file_base64": pdf_base64,
                "extension": extension
            })
            new_id = result.fetchone()[0]
        return jsonify({"status": "success", "doc_id": new_id, "file_base64" : pdf_base64})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})
    
@main.route("/api/documents", methods = ['GET'])
def get_documents():
    try:
        with db.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT *
                FROM app.documents
                ORDER BY file_name
            """))

            documents = [dict(row) for row in result.mappings()]

        return jsonify({
            "status": "success",
            "count": len(documents),
            "data": documents
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    
@main.route('/api/extract_pdf', methods=['POST'])
def extract_pdf():
    try:
        data = request.json.get("pdf_base64")
        if not data:
            return jsonify({"error": "No base64 data received"}), 400

        # Hapus prefix jika ada
        if "base64," in data:
            data = data.split("base64,")[1]

        # Decode base64 → bytes PDF
        pdf_bytes = base64.b64decode(data)

        # Ekstrak teks pakai pdfplumber
        text = ""
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                text += page.extract_text() or ""

        cleaned = clean_pdf_text_general(text)

        return jsonify({
            "status": "success",
            "extracted_text": cleaned.strip()
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    
@main.route("/api/extract_cv_info", methods=["POST"])
def extract_cv():
    data = request.get_json()
    text = data.get("extracted_text", "")

    if not text:
        return jsonify({"error": "Text kosong"}), 400

    prompt = f"""
    You are an information extraction assistant.

    Extract the following information from the provided text, and return **only valid JSON** (no explanations, no markdown, no extra words).

    Required keys:
    - YearsOfExperience: number of years if mentioned
    - Skills: include all skills, programming languages, tools, frameworks, and technologies.
    - Responsibilities: list of main work or job duties.
    - Keywords: important phrases or concepts related to expertise or domain.

    Now extract from this text:
    {text}
    """

    try:
        response = requests.post("http://localhost:11434/api/generate", json={
            "model": "llama3",
            "prompt": prompt, 
            "stream": False
        })
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Gagal terhubung ke Ollama: {str(e)}"}), 500

    if response.status_code != 200:
        return jsonify({"error": "Gagal dari Ollama"}), 500
    
    result_text = response.text.strip()
    result_json = try_fix_json(result_text)
    return jsonify({"result": result_json})

@main.route("/api/insert_cv_info", methods=["POST"])
def insert_cv_info():
    data = request.get_json()
    # print(data)
    years_exp = "1+" if data.get("yearsOfExperience") is None else data.get("yearsOfExperience")
    skills = ", ".join(data.get("skills", []))
    responsibilities = "\n".join(data.get("responsibilities", []))
    keywords = ", ".join(data.get("keywords", []))
    doc_id = data.get("doc_id")
    extracted_text = data.get("extracted_text")
    # print(years_exp)
    # print(skills)
    # print(responsibilities)
    # print(keywords)
    # print(doc_id)
    # print(extracted_text)
    recommendation_result = predict_job(skills, responsibilities, keywords, years_exp)
    experience_level = recommendation_result.get("Predicted_ExperienceLevel")
    print(recommendation_result)
    try:
        with db.engine.begin() as conn:
            stmt = text("""
                INSERT INTO app.document_values (doc_id, years_of_experience, skills, responsibilities, keywords, doc_content, recommendation_result, experience_level)
                VALUES (:doc_id, :years_exp, :skills, :responsibilities, :keywords, :extracted_text, :recommendation_result, :experience_level) RETURNING doc_val_id
            """)
            result = conn.execute(stmt, {
                "years_exp": years_exp,
                "skills": skills,
                "responsibilities": responsibilities,
                "keywords": keywords,
                "doc_id": doc_id,
                "extracted_text": extracted_text,
                "recommendation_result":recommendation_result,
                "experience_level":experience_level
            })
            new_id = result.fetchone()[0]
        return jsonify({"status": "success", "doc_val_id": new_id, "result":recommendation_result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

# ====== Fungsi utama ======
def predict_job(skills, responsibilities, keywords, years_exp):
    """
    Prediksi job title paling cocok dari input kandidat.
    """
    # === 1️⃣ Gabungkan teks & preprocessing ===
    text = " ".join([
        clean_text(skills),
        clean_text(responsibilities),
        clean_text(keywords)
    ])
    years_num = parse_years(years_exp)
    print(text)
    input_df = pd.DataFrame([{
        "text": text,
        "Years_num": years_num
    }])

    # === 2️⃣ Prediksi Experience Level ===
    exp_pred_label = le_exp.inverse_transform(model_exp.predict(input_df))[0]

    # Tambahkan ke data untuk model kedua
    input_df["Predicted_ExperienceLevel"] = exp_pred_label

    # === 3️⃣ Prediksi Job Title ===
    if hasattr(model_title.named_steps['clf'], "predict_proba"):
        # Jika model support probabilitas (misal XGBClassifier)
        proba = model_title.predict_proba(input_df)[0]
        sorted_idx = np.argsort(proba)[::-1]
        top_titles = [(le_title.inverse_transform([i])[0], float(proba[i])) for i in sorted_idx[:5]]
    else:
        # Jika pakai SVC (tanpa proba)
        pred_title = le_title.inverse_transform(model_title.predict(input_df))[0]
        top_titles = [(pred_title, 1.0)]

    # === 4️⃣ Return hasil ===
    return {
        "Predicted_ExperienceLevel": exp_pred_label,
        "Top_Job_Titles": [
            {"Title": title, "Confidence": round(score, 4)} for title, score in top_titles
        ]
    }

def clean_pdf_text_general(text):
    # Hilangkan spasi berlebihan
    text = re.sub(r"\s+", " ", text)
    
    # Hilangkan kata "page" atau "halaman" diikuti angka
    text = re.sub(r"(?i)\b(page|halaman)\s*\d+\b", "", text)
    
    # Pertahankan karakter penting dalam istilah teknologi (misal: C++, Node.js, AWS::EC2, email, URL, dsb.)
    allowed_chars_pattern = r"[^a-zA-Z0-9.,;:!?()\[\]\-_'\"/@&%#+=*<>{}|\\^~`\s]"
    text = re.sub(allowed_chars_pattern, " ", text)
    
    # Hilangkan spasi berlebih lagi setelah pembersihan
    text = re.sub(r"\s{2,}", " ", text)
    
    # Bersihkan spasi di awal/akhir
    return text.strip()

def try_fix_json(text):
    text = text.strip()

    # Hapus blok markdown dan penjelasan tambahan
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"^.*?\{", "{", text, flags=re.DOTALL)
    text = re.sub(r"Let me know.*", "", text, flags=re.DOTALL).strip()

    # Coba parsing langsung
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Kadang Llama pakai kutip tunggal atau ada koma nyasar
        fixed = (
            text.replace("'", '"')
            .replace("\n", "")
            .replace("\r", "")
            .strip()
        )

        # Hapus trailing koma sebelum penutup } atau ]
        fixed = re.sub(r",(\s*[}\]])", r"\1", fixed)

        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            return {"raw_text": text}

def parse_years(x):
    """Ubah YearsOfExperience ke bentuk numerik (float)"""
    if pd.isna(x):
        return np.nan
    x = str(x).strip().lower()
    if "less than" in x:
        return 0.5
    if re.match(r"(\d+)\+", x):
        return float(re.match(r"(\d+)\+", x).group(1)) + 1
    if re.match(r"(\d+)-(\d+)", x):
        a, b = map(float, re.match(r"(\d+)-(\d+)", x).groups())
        return (a + b) / 2
    nums = re.findall(r"\d+", x)
    if nums:
        return float(nums[0])
    return np.nan

def clean_text(text):
    lemmatizer = WordNetLemmatizer()
    """Bersihkan dan normalisasi teks job description tanpa merusak istilah teknis."""
    if not isinstance(text, str):
        return ''

    # Lowercase
    text = text.lower()

    # Ganti pemisah seperti ; atau , jadi spasi
    text = text.replace(';', ' ').replace(',', ' ')

    # Hapus tanda baca kecuali simbol penting teknologi
    text = re.sub(r"[^a-z0-9\.\+#_ ]", " ", text)

    # Hapus spasi berlebih
    text = re.sub(r'\s+', ' ', text).strip()

    # Lemmatize kata umum (tanpa mengubah istilah teknis seperti c#, sql, net)
    tokens = []
    for word in text.split():
        if not re.search(r"[#\.+_]", word):  # skip kata teknis
            word = lemmatizer.lemmatize(word)
        tokens.append(word)

    return ' '.join(tokens)

# @main.route("/api/extract_cv_info", methods=["POST"])
# def extract_cv_info():
#     api_key = os.getenv("OPENAI_API_KEY")
#     if not api_key:
#         return jsonify({"error": "OPENAI_API_KEY belum diset. Set environment variable terlebih dahulu."}), 500

#     data = request.get_json() or {}
#     text = data.get("extracted_text", "")
#     if not text:
#         return jsonify({"error": "Field 'text' required in JSON body"}), 400
#     client = OpenAI()  
    
#     try:
#         response = client.chat.completions.create(
#             model="gpt-3.5-turbo",
#             messages=[
#                 {"role": "system", "content": "You are an assistant that extracts structured CV fields."},
#                 {"role": "user", "content": (
#                     "Extract the following fields from the resume text and return a VALID JSON object:\n"
#                     "- YearsOfExperience\n- Skills (list)\n- Responsibilities (list)\n- Keywords (list)\n\n"
#                     f"Resume text:\n{text}"
#                 )}
#             ],
#             temperature=0.2,
#             max_tokens=800
#         )

#         # modern API: content path
#         # response.choices[0].message.content  (object)
#         raw = response.choices[0].message.content

#         # Try parse JSON; fallback return raw string
#         try:
#             parsed = json.loads(raw)
#             return jsonify(parsed)
#         except Exception:
#             return jsonify({"raw": raw}), 200

#     except Exception as e:
#         return jsonify({"error": str(e)}), 500