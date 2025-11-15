from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from models import db, Usuario, Setor, Espaco, Agendamento
import services

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///sala_agenda.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = "segredo-top"


# --------------------------------
# Inicializa o banco e cria admin
# --------------------------------
db.init_app(app)

with app.app_context():
    db.create_all()

    # cria admin padrão se não existir
    if not Usuario.query.filter_by(email="admin@admin.com").first():
        admin = Usuario(
            nome="Administrador",
            email="admin@admin.com",
            senha_hash=generate_password_hash("admin"),
            papel="ADMIN"
        )
        db.session.add(admin)
        db.session.commit()


# --------------------------------
# Helper: usuário logado
# --------------------------------
def usuario_logado():
    if "usuario_id" in session:
        return Usuario.query.get(session["usuario_id"])
    return None


# --------------------------------
# Context processor: pendentes no topo
# --------------------------------
@app.context_processor
def inject_pendentes_count():
    user = usuario_logado()
    if not user or not user.pode_aprovar():
        return {"pendentes_count": None}
    count = Agendamento.query.filter_by(status="PENDENTE").count()
    return {"pendentes_count": count, "usuario": user}


# --------------------------------
# Rotas de autenticação
# --------------------------------
@app.route("/")
def index():
    user = usuario_logado()
    if not user:
        return redirect(url_for("login"))
    return redirect(url_for("dashboard"))


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":
        email = request.form["email"]
        senha = request.form["senha"]

        user = Usuario.query.filter_by(email=email).first()

        if user and check_password_hash(user.senha_hash, senha):
            session["usuario_id"] = user.id
            return redirect(url_for("dashboard"))

        return render_template("login.html", erro="Email ou senha incorretos.")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/api/verificar_conflitos")
def verificar_conflitos():
    espaco_id = request.args.get("espaco_id")
    inicio = request.args.get("inicio")
    fim = request.args.get("fim")

    if not espaco_id or not inicio or not fim:
        return jsonify({"erro": "Dados insuficientes"}), 400

    inicio = datetime.fromisoformat(inicio)
    fim = datetime.fromisoformat(fim)

    conflitos = (
        Agendamento.query
        .filter(Agendamento.espaco_id == espaco_id)
        .filter(Agendamento.status != "CANCELADO")
        .filter(Agendamento.fim > inicio)
        .filter(Agendamento.inicio < fim)
        .order_by(Agendamento.inicio)
        .all()
    )

    pendentes = []
    aprovados = []

    for ag in conflitos:
        dado = {
            "id": ag.id,
            "inicio": ag.inicio.strftime("%H:%M"),
            "fim": ag.fim.strftime("%H:%M"),
            "usuario": ag.usuario.nome,
            "status": ag.status,
            "setor": ag.espaco.setor.nome,
            "espaco": ag.espaco.nome
        }

        if ag.status == "PENDENTE":
            pendentes.append(dado)
        elif ag.status == "APROVADO":
            aprovados.append(dado)

    return jsonify({
        "pendentes": pendentes,
        "aprovados": aprovados
    })

# --------------------------------
# Agenda (FullCalendar)
# --------------------------------
@app.route("/agenda")
def agenda():
    user = usuario_logado()
    if not user:
        return redirect(url_for("login"))

    return render_template(
        "agenda.html",
        user=user,
        Setor=Setor,   # 🔥 agora o template enxerga Setor
        Espaco=Espaco  # (não obrigatório, mas útil)
    )


# API que devolve os agendamentos em JSON para o FullCalendar
@app.route("/api/agendamentos")
def api_agendamentos():
    status = request.args.getlist("status")
    setor_id = request.args.get("setor_id")
    espaco_id = request.args.get("espaco_id")

    query = Agendamento.query

    if status:
        query = query.filter(Agendamento.status.in_(status))

    if setor_id:
        query = query.join(Espaco).filter(Espaco.setor_id == setor_id)

    if espaco_id:
        query = query.filter(Agendamento.espaco_id == espaco_id)

    eventos = query.all()

    lista = []
    for e in eventos:

        motivo_curto = ""
        if e.motivo:
            motivo_curto = e.motivo[:25] + ("..." if len(e.motivo) > 25 else "")

        lista.append({
            "id": e.id,
            "title": f"{e.espaco.setor.acronimo} – {e.espaco.nome}\n{motivo_curto}",
            "start": e.inicio.isoformat(),
            "end": e.fim.isoformat(),
            "color": cor_status(e.status),

            # Enviamos para o tooltip (opcional, mas profissional)
            "setor": e.espaco.setor.nome,
            "acronimo": e.espaco.setor.acronimo,
            "espaco": e.espaco.nome,
            "motivo": e.motivo,
            "usuario": e.usuario.nome,
            "status": e.status
        })

    return jsonify(lista)


