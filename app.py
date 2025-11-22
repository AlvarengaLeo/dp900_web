from flask import Flask, render_template, request, redirect, url_for, session
import json
import os
import random

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
    Verifica si la respuesta seleccionada es correcta.
    Soporta enteros (single choice) y listas (multi choice).
    """
    if isinstance(correct, list):
        # Multi-choice: comparar conjuntos o listas ordenadas
        if not isinstance(selected, list):
            return False
        return sorted(selected) == sorted(correct)
    else:
        # Single-choice
        return selected == correct


def get_shuffled_question(q, permutation):
    """
    Retorna una copia de la pregunta con las opciones reordenadas según 'permutation'.
    Ajusta 'answer' o 'answers' para que apunten a los nuevos índices.
    """
    new_q = q.copy()
    options = q["options"]
    
    # Reordenar opciones
    new_q["options"] = [options[i] for i in permutation]
    
    # Crear mapa de viejo índice -> nuevo índice
    # permutation[new_index] = old_index
    # Queremos: old_index -> new_index
    old_to_new = {old_idx: new_idx for new_idx, old_idx in enumerate(permutation)}
    
    # Ajustar respuesta correcta
    if "answers" in q and q["answers"] is not None:
        new_q["answers"] = [old_to_new[ans] for ans in q["answers"]]
    elif "answer" in q and q["answer"] is not None:
        new_q["answer"] = old_to_new[q["answer"]]
        
    return new_q


def is_hotspot_question(q):
    """
    Verifica si la pregunta es de tipo HOTSPOT Yes/No.
    """
    return q.get("type") == "hotspot_yes_no"


def evaluate_hotspot(user_answers, statements):
    """
    Evalúa las respuestas de una pregunta HOTSPOT.
    
    Args:
        user_answers: dict {statement_index: "yes"/"no"}
        statements: list de statements con campo "answer" (True/False)
    
    Returns:
        dict con:
            - "details": lista de {index, user_answer, correct_answer, is_correct}
            - "all_correct": bool indicando si todos fueron correctos
            - "score": número de statements correctos
    """
    details = []
    correct_count = 0
    
    for idx, stmt in enumerate(statements):
        user_ans = user_answers.get(str(idx))  # "yes" o "no"
        correct_ans = stmt.get("answer")  # True o False
        
        # Convertir user_ans a booleano
        user_bool = None
        if user_ans == "yes":
            user_bool = True
        elif user_ans == "no":
            user_bool = False
        
        is_correct = (user_bool == correct_ans) if user_bool is not None else False
        
        if is_correct:
            correct_count += 1
        
        details.append({
            "index": idx,
            "text": stmt.get("text"),
            "user_answer": user_ans,
            "correct_answer": correct_ans,
            "is_correct": is_correct
        })
    
    return {
        "details": details,
        "all_correct": correct_count == len(statements),
        "score": correct_count
    }


def get_shuffled_hotspot(q, permutation):
    """
    Retorna una copia de la pregunta HOTSPOT con statements reordenados.
    """
    new_q = q.copy()
    statements = q["statements"]
    
    # Reordenar statements
    new_q["statements"] = [statements[i] for i in permutation]
    
    return new_q

# =========================
# Ruta de inicio
# =========================
@app.route("/", methods=["GET", "POST"])
def start():
    session.clear()
    all_questions = load_questions()
    
    # Obtener categorías únicas
    categories = sorted(list(set(q.get("category", "General") for q in all_questions)))

    if request.method == "POST":
        selected_category = request.form.get("category")
        if selected_category:
            session["selected_category"] = selected_category
            
            # Filtrar y aleatorizar
            if selected_category == "Todas":
                filtered = all_questions
            else:
                filtered = [q for q in all_questions if q.get("category") == selected_category]
            
            q_ids = [q["id"] for q in filtered]
            random.shuffle(q_ids)
            session["quiz_question_ids"] = q_ids
            
            # Generar permutaciones para opciones y statements
            # Diccionario: str(question_id) -> lista de índices permutados
            perms = {}
            for q in filtered:
                if is_hotspot_question(q):
                    # Para HOTSPOT, permutar statements
                    n_stmts = len(q.get("statements", []))
                    perms[str(q["id"])] = random.sample(range(n_stmts), n_stmts)
                else:
                    # Para preguntas normales, permutar options
                    n_opts = len(q.get("options", []))
                    perms[str(q["id"])] = random.sample(range(n_opts), n_opts)
            session["option_permutations"] = perms
            
            return redirect(url_for("quiz", index=1))
    
    return render_template("start.html", categories=categories)


# =========================
# Ruta del quiz
# =========================
@app.route("/quiz/<int:index>", methods=["GET", "POST"])
def quiz(index):
    all_questions = load_questions()
    
    # Usar el orden aleatorio guardado en sesión
    quiz_ids = session.get("quiz_question_ids")
    
    if quiz_ids:
        q_map = {q["id"]: q for q in all_questions}
        questions = [q_map[qid] for qid in quiz_ids if qid in q_map]
    else:
        # Fallback: Filtrar por categoría seleccionada si no hay IDs (no debería pasar en flujo normal)
        selected_category = session.get("selected_category")
        if selected_category and selected_category != "Todas":
            questions = [q for q in all_questions if q.get("category") == selected_category]
        else:
            questions = all_questions

    # Fallback si no hay preguntas (no debería pasar si el filtro es correcto)
    if not questions:
        questions = all_questions

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

    current_q_raw = questions[index - 1]
    qid = str(current_q_raw["id"])
    
    # Detectar si es HOTSPOT
    is_hotspot = is_hotspot_question(current_q_raw)
    
    # Aplicar permutación de opciones/statements si existe
    perms = session.get("option_permutations", {})
    if qid in perms:
        if is_hotspot:
            current_q = get_shuffled_hotspot(current_q_raw, perms[qid])
        else:
            current_q = get_shuffled_question(current_q_raw, perms[qid])
    else:
        current_q = current_q_raw

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

        # HOTSPOT QUESTION
        if is_hotspot:
            # Recopilar respuestas: stmt_0=yes, stmt_1=no, etc.
            statements = current_q.get("statements", [])
            user_answers = {}
            for idx in range(len(statements)):
                ans = request.form.get(f"stmt_{idx}")
                if ans:
                    user_answers[str(idx)] = ans
            
            # Evaluar HOTSPOT
            hotspot_result = evaluate_hotspot(user_answers, statements)
            
            # Verificar si ya existe respuesta previa
            prev_state = session["answers"].get(qid, {}).get("is_correct")
            now_correct = hotspot_result["all_correct"]
            
            score = session.get("score", 0)
            
            # Ajuste inteligente del puntaje
            if prev_state is True and not now_correct:
                score -= 1
            elif prev_state is not True and now_correct:
                score += 1
            
            session["score"] = score
            
            # Guardar resultado HOTSPOT
            if qid not in session["answers"]:
                session["answers"][qid] = {}
            
            session["answers"][qid]["type"] = "hotspot"
            session["answers"][qid]["details"] = hotspot_result["details"]
            session["answers"][qid]["is_correct"] = now_correct
            
            explanation = current_q.get("explanation", "")
            if now_correct:
                feedback = "Correct. " + explanation
            else:
                feedback = "Incorrect. " + explanation
            
            is_correct = now_correct
        
        # PREGUNTA REGULAR (MULTI O SINGLE)
        else:
            # Determinar si es multi-respuesta
            is_multi = current_q.get("is_multi", False)
            
            # Obtener la respuesta correcta
            if is_multi:
                correct_answer = current_q.get("answers", [])
            else:
                correct_answer = current_q.get("answer")
            
            # MULTI-RESPUESTA → recibir lista
            if is_multi:
                selected_raw = request.form.getlist("answer")
                selected = [int(x) for x in selected_raw] if selected_raw else []
                if not selected:
                    selected = None
            else:
                selected_raw = request.form.get("answer")
                selected = int(selected_raw) if selected_raw is not None else None

            if selected is None:
                feedback = "Please select an answer."
                is_correct = None
            elif correct_answer is None:
                feedback = "⚠️ Error de configuración: Esta pregunta no tiene una respuesta correcta definida."
                is_correct = False
            else:
                # Verificar si ya existe respuesta previa
                prev_state = session["answers"].get(qid, {}).get("is_correct")
                now_correct = is_answer_correct(selected, correct_answer)

                score = session.get("score", 0)

                # Ajuste inteligente del puntaje
                if prev_state is True and not now_correct:
                    score -= 1
                elif prev_state is not True and now_correct:
                    score += 1

                session["score"] = score

                # Asegurar que la estructura existe
                if qid not in session["answers"]:
                     session["answers"][qid] = {}

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
            # Preparar datos para HOTSPOT o regular
            hotspot_details = None
            selected_val = None
            
            if is_hotspot:
                hotspot_details = session["answers"][qid].get("details", [])
            else:
                selected_val = session["answers"][qid].get("selected")
            
            return render_template(
                "quiz.html",
                question=current_q,
                index=index,
                total=total,
                progress=(index / total) * 100,
                selected=selected_val,
                correct_count=score,
                percentage=score_10,
                feedback=feedback,
                is_correct=is_correct,
                is_last=(index == total),
                is_multi=is_multi if not is_hotspot else False,
                is_hotspot=is_hotspot,
                hotspot_details=hotspot_details,
            )

        elif action == "next":
            if index >= total:
                return redirect(url_for("results"))
            return redirect(url_for("quiz", index=index + 1))

        elif action == "finish":
            return redirect(url_for("results"))

    # GET normal
    # Manejo seguro de claves en session["answers"]
    ans_data = session["answers"].get(qid, {"selected": None, "is_correct": None})
    selected = ans_data.get("selected") if not is_hotspot else None
    hotspot_details = ans_data.get("details") if is_hotspot else None
    
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
        is_last=(index == total),
        is_multi=is_multi if not is_hotspot else False,
        is_hotspot=is_hotspot,
        hotspot_details=hotspot_details,
    )


# =========================
@app.route("/results")
def results():
    all_questions = load_questions()
    
    # Usar el orden aleatorio guardado en sesión
    quiz_ids = session.get("quiz_question_ids")
    
    if quiz_ids:
        q_map = {q["id"]: q for q in all_questions}
        questions = [q_map[qid] for qid in quiz_ids if qid in q_map]
    else:
        # Fallback
        selected_category = session.get("selected_category")
        if selected_category and selected_category != "Todas":
            questions = [q for q in all_questions if q.get("category") == selected_category]
        else:
            questions = all_questions

    # Fallback
    if not questions:
        questions = all_questions

    total = len(questions)

    answers = session.get("answers", {})
    score = session.get("score", 0)

    score_10 = (score / total) * 10 if total > 0 else 0
    percentage = (score / total) * 100 if total > 0 else 0

    detailed = []
    
    perms = session.get("option_permutations", {})

    for q_raw in questions:
        qid = str(q_raw["id"])
        
        # Check if this is a HOTSPOT question
        is_hotspot = is_hotspot_question(q_raw)
        
        # Aplicar permutación para mostrar resultados consistentes con lo que vio el usuario
        if is_hotspot:
            # For HOTSPOT, apply statement shuffling
            if qid in perms:
                q = get_shuffled_hotspot(q_raw, perms[qid])
            else:
                q = q_raw
        else:
            # For regular questions, apply option shuffling
            if qid in perms:
                q = get_shuffled_question(q_raw, perms[qid])
            else:
                q = q_raw
            
        ans = answers.get(qid, {"selected": None, "is_correct": None})

        # Build the detailed entry
        entry = {
            "id": q["id"],
            "text": q["text"],
            "is_correct": ans.get("is_correct"),
            "explanation": q.get("explanation", ""),
            "is_hotspot": is_hotspot,
        }
        
        if is_hotspot:
            # For HOTSPOT questions, include statement details
            entry["statements"] = q.get("statements", [])
            entry["hotspot_details"] = ans.get("details", [])
        else:
            # For regular questions, include options and answers
            entry["options"] = q["options"]
            entry["correct_answer"] = q.get("answer", q.get("answers"))
            entry["selected"] = ans.get("selected")
        
        detailed.append(entry)

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
