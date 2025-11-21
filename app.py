from flask import Flask, render_template, request, redirect, url_for, session
import json
import os

app = Flask(__name__)
app.secret_key = "change-this-secret-key"  # cámbialo si quieres


# =========================
# Cargar preguntas desde JSON
# =========================
def load_questions():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(base_dir, "questions.json")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["questions"]


# =========================
# Función para evaluar respuestas múltiples
# =========================
def is_answer_correct(selected, correct):
    """
    selected = lista de índices seleccionados por el usuario
    correct  = int o lista de ints
    """
    if selected is None:
        return False

    # Convertir correct a lista si viene como entero
    if isinstance(correct, int):
        correct = [correct]

    # Convertir selected a lista (viene como ints)
    if isinstance(selected, int):
        selected = [selected]

    # Ordenar para evitar falsos negativos
    return sorted(selected) == sorted(correct)


# =========================
# Ruta de inicio
# =========================
@app.route("/", methods=["GET"])
def start():
    session.clear()
    questions = load_questions()
    total = len(questions)
    return render_template("start.html", total=total)


# =========================
# Ruta del quiz
# =========================
@app.route("/quiz/<int:index>", methods=["GET", "POST"])
def quiz(index):
    questions = load_questions()
    total = len(questions)

    if index < 1:
        return redirect(url_for("quiz", index=1))
    if index > total:
        return redirect(url_for("results"))

    # Inicializar estructura de respuestas
    if "answers" not in session:
        session["answers"] = {
            str(q["id"]): {"selected": None, "is_correct": None}
            for q in questions
        }
        session["score"] = 0

    current_q = questions[index - 1]
    qid = str(current_q["id"])

    # Determinar si es multi-respuesta basado en el flag explícito o inferencia
    is_multi = current_q.get("is_multi", False)
    
    # Obtener la respuesta correcta (lista o entero)
    if is_multi:
        correct_answer = current_q.get("answers", [])
    else:
        correct_answer = current_q.get("answer")

    feedback = None
    is_correct = None

    if request.method == "POST":
        action = request.form.get("action")

        # MULTI-RESPUESTA → recibir lista
        if is_multi:
            selected_raw = request.form.getlist("answer")
            selected = [int(x) for x in selected_raw] if selected_raw else []
            # En multi, si no selecciona nada, selected es []
            if not selected:
                selected = None
        else:
            selected_raw = request.form.get("answer")
            selected = int(selected_raw) if selected_raw is not None else None

        if selected is None:
            feedback = "Please select an answer."
            is_correct = None
        else:
            prev_state = session["answers"][qid]["is_correct"]
            now_correct = is_answer_correct(selected, correct_answer)

            score = session.get("score", 0)

            # Ajuste inteligente del puntaje
            # Si antes estaba bien y ahora mal, restamos
            if prev_state is True and not now_correct:
                score -= 1
            # Si antes no estaba bien (None o False) y ahora sí, sumamos
            elif prev_state is not True and now_correct:
                score += 1
            
            # Nota: Si estaba mal y sigue mal, o bien y sigue bien, no cambia.

            session["score"] = score

            session["answers"][qid]["selected"] = selected
            session["answers"][qid]["is_correct"] = now_correct

            explanation = current_q.get("explanation", "")
            if now_correct:
                feedback = "Correct. " + explanation
            else:
                feedback = "Incorrect. " + explanation

            is_correct = now_correct

        score = session.get("score", 0)
        score_10 = (score / total) * 10 if total > 0 else 0

        # Botones
        if action == "check":
            return render_template(
                "quiz.html",
                question=current_q,
                index=index,
                total=total,
                progress=(index / total) * 100,
                selected=session["answers"][qid]["selected"],
                correct_count=score,
                percentage=score_10,
                feedback=feedback,
                is_correct=is_correct,
                is_last=(index == total),
                is_multi=is_multi,
            )

        elif action == "next":
            if index >= total:
                return redirect(url_for("results"))
            return redirect(url_for("quiz", index=index + 1))

        elif action == "finish":
            return redirect(url_for("results"))

    # GET normal
    selected = session["answers"][qid]["selected"]
    score = session.get("score", 0)
    score_10 = (score / total) * 10 if total > 0 else 0

    return render_template(
        "quiz.html",
        question=current_q,
        index=index,
        total=total,
        progress=(index / total) * 100,
        selected=selected,
        correct_count=score,
        percentage=score_10,
        feedback=None,
        is_correct=None,
        is_last=(index == total),
        is_multi=is_multi,
    )


# =========================
# Resultados finales
# =========================
@app.route("/results")
def results():
    questions = load_questions()
    total = len(questions)

    answers = session.get("answers", {})
    score = session.get("score", 0)

    score_10 = (score / total) * 10 if total > 0 else 0
    percentage = (score / total) * 100 if total > 0 else 0

    detailed = []

    for q in questions:
        qid = str(q["id"])
        ans = answers.get(qid, {"selected": None, "is_correct": None})

        detailed.append(
            {
                "id": q["id"],
                "text": q["text"],
                "options": q["options"],
                "correct_answer": q.get("answer", q.get("answers")),
                "selected": ans.get("selected"),
                "is_correct": ans.get("is_correct"),
                "explanation": q.get("explanation", ""),
            }
        )

    return render_template(
        "results.html",
        questions=detailed,
        score=score,
        correct_count=score,
        total=total,
        score_10=score_10,
        percentage=percentage,
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