# Função auxiliar de cores
def cor_status(status):
    return {
        "APROVADO": "#28a745",   # verde
        "PENDENTE": "#ffc107",   # amarelo
        "RECUSADO": "#dc3545",   # vermelho
        "CANCELADO": "#6c757d",  # cinza
    }.get(status, "#0d6efd")     # padrão azul

@app.route("/api/agendamento/<int:id>")
def api_agendamento(id):
    ag = Agendamento.query.get(id)
    if not ag:
        return jsonify({"erro": "Agendamento não encontrado"}), 404

    return jsonify({
        "id": ag.id,
        "espaco": ag.espaco.nome,
        "setor": ag.espaco.setor.nome,
        "acronimo": ag.espaco.setor.acronimo,
        "status": ag.status,
        "motivo": ag.motivo,
        "motivo_recusa": ag.motivo_recusa,
        "usuario": ag.usuario.nome,
        "inicio": ag.inicio.strftime("%d/%m/%Y %H:%M"),
        "fim": ag.fim.strftime("%d/%m/%Y %H:%M"),
        "color": cor_status(ag.status)
    })

# --------------------------------
# Exportar Agenda do Dia (PDF)
# -------------------------------
@app.route("/exportar_pdf")
def exportar_pdf():
    user = usuario_logado()
    if not user:
        return redirect(url_for("login"))

    # ----- COLETAR OS FILTROS -----
    status_filtros = request.args.getlist("status")
    setor_id = request.args.get("setor_id")
    espaco_id = request.args.get("espaco_id")

    # ----- PERÍODO (apenas dia atual por enquanto) -----
    hoje = datetime.now().date()
    inicio = datetime(hoje.year, hoje.month, hoje.day)
    fim = datetime(hoje.year, hoje.month, hoje.day, 23, 59, 59)

    # ----- QUERY BASE -----
    q = (
        Agendamento.query
        .filter(
            Agendamento.inicio >= inicio,
            Agendamento.inicio <= fim,
            Agendamento.status != "CANCELADO",
        )
        .join(Espaco)
        .order_by(Espaco.setor_id, Agendamento.inicio)
    )

    # ----- APLICAR FILTROS -----
    if status_filtros:
        q = q.filter(Agendamento.status.in_(status_filtros))

    if setor_id:
        q = q.filter(Espaco.setor_id == setor_id)

    if espaco_id:
        q = q.filter(Agendamento.espaco_id == espaco_id)

    agendamentos = q.all()

    # AGRUPAR POR SETOR
    setores = {}
    for ag in agendamentos:
        nome_setor = ag.espaco.setor.nome
        setores.setdefault(nome_setor, []).append(ag)

    # ----- CRIAR PDF -----
    caminho_pdf = "agenda_filtrada.pdf"
    c = canvas.Canvas(caminho_pdf, pagesize=A4)
    largura, altura = A4

    # TÍTULO PRINCIPAL
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, altura - 40, "Agenda – Relatório Filtrado")

    y = altura - 80

    # ----- DESCREVER OS FILTROS USADOS -----
    c.setFont("Helvetica", 11)

    filtros_desc = [
        f"Período: {hoje.strftime('%d/%m/%Y')}",
        f"Status: {', '.join(status_filtros) if status_filtros else 'Todos'}",
        f"Setor: {Setor.query.get(setor_id).nome if setor_id else 'Todos'}",
        f"Espaço: {Espaco.query.get(espaco_id).nome if espaco_id else 'Todos'}",
    ]

    for linha in filtros_desc:
        c.drawString(40, y, linha)
        y -= 18

    y -= 15

    # ----- SEM RESULTADOS -----
    if not setores:
        c.setFont("Helvetica-Bold", 12)
        c.drawString(40, y, "Nenhum resultado para os filtros aplicados.")
        c.save()
        return send_file(caminho_pdf, as_attachment=True)

    # ----- TABELA POR SETOR -----
    for nome_setor, lista in setores.items():

        # Nome do setor
        c.setFont("Helvetica-Bold", 14)
        c.drawString(40, y, f"SETOR: {nome_setor}")
        y -= 28

        # Cabeçalho da tabela
        c.setFont("Helvetica-Bold", 11)
        c.drawString(40, y,  "HORÁRIO")
        c.drawString(120, y, "ESPAÇO")
        c.drawString(260, y, "USUÁRIO")
        c.drawString(380, y, "STATUS")
        c.drawString(450, y, "MOTIVO / RECUSA")
        y -= 10
        c.line(40, y, largura - 40, y)
        y -= 15

        c.setFont("Helvetica", 10)

        # LINHAS DA TABELA
        for ag in lista:

            # coluna 1 - horário
            c.drawString(40, y, f"{ag.inicio.strftime('%H:%M')}–{ag.fim.strftime('%H:%M')}")

            # coluna 2 - espaço
            c.drawString(120, y, ag.espaco.nome[:18])

            # coluna 3 - usuário
            c.drawString(260, y, ag.usuario.nome[:18])

            # coluna 4 - status
            c.drawString(380, y, ag.status)

            # coluna 5 - motivo + recusa (quebra automática)
            motivo_texto = f"{ag.motivo or ''}"
            if ag.motivo_recusa:
                motivo_texto += f"\nRecusa: {ag.motivo_recusa}"

            linhas = simpleSplit(motivo_texto, 'Helvetica', 10, 120)

            # desenhar as linhas do motivo
            yy = y
            for l in linhas:
                c.drawString(450, yy, l)
                yy -= 12

            y -= max(20, 12 * len(linhas))

            # quebra de página
            if y < 50:
                c.showPage()
                y = altura - 50
                c.setFont("Helvetica-Bold", 14)
                c.drawString(40, y, f"SETOR: {nome_setor} (continuação)")
                y -= 28

                c.setFont("Helvetica-Bold", 11)
                c.drawString(40, y,  "HORÁRIO")
                c.drawString(120, y, "ESPAÇO")
                c.drawString(260, y, "USUÁRIO")
                c.drawString(380, y, "STATUS")
                c.drawString(450, y, "MOTIVO / RECUSA")
                y -= 10
                c.line(40, y, largura - 40, y)
                y -= 15
                c.setFont("Helvetica", 10)

        y -= 30

    c.save()
    return send_file(caminho_pdf, as_attachment=True)


