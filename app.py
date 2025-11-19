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
# Ruta de inicio
# =========================
@app.route("/", methods=["GET"])
def start():
    # Cada vez que entras al inicio, reseteamos el estado del examen
    session.clear()
    questions = load_questions()
    total = len(questions)
    return render_template("start.html", total=total)


# =========================
# Ruta del quiz (1 pregunta por página)
# =========================
@app.route("/quiz/<int:index>", methods=["GET", "POST"])
def quiz(index):
    questions = load_questions()
    total = len(questions)

    # Si el índice está fuera de rango, redirigimos
    if index < 1:
        return redirect(url_for("quiz", index=1))
    if index > total:
        return redirect(url_for("results"))

    # Inicializar estado en sesión si no existe
    if "answers" not in session:
        session["answers"] = {
            str(q["id"]): {"selected": None, "is_correct": None} for q in questions
        }
        session["score"] = 0

    current_q = questions[index - 1]
    qid = str(current_q["id"])

    feedback = None
    is_correct = None

    if request.method == "POST":
        action = request.form.get("action")
        answer_str = request.form.get("answer")

        # Aunque el HTML ya obliga a seleccionar, reforzamos en servidor
        if answer_str is not None:
            selected = int(answer_str)
            correct_answer = current_q["answer"]

            prev_state = session["answers"][qid]["is_correct"]
            now_correct = (selected == correct_answer)

            score = session.get("score", 0)

            # Ajustar score si cambiaste de correcta->incorrecta o viceversa
            if prev_state is True and not now_correct:
                score -= 1
            elif prev_state is not True and now_correct:
                score += 1

            session["score"] = score
            session["answers"][qid]["selected"] = selected
            session["answers"][qid]["is_correct"] = now_correct

            explanation = current_q.get("explanation", "")
            if now_correct:
                feedback = "Correct. " + explanation
            else:
                feedback = "Incorrect. " + explanation

            is_correct = now_correct
        else:
            feedback = "Please select an answer."
            is_correct = None

        # Nota sobre 10
        score = session.get("score", 0)
        score_10 = (score / total) * 10 if total > 0 else 0
        percentage_10 = score_10  # la variable se llama percentage en el template

        # Acción según botón
        if action == "check":
            return render_template(
                "quiz.html",
                question=current_q,
                index=index,
                total=total,
                progress=(index / total) * 100,
                selected=session["answers"][qid]["selected"],
                correct_count=score,
                percentage=percentage_10,
                feedback=feedback,
                is_correct=is_correct,
                is_last=(index == total),
            )

        elif action == "next":
            # Si era la última, ir a resultados
            if index >= total:
                return redirect(url_for("results"))
            return redirect(url_for("quiz", index=index + 1))

        elif action == "finish":
            return redirect(url_for("results"))

    # GET normal (sin POST) → mostrar pregunta con selección previa (si existe)
    selected = session["answers"][qid]["selected"]
    score = session.get("score", 0)
    score_10 = (score / total) * 10 if total > 0 else 0
    percentage_10 = score_10

    return render_template(
        "quiz.html",
        question=current_q,
        index=index,
        total=total,
        progress=(index / total) * 100,
        selected=selected,
        correct_count=score,
        percentage=percentage_10,
        feedback=None,
        is_correct=None,
        is_last=(index == total),
    )


# =========================
# Ruta de resultados finales
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
                "correct_index": q["answer"],
                "selected_index": ans.get("selected"),
                "is_correct": ans.get("is_correct"),
                "explanation": q.get("explanation", ""),
            }
        )

    return render_template(
        "results.html",
        questions=detailed,
        score=score,
        total=total,
        score_10=score_10,
        percentage=percentage,
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