# --------------------------------
# Dashboard
# --------------------------------
@app.route("/dashboard")
def dashboard():
    user = usuario_logado()
    if not user:
        return redirect(url_for("login"))

    return render_template(
        "dashboard.html",
        usuario=user,
        Setor=Setor,       # 🔥 necessário para carregar setores
        Espaco=Espaco      # opcional, mas útil
    )

@app.route("/api/dashboard")
def api_dashboard():
    status = request.args.getlist("status")
    setor_id = request.args.get("setor_id")
    espaco_id = request.args.get("espaco_id")

    hoje = datetime.now().date()
    inicio = datetime(hoje.year, hoje.month, hoje.day)
    fim = datetime(hoje.year, hoje.month, hoje.day, 23, 59, 59)

    q = Agendamento.query.filter(
        Agendamento.inicio >= inicio,
        Agendamento.inicio <= fim,
        Agendamento.status != "CANCELADO"
    ).join(Espaco)

    if status:
        q = q.filter(Agendamento.status.in_(status))

    if setor_id:
        q = q.filter(Espaco.setor_id == setor_id)

    if espaco_id:
        q = q.filter(Agendamento.espaco_id == espaco_id)

    ags = q.order_by(Agendamento.inicio).all()

    lista = []
    for ag in ags:
        lista.append({
            "id": ag.id,
            "setor": ag.espaco.setor.nome,
            "espaco": ag.espaco.nome,
            "usuario": ag.usuario.nome,
            "inicio": ag.inicio.strftime("%H:%M"),
            "fim": ag.fim.strftime("%H:%M"),
            "status": ag.status,
            "motivo": ag.motivo,
            "motivo_recusa": ag.motivo_recusa
        })

    return jsonify(lista)


# --------------------------------
# Usuários (apenas ADMIN/AGENDADOR via pode_aprovar)
# --------------------------------
@app.route("/usuarios/novo", methods=["GET", "POST"])
def novo_usuario():
    user = usuario_logado()
    if not user or not user.pode_aprovar():
        return redirect(url_for("login"))

    if request.method == "POST":
        nome = request.form["nome"]
        email = request.form["email"]
        senha = request.form["senha"]
        papel = request.form["papel"]

        if Usuario.query.filter_by(email=email).first():
            return render_template("usuarios_form.html",
                                   erro="Email já cadastrado.",
                                   usuario=user)

        novo = Usuario(
            nome=nome,
            email=email,
            senha_hash=generate_password_hash(senha),
            papel=papel
        )
        db.session.add(novo)
        db.session.commit()

        return redirect(url_for("dashboard"))

    return render_template("usuarios_form.html", usuario=user)


# --------------------------------
# Setores (somente ADMIN/AGENDADOR)
# --------------------------------
@app.route("/setores")
def setores_list():
    user = usuario_logado()
    if not user or not user.pode_aprovar():
        return redirect(url_for("login"))

    setores = Setor.query.all()
    return render_template("setores_list.html", setores=setores, usuario=user)


@app.route("/setores/novo", methods=["GET", "POST"])
def setores_novo():
    user = usuario_logado()
    if not user or not user.pode_aprovar():
        return redirect(url_for("login"))

    if request.method == "POST":
        nome = request.form["nome"]
        setor = Setor(nome=nome)
        db.session.add(setor)
        db.session.commit()
        return redirect(url_for("setores_list"))

    return render_template("setores_form.html", usuario=user)


# --------------------------------
# Espaços (somente ADMIN/AGENDADOR)
# --------------------------------
@app.route("/espacos")
def espacos_list():
    user = usuario_logado()
    if not user or not user.pode_aprovar():
        return redirect(url_for("login"))

    espacos = Espaco.query.all()
    return render_template("espacos_list.html", espacos=espacos, usuario=user)


@app.route("/espacos/novo", methods=["GET", "POST"])
def espacos_novo():
    user = usuario_logado()
    if not user or not user.pode_aprovar():
        return redirect(url_for("login"))

    setores = Setor.query.all()

    if request.method == "POST":
        nome = request.form["nome"]
        setor_id = request.form["setor_id"]

        espaco = Espaco(
            nome=nome,
            setor_id=setor_id
        )
        db.session.add(espaco)
        db.session.commit()

        return redirect(url_for("espacos_list"))

    return render_template("espacos_form.html", usuario=user, setores=setores)


@app.route("/espacos/<int:id>/status", methods=["POST"])
def espaco_status(id):
    user = usuario_logado()
    if not user or not user.pode_aprovar():
        return redirect(url_for("login"))

    espaco = Espaco.query.get(id)
    if not espaco:
        return redirect(url_for("espacos_list"))

    espaco.status = "LIVRE" if espaco.status == "BLOQUEADO" else "BLOQUEADO"
    db.session.commit()

    return redirect(url_for("espacos_list"))


# --------------------------------
# API: espaços por setor (para formulário de agendamento)
# --------------------------------
@app.route("/api/espacos/<int:setor_id>")
def api_espacos_por_setor(setor_id):
    espacos = Espaco.query.filter_by(setor_id=setor_id).all()
    return jsonify([
        {
            "id": e.id,
            "nome": e.nome,
            "status": e.status
        }
        for e in espacos
    ])


# --------------------------------
# Agendamentos - novo
# --------------------------------
@app.route("/agendamentos/novo", methods=["GET", "POST"])
def novo_agendamento():
    user = usuario_logado()
    if not user:
        return redirect(url_for("login"))

    setores = Setor.query.all()

    if request.method == "POST":
        espaco = Espaco.query.get(request.form["espaco_id"])
        data = request.form["data"]
        inicio_str = request.form["inicio"]
        fim_str = request.form["fim"]
        motivo = request.form["motivo"]

        if not espaco or not data or not inicio_str or not fim_str:
            return render_template(
                "agendamentos_form.html",
                erro="Preencha todos os campos.",
                usuario=user,
                setores=setores
            )

        inicio = datetime.fromisoformat(f"{data}T{inicio_str}")
        fim = datetime.fromisoformat(f"{data}T{fim_str}")

        try:
            services.criar_agendamento(
                usuario=user,
                espaco=espaco,
                inicio=inicio,
                fim=fim,
                motivo=motivo
            )
            return redirect(url_for("dashboard"))
        except ValueError as e:
            return render_template(
                "agendamentos_form.html",
                erro=str(e),
                usuario=user,
                setores=setores
            )

    return render_template("agendamentos_form.html", usuario=user, setores=setores)


# --------------------------------
# Agendamentos pendentes (para ADMIN / AGENDADOR)
# --------------------------------
@app.route("/agendamentos/pendentes")
def agendamentos_pendentes():
    user = usuario_logado()
    if not user or not user.pode_aprovar():
        return redirect(url_for("dashboard"))

    pendentes = Agendamento.query.filter_by(status="PENDENTE").all()

    return render_template("agendamentos_pendentes.html",
                           pendentes=pendentes,
                           usuario=user)


# --------------------------------
# Aprovar agendamento
# --------------------------------
@app.route("/agendamentos/aceitar/<int:id>", methods=["POST"])
def aceitar_agendamento(id):
    ag = Agendamento.query.get(id)
    if not ag:
        return {"erro": "não encontrado"}, 404

    ag.status = "APROVADO"
    db.session.commit()
    return {"ok": True}


# --------------------------------
# Recusar agendamento (com justificativa)
# --------------------------------
@app.route("/agendamentos/recusar/<int:id>", methods=["POST"])
def recusar_agendamento(id):
    justificativa = request.json.get("justificativa")
    ag = Agendamento.query.get(id)
    if not ag:
        return {"erro": "não encontrado"}, 404

    ag.status = "RECUSADO"
    ag.motivo_recusa = justificativa
    db.session.commit()
    return {"ok": True}



# --------------------------------
# Aceitar com conflitos
# --------------------------------
@app.route("/api/conflitos_aceitar/<int:id>")
def conflitos_aceitar(id):
    ag = Agendamento.query.get(id)
    if not ag:
        return jsonify({"erro": "Agendamento não encontrado"}), 404

    inicio = ag.inicio
    fim = ag.fim
    espaco_id = ag.espaco_id

    conflitos = (
        Agendamento.query
        .filter(Agendamento.id != ag.id)
        .filter(Agendamento.espaco_id == espaco_id)
        .filter(Agendamento.status != "CANCELADO")
        .filter(Agendamento.fim > inicio)
        .filter(Agendamento.inicio < fim)
        .order_by(Agendamento.inicio)
        .all()
    )

    lista = []
    for c in conflitos:
        lista.append({
            "id": c.id,
            "status": c.status,
            "setor": c.espaco.setor.nome,
            "espaco": c.espaco.nome,
            "inicio": c.inicio.strftime("%H:%M"),
            "fim": c.fim.strftime("%H:%M"),
            "usuario": c.usuario.nome,
            "motivo": c.motivo
        })

    return jsonify(lista)

@app.route("/agendamentos/<int:id>/editar")
def agendamento_editar(id):
    user = usuario_logado()
    if not user or not user.pode_aprovar():
        return redirect("/agenda")
    ag = Agendamento.query.get_or_404(id)
    setores = Setor.query.all()
    espacos = Espaco.query.all()

    # envia JSON com os espaços
    espacos_json = [
        {"id": e.id, "nome": e.nome, "setor_id": e.setor_id}
        for e in espacos
    ]

    return render_template(
        "agendamento_editar.html",
        ag=ag,
        setores=setores,
        espacos_json=espacos_json
    )

@app.route("/agendamentos/<int:id>/editar", methods=["POST"])
def agendamento_salvar(id):
    user = usuario_logado()
    if not user or not user.pode_aprovar():
        return redirect("/agenda")
    ag = Agendamento.query.get_or_404(id)

    espaco_id = request.form["espaco_id"]
    data = request.form["data"]
    inicio = request.form["inicio"]
    fim = request.form["fim"]

    ag.espaco_id = espaco_id
    ag.inicio = datetime.strptime(f"{data} {inicio}", "%Y-%m-%d %H:%M")
    ag.fim = datetime.strptime(f"{data} {fim}", "%Y-%m-%d %H:%M")
    ag.motivo = request.form["motivo"]

    db.session.commit()
    return redirect("/agenda")

@app.route("/agendamentos/<int:id>/excluir")
def agendamento_excluir(id):
    user = usuario_logado()
    if not user or not user.pode_aprovar():
        return redirect("/agenda")  # bloqueia quem não pode excluir

    ag = Agendamento.query.get_or_404(id)
    db.session.delete(ag)
    db.session.commit()
    return redirect("/agenda")

# --------------------------------
# Execução
# --------------------------------
if __name__ == "__main__":
    app.run(debug=True)
